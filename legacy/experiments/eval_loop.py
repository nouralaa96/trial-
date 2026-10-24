"""Bounded chronological research loop. Run from v2 root; never places orders."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.features import build_features, executable_labels, FEATURE_COLUMNS
from research.modeling import _pooled, _eligible, GROUPS
from research.data import load_panel
from research.backtest import run_backtest
from research.run import audit_result, save_frames
from research.metrics import portfolio_metrics, paired_weekly_bootstrap
from diagnostics.trade_quality import loss_streak
OUT=ROOT/'analysis/eval_loop_v3'


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,default=str,allow_nan=False)+'\n')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def ledger(event,**fields):
    with (OUT/'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),event=event,**fields),default=str)+'\n')


def candidates(plan):
    g=plan['candidate_grid'];items=[]
    for h in g['horizons']:
        for label in g['labels']:
            for alpha in g['ridge_alphas']:
                items.append(dict(id=f'ridge_{label}_h{h}_a{int(alpha)}',strategy='ridge',horizon=h,label=label,alpha=alpha))
        items.append(dict(id=f'trend_h{h}',strategy='trend',horizon=h,label='none',alpha=None))
    return {x['id']:x for x in items}


def bracket_labels(frame,horizon,cap_multiplier=1.005,stop_atr=2.,target_atr=6.):
    """Unit gross outcomes conditional on entry; mirrors conservative raw fill rules.

    Earlier completion is observable at actual exit, while incomplete end tails
    are excluded conservatively. No fees/slippage in gross training targets.
    """
    if not frame.splits.isin([0,1]).all():
        raise ValueError('Bracket label generator requires a split-free instrument snapshot')
    out=pd.DataFrame({'label':np.nan,'label_matured':pd.NaT},index=frame.index)
    op,hi,lo,cl,div,atr=(frame[c].to_numpy() for c in ['open','high','low','close','dividends','atr14'])
    for t in range(len(frame)-horizon):
        if not np.isfinite(atr[t]) or atr[t]<=0:continue
        cap=cl[t]*cap_multiplier; stop=cap-stop_atr*atr[t];target=cap+target_atr*atr[t]
        if not 0<stop<cap<target or lo[t+1]>cap:continue
        entry=min(op[t+1],cap);accrued=0.
        for j in range(t+1,t+horizon+1):
            if j>t+1:accrued+=div[j]
            intraday=(j==t+1 and op[j]>cap)
            if entry<=stop or entry>=target:
                exit_price=entry  # immediate fill revalidation, gross0
            elif op[j]<=stop and not intraday:exit_price=op[j]
            elif lo[j]<=stop:exit_price=stop
            elif op[j]>=target and not intraday:exit_price=op[j]
            elif hi[j]>=target and not intraday:exit_price=target
            elif j==t+horizon:exit_price=cl[j]
            else:continue
            out.iloc[t,0]=(exit_price+accrued)/entry-1
            out.iloc[t,1]=frame.index[j]
            break
    return out


def training_rows(rows,cutoff):
    return rows[_eligible(rows)&(rows.date>='2010-01-01')&(rows.label_matured<=cutoff)]


def fit_predict(train,test,alpha):
    m=Pipeline([('scale',StandardScaler()),('ridge',Ridge(alpha=alpha))])
    m.fit(train[FEATURE_COLUMNS],train.label)
    return m.predict(test[FEATURE_COLUMNS]),m


def make_predictions(features,calendar,candidate,partition,plan):
    """Fit only the requested phase; no final model is fitted before locking."""
    begin,end=plan['periods'][partition]
    if candidate['strategy']=='trend':return None
    dest=OUT/'predictions'/partition/candidate['id']
    # No stale cache: outputs are recomputed for the declared immutable plan.
    labeled={}
    for symbol,f in features.items():
        labels=(executable_labels(f,candidate['horizon']) if candidate['label']=='fixed'
                else bracket_labels(f,candidate['horizon']))
        labeled[symbol]=f.drop(columns=['label','label_matured']).join(labels)
    wide=pd.DataFrame(np.nan,index=calendar,columns=list(features))
    logs,records=[],[]
    allowed=calendar[(calendar>=begin)&(calendar<=end)][10:]
    for group,symbols in GROUPS.items():
        rows=_pooled(labeled,symbols)
        for quarter in allowed.to_period('Q').unique():
            dates=allowed[allowed.to_period('Q')==quarter]
            first=dates[0];cutoff=calendar[calendar.get_loc(first)-11]
            train=training_rows(rows,cutoff)
            assert len(train)>=100 and train.label_matured.max()<=cutoff<first
            test=rows[np.isfinite(rows[FEATURE_COLUMNS]).all(axis=1)&rows.date.isin(dates)]
            pred,model=fit_predict(train,test,candidate['alpha'])
            for row,value in zip(test.itertuples(),pred):
                wide.loc[row.date,row.symbol]=value
                records.append(dict(date=row.date,symbol=row.symbol,prediction=float(value),label=row.label,
                                    label_matured=row.label_matured))
            logs.append(dict(group=group,first_decision=str(first.date()),cutoff=str(cutoff.date()),
                max_training_maturity=str(train.label_matured.max().date()),training_rows=len(train),
                alpha=candidate['alpha'],coefficients=model.named_steps['ridge'].coef_.tolist(),
                scaler_mean=model.named_steps['scale'].mean_.tolist()))
    dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(records).to_csv(dest/'predictions.csv',index=False)
    write_json(dest/'fits.json',logs)
    mature=pd.DataFrame(records).dropna(subset=['label','label_matured'])
    mature=mature[mature.label_matured<=end]
    scores=dict(n=len(mature),mse=float(np.mean((mature.prediction-mature.label)**2)),
        zero_mse=float(np.mean(mature.label**2)),direction_accuracy=float((np.sign(mature.prediction)==np.sign(mature.label)).mean()),
        always_positive_accuracy=float((mature.label>0).mean()),label_kind=candidate['label'])
    write_json(dest/'forecast_metrics.json',scores)
    return wide


def annual_return(equity,initial=5000.):
    years=(pd.Timestamp(equity.date.iloc[-1])-pd.Timestamp(equity.date.iloc[0])).days/365.25
    if years<=0:raise ValueError('Annualization needs positive elapsed time')
    final=float(equity.equity.iloc[-1])
    return (final/initial)**(1/years)-1 if final>0 else -1.,years


def summary(result,cfg):
    a=audit_result(result,cfg)
    assert not a['violations'],a
    e,t=result['equity'],result['trades']
    assert e.open_positions.iloc[-1]==0 and e.pending_positions.iloc[-1]==0
    m=portfolio_metrics(e,t,result['decisions'],initial_equity=5000.)
    cagr,years=annual_return(e)
    return {**{k:m[k] for k in ['net_pnl','net_return','max_drawdown','max_drawdown_dollars','completed_trades',
        'win_rate','profit_factor','fees','friction','net_expectancy_per_trade']},
        'cagr':cagr,'years':years,'loss_streak':loss_streak(t)['count'],
        'annualized_net_dollars':m['net_pnl']/years,'audit_violations':len(a['violations'])}


def rank_candidates(frame):
    """Predeclared deterministic score; only supplied phase can affect selection."""
    rows=[]
    for candidate,g in frame.groupby('candidate'):
        pass_count=int(((g.cagr>.10)&(g.max_drawdown<=.10)).sum())
        worst=float((g.cagr-2*(g.max_drawdown-.10).clip(lower=0)).min())
        rows.append(dict(candidate=candidate,pass_count=pass_count,worst_penalized_cagr=worst,
                         worst_drawdown=float(g.max_drawdown.max()),worst_cagr=float(g.cagr.min())))
    return pd.DataFrame(rows).sort_values(['pass_count','worst_penalized_cagr','worst_drawdown','candidate'],
        ascending=[False,False,True,True]).reset_index(drop=True)


def run_stage(partition,plan,all_candidates,selected_by_risk=None):
    config=json.loads((ROOT/'frozen_config.json').read_text())
    begin,end=plan['periods'][partition]
    # All labels, inputs and model fitting are truncated at this phase end.
    features=build_features({s:f.loc[:end].copy() for s,f in load_panel(ROOT/'data').items()})
    calendar=next(iter(features.values())).index
    sessions=calendar[(calendar>=begin)&(calendar<=end)]
    predictions={};rows=[]
    for risk in plan['risk_policies']:
        ids=list(all_candidates) if selected_by_risk is None else selected_by_risk[risk]
        scenarios=[name for name in config['scenarios'] if name.startswith(risk) and
                   (partition!='development' or name.endswith('_whole'))]
        for cid in ids:
            cand=all_candidates[cid]
            if cid not in predictions:predictions[cid]=make_predictions(features,calendar,cand,partition,plan)
            for scenario in scenarios:
                cfg={**config,**config['scenarios'][scenario],'max_holding_sessions':cand['horizon'],
                     'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-cand['horizon']-1].date())}
                result=run_backtest(features,predictions[cid],cfg,cand['strategy'],start=begin,end=end)
                s=summary(result,cfg)
                dest=OUT/'portfolios'/partition/scenario/cid
                save_frames(result,dest)
                rows.append(dict(partition=partition,risk=risk,scenario=scenario,candidate=cid,
                    strategy=cand['strategy'],horizon=cand['horizon'],label=cand['label'],**s))
                # Existing baseline parity anchors the new loop to tested execution.
                if cid=='trend_h5' or (partition=='development' and cid=='ridge_fixed_h5_a1'):
                    old=pd.read_csv(ROOT/'artifacts/historical'/partition/scenario/cand['strategy']/'equity.csv')
                    assert np.allclose(result['equity'].equity,old.equity,rtol=0,atol=1e-6)
            pd.DataFrame(rows).to_csv(OUT/f'{partition}_results.csv',index=False)
            ledger('candidate_complete',partition=partition,risk=risk,candidate=cid,portfolios=len(scenarios))
            print(f'{partition}: {risk}/{cid} complete ({len(rows)} portfolios)',flush=True)
    return pd.DataFrame(rows)


def load_equity(partition,scenario,candidate):
    return pd.read_csv(OUT/'portfolios'/partition/scenario/candidate/'equity.csv',parse_dates=['date'])


def final_gates(frame,locked):
    gates={}
    for risk,entry in locked.items():
        r=frame[(frame.risk==risk)&(frame.candidate==entry['ridge'])]
        base=r[r.scenario.str.contains('_base_')];stress=r[r.scenario.str.contains('_stress_')]
        checks=dict(base_annual_return_above_10pct=bool((base.cagr>.10).all()),
            base_drawdown_at_most_10pct=bool((base.max_drawdown<=.10).all()),
            stress_profitable=bool((stress.cagr>0).all()),stress_drawdown_at_most_10pct=bool((stress.max_drawdown<=.10).all()),
            minimum_100_trades=bool((base.completed_trades>=100).all()))
        comparisons=[]
        for scenario in base.scenario:
            e=load_equity('final',scenario,entry['ridge'])
            model=base[base.scenario==scenario].iloc[0]
            for benchmark in sorted(set([entry['trend'],'trend_h5'])):
                b=frame[(frame.scenario==scenario)&(frame.candidate==benchmark)].iloc[0]
                other=load_equity('final',scenario,benchmark)
                bootstrap=paired_weekly_bootstrap(e,other,initial_equity=5000.,resamples=10000,
                    seed=20261020,block_lengths=(2,4,8))
                lower=bootstrap['ci95_annualized_incremental_dollars'][0]
                comparisons.append(dict(scenario=scenario,benchmark=benchmark,
                    annual_increment_dollars=float((model.net_pnl-b.net_pnl)/model.years),
                    bootstrap_lower=lower,bootstrap=bootstrap))
        checks['usefulness_annual_increment_above_100usd']=all(x['annual_increment_dollars']>100 for x in comparisons)
        checks['incremental_bootstrap_lower_positive']=all(x['bootstrap_lower'] is not None and x['bootstrap_lower']>0 for x in comparisons)
        gates[risk]=dict(candidate=entry['ridge'],checks=checks,historical_pass=all(checks.values()),
            deployment_ready=False,comparisons=comparisons,
            status='HISTORICAL_PASS_REQUIRES_NEW_EVALUATION' if all(checks.values()) else 'TARGET_NOT_ESTABLISHED')
    return gates


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((OUT/'plan.json').read_text());ph=digest(OUT/'plan.json')
    # Refuse overwrite: reruns require a distinct archived output directory.
    if (OUT/'events.jsonl').exists():raise RuntimeError('Existing run retained; archive output before rerunning')
    ledger('run_started',plan_sha256=ph)
    config=json.loads((ROOT/'artifacts/source-manifest.json').read_text())
    for name,h in config['sha256'].items():assert digest(ROOT/name)==h,name
    catalog=candidates(plan);write_json(OUT/'candidates.json',catalog)
    dev=run_stage('development',plan,catalog)
    shortlist={};validation_ids={}
    for risk in plan['risk_policies']:
        f=dev[dev.risk==risk]
        rr=rank_candidates(f[f.strategy=='ridge']);tr=rank_candidates(f[f.strategy=='trend'])
        shortlist[risk]=dict(ridge=rr.candidate.iloc[:3].tolist(),trend=tr.candidate.iloc[0],
                             ranking_ridge=rr.to_dict('records'),ranking_trend=tr.to_dict('records'))
        validation_ids[risk]=shortlist[risk]['ridge']+[shortlist[risk]['trend']]
    write_json(OUT/'shortlist.json',shortlist);ledger('shortlist_locked',sha256=digest(OUT/'shortlist.json'))
    val=run_stage('validation',plan,catalog,validation_ids)
    locked={};final_ids={}
    for risk in plan['risk_policies']:
        rr=rank_candidates(val[(val.risk==risk)&(val.strategy=='ridge')])
        locked[risk]=dict(ridge=rr.candidate.iloc[0],trend=shortlist[risk]['trend'],validation_ranking=rr.to_dict('records'))
        final_ids[risk]=list(dict.fromkeys([locked[risk]['ridge'],locked[risk]['trend'],'trend_h5']))
    write_json(OUT/'locked.json',locked);ledger('final_candidates_locked',sha256=digest(OUT/'locked.json'))
    final=run_stage('final',plan,catalog,final_ids)
    gates=final_gates(final,locked);write_json(OUT/'gates.json',gates)
    for name,h in config['sha256'].items():assert digest(ROOT/name)==h,name
    assert digest(OUT/'plan.json')==ph
    ledger('run_completed',development_runs=len(dev),validation_runs=len(val),final_runs=len(final),
           statuses={r:g['status'] for r,g in gates.items()})
    print(json.dumps({r:{'candidate':g['candidate'],'status':g['status'],'checks':g['checks']} for r,g in gates.items()},indent=2),flush=True)

if __name__=='__main__':run()
