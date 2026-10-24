"""Reproduce the bounded six-candidate V4 iteration: python evaluate.py --run."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from model_pipeline import ROOT,MODEL,CONTEXT,load_inputs,predict_stage,write_json,digest,confidence_records
from execution_adapter import run_engine,benchmark
from legacy.research.metrics import portfolio_metrics,paired_weekly_bootstrap

COUNTS={'fits':0,'portfolios':0}
ARTIFACTS=ROOT/'artifacts'
def event(name,**kw):
    with (MODEL/'events.jsonl').open('a') as f:f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),event=name,**kw),default=str)+'\n')

def clean(obj):
    if isinstance(obj,dict):return {str(k):clean(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [clean(v) for v in obj]
    if isinstance(obj,(np.integer,)):return int(obj)
    if isinstance(obj,(float,np.floating)):return float(obj) if np.isfinite(obj) else None
    return obj

def metrics(result,passive=False):
    e=result['equity'].copy();t=result['trades'];d=result['decisions']
    if passive:e=e.drop(columns=['weekly_limit'])
    m=portfolio_metrics(e,t,d,initial_equity=5000.)
    years=(pd.Timestamp(e.date.iloc[-1])-pd.Timestamp(e.date.iloc[0])).days/365.25
    pnl=t.get('net_pnl',t.get('pnl',pd.Series(dtype=float)))
    streak=best=0
    for v in pnl:streak=streak+1 if v<0 else 0;best=max(best,streak)
    m.update(cagr=(float(e.equity.iloc[-1])/5000.)**(1/years)-1,years=years,loss_streak=best)
    return clean(m)

def save_result(partition,scenario,cid,result):
    dest=MODEL/'portfolios'/partition/scenario/cid;dest.mkdir(parents=True,exist_ok=True)
    for name,f in result.items():f.to_csv(dest/f'{name}.csv',index=False)
    COUNTS['portfolios']+=1
    if COUNTS['portfolios']>200:raise RuntimeError('Portfolio budget exceeded')

def curve(partition,scenario,cid):return pd.read_csv(MODEL/'portfolios'/partition/scenario/cid/'equity.csv',parse_dates=['date'])

def comparison_curve(partition,scenario,cid):
    """Normalize week keys before paired calendar-week comparisons.

    Active portfolios retain the Riyadh-aligned week label used by their risk
    ledger, while passive references have no risk week.  The uncertainty
    comparison is explicitly by common calendar week, so derive that key from
    the identical session dates for both sides instead of mixing label types.
    """
    return curve(partition,scenario,cid).drop(columns=['week'],errors='ignore')

def rank_candidates(frame):
    if set(frame.partition)!={'development'}:raise ValueError('Ranking accepts development only')
    rows=[]
    for cid,g in frame[frame.candidate.isin(['P01','P02','C03','C04'])].groupby('candidate'):
        margins=[];passing=0
        for r in g.itertuples():
            refs=frame[(frame.scenario==r.scenario)&frame.candidate.isin(['SPY_cash_dividend','SPY_reinvested_total_return','T05'])]
            b=float(refs.cagr.max());m=r.cagr-b
            passing+=int(m>0 and r.max_drawdown<=.10)
            margins.append(m-2*max(0,r.max_drawdown-.10))
        rows.append(dict(candidate=cid,passing_scenarios=passing,worst_penalized_increment=min(margins),mean_turnover=float(g.turnover.mean())))
    return pd.DataFrame(rows).sort_values(['passing_scenarios','worst_penalized_increment','mean_turnover','candidate'],ascending=[False,False,True,True])

def stage(partition,ids,registry,config):
    begin,end=registry['periods'][partition];features,calendar=load_inputs(end)
    sessions=calendar[(calendar>=begin)&(calendar<=end)]
    catalog={c['id']:c for c in registry['candidates']};preds={};models={};records={};rows=[]
    # C04 shares C03 production models and its independent historical calibration.
    compute=list(dict.fromkeys(['C03' if cid=='C04' else cid for cid in ids]))
    for cid in compute:
        p,l,logs,recs,mods,n=predict_stage(catalog[cid],partition,features,calendar,registry)
        COUNTS['fits']+=n
        if COUNTS['fits']>1000:raise RuntimeError('Fit budget exceeded')
        preds[cid]=p;models[cid]=mods;records[cid]=recs
        if cid=='C03':preds['C04']=p.where(l>0);models['C04']=mods;records['C04']=confidence_records(recs)
        dest=MODEL/'predictions'/partition/cid;dest.mkdir(parents=True,exist_ok=True)
        pd.DataFrame(recs).to_csv(dest/'predictions.csv',index=False);write_json(dest/'fits.json',logs)
        event('predictions_complete',partition=partition,candidate=cid,fits=n)
    for cid in ids:
        if cid=='C04':
            dest=MODEL/'predictions'/partition/cid;dest.mkdir(parents=True,exist_ok=True)
            pd.DataFrame(records[cid]).to_csv(dest/'predictions.csv',index=False)
        if partition=='final' and records.get(cid):
            (ARTIFACTS/'predictions').mkdir(parents=True,exist_ok=True)
            pd.DataFrame(records[cid]).to_csv(ARTIFACTS/'predictions'/f'{cid}.csv',index=False)
    for scenario,overrides in config['scenarios'].items():
        cfg={**config,**overrides,'max_holding_sessions':20,'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-21].date())}
        for cid in ids:
            # All six use explicit predictions; deterministic trends are frozen
            # return20 forecasts, enabling exactly the same context entry mask.
            result=run_engine(features,preds[cid],cfg,'ridge',begin,end)
            save_result(partition,scenario,cid,result);m=metrics(result)
            rows.append(dict(partition=partition,scenario=scenario,candidate=cid,**m))
        for cid,reinvest in [('SPY_cash_dividend',False),('SPY_reinvested_total_return',True)]:
            result=benchmark(features['SPY'],cfg,begin,end,reinvest)
            save_result(partition,scenario,cid,result);rows.append(dict(partition=partition,scenario=scenario,candidate=cid,**metrics(result,True)))
        event('scenario_complete',partition=partition,scenario=scenario,portfolios=COUNTS['portfolios'])
    # Exact frozen sensitivities; not included in rank or finalist replacement.
    if partition=='final':
        for cid in ['P01','T05']:
            p,_,logs,recs,mods,n=predict_stage(catalog[cid],partition,features,calendar,registry,common=False)
            COUNTS['fits']+=n
            for scenario,overrides in config['scenarios'].items():
                cfg={**config,**overrides,'max_holding_sessions':20,'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-21].date())}
                result=run_engine(features,p,cfg,'ridge',begin,end);name=cid+'_fullhistory'
                save_result(partition,scenario,name,result);rows.append(dict(partition=partition,scenario=scenario,candidate=name,**metrics(result)))
        finalist=ids[0]
        for variant in ['no_trend','half_risk_ceilings']:
            for scenario,overrides in config['scenarios'].items():
                if not scenario.endswith('_whole'):continue
                cfg={**config,**overrides,'max_holding_sessions':20,'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-21].date())}
                if variant=='half_risk_ceilings':
                    cfg['per_trade_risk_fraction']*=.5;cfg['session_risk_fraction']*=.5
                result=run_engine(features,preds[finalist],cfg,'ridge',begin,end,trend_filter=variant!='no_trend');name=finalist+'_'+variant
                save_result(partition,scenario,name,result);rows.append(dict(partition=partition,scenario=scenario,candidate=name,**metrics(result)))
    frame=pd.DataFrame(rows)
    write_json(MODEL/f'{partition}_metrics.json',clean(rows))
    frame.drop(columns=[c for c in frame if isinstance(frame[c].iloc[0],(dict,list))]).to_csv(MODEL/f'{partition}_results.csv',index=False)
    folds=[];years=[]
    for r in rows:
        e=curve(partition,r['scenario'],r['candidate']);previous=5000.
        for year,g in e.groupby(e.date.dt.year):
            final=float(g.equity.iloc[-1]);years.append(dict(partition=partition,scenario=r['scenario'],candidate=r['candidate'],year=int(year),return_fraction=final/previous-1,pnl=final-previous,partial=int(year)==2026));previous=final
        previous=5000.
        for quarter,g in e.groupby(e.date.dt.to_period('Q')):
            final=float(g.equity.iloc[-1]);folds.append(dict(partition=partition,scenario=r['scenario'],candidate=r['candidate'],quarter=str(quarter),return_fraction=final/previous-1,pnl=final-previous));previous=final
    pd.DataFrame(years).to_csv(MODEL/f'{partition}_yearly.csv',index=False);pd.DataFrame(folds).to_csv(MODEL/f'{partition}_folds.csv',index=False)
    return frame,models,records

def gates(partition,frame,cid):
    selected=frame[frame.candidate==cid];base=selected[selected.scenario.str.contains('_base_')];stress=selected[selected.scenario.str.contains('_stress_')]
    checks=dict(base_profitable=bool((base.net_pnl>0).all()),stress_profitable=bool((stress.net_pnl>0).all()),base_drawdown_at_most_10pct=bool((base.max_drawdown<=.10).all()),stress_drawdown_at_most_10pct=bool((stress.max_drawdown<=.10).all()),minimum_100_completed_trades=bool((selected.completed_trades>=100).all()))
    increments=[];annual=[]
    yearly=pd.read_csv(MODEL/f'{partition}_yearly.csv')
    refs=['SPY_cash_dividend','SPY_reinvested_total_return','T05']+(['T05_fullhistory'] if partition=='final' else [])
    for r in base.itertuples():
        for ref in refs:
            other=frame[(frame.candidate==ref)&(frame.scenario==r.scenario)].iloc[0]
            boot=paired_weekly_bootstrap(comparison_curve(partition,r.scenario,cid),comparison_curve(partition,r.scenario,ref),initial_equity=5000.,resamples=2000,seed=20261021,block_lengths=(2,4,8))
            increments.append(dict(scenario=r.scenario,reference=ref,cagr_increment=r.cagr-other.cagr,net_pnl_increment=r.net_pnl-other.net_pnl,bootstrap=boot))
        cy=yearly[(yearly.candidate==cid)&(yearly.scenario==r.scenario)]
        for y in cy.itertuples():
            spy=float(yearly[(yearly.candidate=='SPY_reinvested_total_return')&(yearly.scenario==r.scenario)&(yearly.year==y.year)].return_fraction.iloc[0])
            annual.append(dict(scenario=r.scenario,year=int(y.year),partial=bool(y.partial),strategy_return=y.return_fraction,spy_total_return=spy,excess_percentage_points=100*(y.return_fraction-spy),positive_market_multiple=y.return_fraction/spy if spy>0 else None,five_times_gate=None if bool(y.partial) or spy<=0 else bool(y.return_fraction>=5*spy)))
    checks['positive_increment_over_both_baselines_each_base_scenario']=all(x['cagr_increment']>0 for x in increments)
    checks['exploratory_paired_CI_lower_positive_all_block_lengths']=all(v['ci95'] is not None and v['ci95'][0]>0 for x in increments for v in x['bootstrap']['block_sensitivity'].values())
    full=[a['five_times_gate'] for a in annual if a['five_times_gate'] is not None]
    checks['five_times_positive_SPY_full_calendar_years']=bool(full) and all(full)
    return dict(partition=partition,candidate=cid,checks=checks,all_gates_pass=all(checks.values()),annual_market_targets=annual,comparisons=increments,history_status='EXPLORATORY_REUSED_HISTORY_NO_PROSPECTIVE_EVIDENCE')

def run():
    if (MODEL/'events.jsonl').exists():raise RuntimeError('Run retained; use a copied isolated output directory for reproduction')
    registry=json.loads((MODEL/'registry.json').read_text());rh=digest(MODEL/'registry.json')
    features,calendar=load_inputs();mask=np.isfinite(features['SPY'][CONTEXT]).all(axis=1)
    eligible_availability={}
    for phase,(begin,end) in registry['periods'].items():
        sessions=calendar[(calendar>=begin)&(calendar<=end)]
        entries=sessions[10:-20]
        eligible_availability[phase]=dict(first_eligible=str(entries[0].date()),last_eligible=str(entries[-1].date()),eligible_sessions=len(entries),missing_context_eligible_sessions=int((~mask.loc[entries]).sum()))
    write_json(MODEL/'availability_frozen.json',dict(utc=datetime.now(timezone.utc).isoformat(),registry_sha256=rh,first_common=str(calendar[mask][0].date()),last_common=str(calendar[mask][-1].date()),common_sessions=int(mask.sum()),missing_sessions=[str(d.date()) for d in calendar[(calendar>='2010-01-01')&~mask]],eligible_decision_availability=eligible_availability,decision='common exact observed features entry mask; full phase valuation calendar'))
    source_hashes={str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'model_pipeline.py',ROOT/'evaluate.py',ROOT/'execution_adapter.py',ROOT/'analysis/model/registry.json',ROOT/'data/context.csv',*sorted((ROOT/'data/processed').glob('*.csv'))]}
    write_json(MODEL/'inputs.json',source_hashes);event('run_started',registry_sha256=rh)
    config=json.loads((ROOT/'legacy/frozen_config.json').read_text())
    dev,_,_=stage('development',[c['id'] for c in registry['candidates']],registry,config)
    ranking=rank_candidates(dev);ranking.to_csv(MODEL/'development_ranking.csv',index=False);cid=ranking.candidate.iloc[0]
    lock=dict(candidate=cid,locked_utc=datetime.now(timezone.utc).isoformat(),basis='development_only',registry_sha256=rh,ranking=ranking.to_dict('records'),replacement_after_validation=False)
    write_json(MODEL/'locked.json',lock);event('finalist_locked',**lock)
    ids=list(dict.fromkeys([cid,'T05','T06']))
    val,_,_=stage('validation',ids,registry,config);vg=gates('validation',val,cid);write_json(MODEL/'validation_gates.json',vg)
    event('validation_complete',candidate=cid,all_gates_pass=vg['all_gates_pass'],replacement=False)
    final,models,records=stage('final',ids,registry,config);fg=gates('final',final,cid);write_json(MODEL/'final_gates.json',fg)
    status='REJECTED_RESEARCH' if not(vg['all_gates_pass'] and fg['all_gates_pass']) else 'HISTORICAL_ONLY_REQUIRES_NEW_PROSPECTIVE_EVALUATION'
    (ARTIFACTS/'models').mkdir(parents=True,exist_ok=True)
    joblib.dump(models[cid],ARTIFACTS/'models/finalist.joblib')
    metadata=dict(candidate=cid,status=status,deployment_ready=False,feature_columns={g:m['features'] for g,m in models[cid].items()},training_cutoff={g:m['training_cutoff'] for g,m in models[cid].items()},data_hashes={p:h for p,h in source_hashes.items() if p.startswith('data/')},source_hashes=source_hashes,predictions_file=str(ARTIFACTS/'predictions'/f'{cid}.csv'),registry_sha256=rh,history_status=registry['history_status'])
    write_json(ARTIFACTS/'models/metadata.json',metadata)
    recs=records[cid];latest=max(str(r['date']) for r in recs);write_json(ARTIFACTS/'models/latest_decision.json',dict(status=status,date=latest,decisions=[clean(r) for r in recs if str(r['date'])==latest]))
    calibration=[]
    for partition in registry['periods']:
        p=MODEL/'predictions'/partition/'C03'/'predictions.csv'
        if p.exists():
            f=pd.read_csv(p);f=f.dropna(subset=['prediction','label','prediction_low']);f=f[pd.to_datetime(f.label_matured)<=registry['periods'][partition][1]]
            if len(f):
                for group,g in f.groupby('group'):calibration.append(dict(partition=partition,group=group,n=len(g),median_absolute_error=float(np.median(np.abs(g.prediction-g.label))),lower_bound_coverage=float((g.label>=g.prediction_low).mean()),positive_lower_count=int((g.prediction_low>0).sum()),mse=float(np.mean((g.prediction-g.label)**2))))
    write_json(MODEL/'confidence_calibration.json',calibration)
    assert digest(MODEL/'registry.json')==rh
    assert all(digest(ROOT/p)==h for p,h in source_hashes.items())
    write_json(MODEL/'run_counts.json',dict(**COUNTS,budget_portfolios=200,budget_fits=1000));event('run_completed',status=status,**COUNTS)
    print(json.dumps(dict(candidate=cid,status=status,counts=COUNTS,checks=fg['checks']),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    if not args.run:parser.error('--run required')
    if args.output:
        if args.output.exists():parser.error('--output must be a fresh nonexistent directory')
        source=MODEL/'registry.json';MODEL=args.output.resolve();MODEL.mkdir(parents=True)
        (MODEL/'registry.json').write_bytes(source.read_bytes())
        ARTIFACTS=MODEL/'artifacts'
    run()
