"""Run predeclared exploratory candidates; frozen original source/config is untouched."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.data import load_panel
from research.features import build_features, FEATURE_COLUMNS
from research.modeling import _pooled, _eligible, _fit, GROUPS
from research.backtest import run_backtest
from research.metrics import portfolio_metrics
from research.run import audit_result, save_frames
from diagnostics.trade_quality import loss_streak
OUT=ROOT/'analysis/trade_quality'
PERIODS={'development':('2019-01-01','2021-12-31'),'validation':('2022-01-01','2023-12-31')}


def rolling_training(rows, cutoff):
    return rows[_eligible(rows) & (rows.date>=pd.Timestamp(cutoff)-pd.DateOffset(years=3)) &
                (rows.label_matured<=cutoff)]


def rolling_predictions(features, calendar, metadata):
    wide=pd.DataFrame(np.nan,index=calendar,columns=list(features))
    fits, records=[],[]
    for group,symbols in GROUPS.items():
        rows=_pooled(features,symbols)
        for partition,(begin,end) in PERIODS.items():
            allowed=calendar[(calendar>=begin)&(calendar<=end)][10:]
            for quarter in allowed.to_period('Q').unique():
                dates=allowed[allowed.to_period('Q')==quarter]
                first=dates[0]
                cutoff=calendar[calendar.get_loc(first)-11]
                train=rolling_training(rows,cutoff)
                assert train.label_matured.max()<=cutoff<first
                assert len(train)>=100
                alpha=1. if partition=='development' else metadata['alpha_selection'][group]['selected']
                model=_fit(train,alpha)
                test=rows[np.isfinite(rows[FEATURE_COLUMNS]).all(axis=1)&rows.date.isin(dates)]
                predictions=model.predict(test[FEATURE_COLUMNS])
                for row,pred in zip(test.itertuples(),predictions):
                    wide.loc[row.date,row.symbol]=pred
                    records.append(dict(partition=partition,date=row.date,symbol=row.symbol,prediction=float(pred),
                        label=row.label,label_matured=row.label_matured))
                fits.append(dict(group=group,partition=partition,first_decision=str(first.date()),
                    cutoff=str(cutoff.date()),min_training_date=str(train.date.min().date()),
                    max_training_maturity=str(train.label_matured.max().date()),
                    training_rows=len(train),alpha=alpha))
    return wide,pd.DataFrame(records),fits


def summarize(result, cfg):
    audit=audit_result(result,cfg)
    assert not audit['violations'],audit
    e,t=result['equity'],result['trades']
    assert e.open_positions.iloc[-1]==0 and e.pending_positions.iloc[-1]==0
    m=portfolio_metrics(e,t,result['decisions'],initial_equity=5000.)
    s=loss_streak(t)
    return {**{k:m[k] for k in ('net_pnl','max_drawdown','max_drawdown_dollars','completed_trades',
        'net_expectancy_per_trade','profit_factor','win_rate','fees','friction')},
        'loss_streak':s['count'],'gross_same_trades':m['net_pnl']+m['fees']+m['friction'],
        'controllable_violations':audit['controllable_violations']}


def run():
    plan=OUT/'EXPERIMENT_PLAN.json'
    plan_hash=hashlib.sha256(plan.read_bytes()).hexdigest()
    config=json.loads((ROOT/'frozen_config.json').read_text())
    metadata=json.loads((ROOT/'inputs/model_metadata.json').read_text())
    # Truncate before building labels: no new candidate accesses final-period prices.
    panel={s:f.loc[:'2023-12-31'].copy() for s,f in load_panel(ROOT/'data').items()}
    features=build_features(panel)
    calendar=next(iter(panel.values())).index
    frozen=pd.read_csv(ROOT/'inputs/ridge_explanations.csv',parse_dates=['date','label_matured'])
    frozen=frozen[frozen.date<='2023-12-31']
    original=frozen.pivot(index='date',columns='symbol',values='prediction').reindex(calendar)
    rolling,records,fits=rolling_predictions(features,calendar,metadata)
    records.to_csv(OUT/'rolling_predictions.csv',index=False)
    (OUT/'rolling_fit_audit.json').write_text(json.dumps(fits,indent=2)+'\n')
    forecast=[]
    for partition,(_,end) in PERIODS.items():
        a=records[(records.partition==partition)&(records.label_matured<=end)].dropna(subset=['label'])
        b=frozen[(frozen.partition==partition)&(frozen.label_matured<=end)].dropna(subset=['label'])
        joined=a.merge(b[['date','symbol','prediction','label']],on=['date','symbol'],suffixes=('_rolling','_original'),validate='one_to_one')
        assert len(joined)==len(a)==len(b)
        assert np.allclose(joined.label_rolling,joined.label_original)
        for variant in ('rolling','original'):
            pred=joined[f'prediction_{variant}'];label=joined.label_original
            forecast.append(dict(partition=partition,variant=variant,n=len(joined),
                mse=float(np.mean((pred-label)**2)),zero_mse=float(np.mean(label**2)),
                direction_accuracy=float((np.sign(pred)==np.sign(label)).mean()),
                always_positive_accuracy=float((label>0).mean())))
    pd.DataFrame(forecast).to_csv(OUT/'trial_forecast_metrics.csv',index=False)
    rows,controls=[],[]
    for partition,(begin,end) in PERIODS.items():
        sessions=calendar[(calendar>=begin)&(calendar<=end)]
        for strategy in ('ridge','trend'):
            cfg={**config,**config['scenarios']['risk05_base_whole'],
                 'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-6].date())}
            result=run_backtest(features,original,cfg,strategy,start=begin,end=end)
            s=summarize(result,cfg)
            saved=ROOT/'artifacts/historical'/partition/'risk05_base_whole'/strategy
            se=pd.read_csv(saved/'equity.csv');st=pd.read_csv(saved/'trades.csv')
            assert np.allclose(result['equity'].equity,se.equity,rtol=0,atol=1e-6)
            assert np.allclose(result['trades'].net_pnl,st.net_pnl,rtol=0,atol=1e-6)
            assert np.allclose(result['trades'].qty,st.qty,rtol=0,atol=1e-8)
            controls.append(dict(partition=partition,strategy=strategy,matched=True,**s))
        print(f'{partition}: baseline controls matched',flush=True)
        for scenario,override in config['scenarios'].items():
            for variant,strategy,hold,pred in [('ridge_rolling3y','ridge',5,rolling),
                    ('ridge_hold10','ridge',10,original),('trend_hold10','trend',10,original)]:
                cfg={**config,**override,'max_holding_sessions':hold,
                     'entry_start':str(sessions[10].date()),'entry_end':str(sessions[-hold-1].date())}
                result=run_backtest(features,pred,cfg,strategy,start=begin,end=end)
                s=summarize(result,cfg)
                dest=OUT/'trials'/partition/scenario/variant
                save_frames(result,dest)
                rows.append(dict(partition=partition,scenario=scenario,variant=variant,
                    baseline_strategy=strategy,entry_end=cfg['entry_end'],**s))
            print(f'{partition}: {scenario} finished',flush=True)
    frame=pd.DataFrame(rows)
    baseline=pd.read_csv(OUT/'summary.csv')
    matched=frame.merge(baseline[['partition','scenario','strategy','net_pnl','max_drawdown']],
        left_on=['partition','scenario','baseline_strategy'],right_on=['partition','scenario','strategy'],suffixes=('','_baseline'),validate='many_to_one')
    matched['delta_net_pnl']=matched.net_pnl-matched.net_pnl_baseline
    matched['delta_drawdown_pp']=100*(matched.max_drawdown-matched.max_drawdown_baseline)
    matched.to_csv(OUT/'trial_comparison.csv',index=False)
    pd.DataFrame(controls).to_csv(OUT/'baseline_controls.csv',index=False)
    assert hashlib.sha256(plan.read_bytes()).hexdigest()==plan_hash
    (OUT/'trial_run_audit.json').write_text(json.dumps(dict(plan_sha256=plan_hash,
        candidate_runs=len(rows),baseline_controls=len(controls),latest_candidate_price='2023-12-29',
        final_period_candidate_runs=0,controllable_violations=int(frame.controllable_violations.sum())),indent=2)+'\n')
    print(matched[matched.scenario=='risk05_base_whole'].to_string(index=False),flush=True)

if __name__=='__main__':run()
