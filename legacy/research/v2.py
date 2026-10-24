"""Isolated, predeclared $5,000 risk-fraction comparison; no live orders."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from .run import ROOT, audit_result, chart, ledger, save_frames, software_evidence, write_json
from .features import build_features
from .backtest import run_backtest
from .metrics import portfolio_metrics, paired_weekly_bootstrap
from .acceptance import evaluate_gates
from .modeling import PARTITIONS


def frozen_predictions(calendar):
    manifest = json.loads((ROOT/'inputs/manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((ROOT/'inputs'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen prediction input hash mismatch: '+name)
    rows = pd.read_csv(ROOT/'inputs/ridge_explanations.csv', parse_dates=['date'])
    return rows.pivot(index='date', columns='symbol', values='prediction').reindex(calendar)


def execute(features, predictions, cfg, strategy, begin, end, destination):
    result = run_backtest(features, predictions, cfg, strategy, start=begin, end=end)
    audit = audit_result(result, cfg)
    if audit['violations']:
        raise AssertionError(audit)
    save_frames(result, destination)
    metrics = portfolio_metrics(result['equity'], result['trades'], result['decisions'],
        initial_equity=cfg['initial_equity'], weekly_limit=cfg['weekly_budget'])
    d = result['decisions']
    admissions = d[d.status == 'admitted'] if len(d) and 'status' in d else pd.DataFrame()
    if len(admissions):
        fractions = admissions.planned_risk/admissions.equity_at_admission
        metrics['admission_risk'] = {'plans':len(admissions),
            'mean_fraction_of_current_equity':float(fractions.mean()),
            'maximum_fraction_of_current_equity':float(fractions.max()),
            'mean_planned_dollars':float(admissions.planned_risk.mean()),
            'maximum_planned_dollars':float(admissions.planned_risk.max())}
    else:
        metrics['admission_risk'] = {'plans':0, 'mean_fraction_of_current_equity':None,
            'maximum_fraction_of_current_equity':None, 'mean_planned_dollars':None,
            'maximum_planned_dollars':None}
    return result, metrics, audit


def compare(config, synthetic=False):
    if config.get('configuration_status') != 'frozen':
        raise ValueError('Configuration must be frozen before a run')
    if synthetic:
        import exchange_calendars as xc
        dates = xc.get_calendar('XNYS', start='2023-01-01', end='2024-12-31').sessions.tz_localize(None)
        panel = {}
        for j, symbol in enumerate(config['universe']):
            x = np.arange(len(dates)); close=50+j*10+.04*x+.4*np.sin(x/12+j)
            panel[symbol]=pd.DataFrame({'open':close-.02,'high':close+.5,'low':close-.5,
                'close':close,'volume':1e6,'dividends':0.,'splits':1.},index=dates)
        predictions=pd.DataFrame(.04,index=dates,columns=panel)
        periods=[('synthetic','2024-01-01','2024-12-31')]
    else:
        from .data import load_panel
        panel=load_panel(ROOT/'data')
        dates=next(iter(panel.values())).index
        predictions=frozen_predictions(dates)
        periods=PARTITIONS
    features=build_features(panel)
    out=ROOT/'artifacts'/('synthetic-smoke' if synthetic else 'historical')
    out.mkdir(parents=True,exist_ok=True)
    partitions={}
    for partition,begin,end in periods:
        sessions=dates[(dates>=begin)&(dates<=end)]
        summary={}
        for name,override in config['scenarios'].items():
            cfg={**config,**override,'entry_start':str(sessions[10].date()),
                 'entry_end':str(sessions[-6].date())}
            dest=out/partition/name
            results,metrics,audits={},{},{}
            for strategy in ['cash','trend','ridge']:
                result,m,a=execute(features,predictions,cfg,strategy,begin,end,dest/strategy)
                results[strategy],metrics[strategy],audits[strategy]=result,m,a
            if not synthetic:
                boot=paired_weekly_bootstrap(results['ridge']['equity'],results['trend']['equity'],
                    initial_equity=5000.,resamples=config['bootstrap_resamples'],
                    seed=config['bootstrap_seed'],block_lengths=tuple(config['bootstrap_block_weeks']))
                ci=boot['ci95_annualized_incremental_dollars']
                metrics['bootstrap']=boot
                metrics['comparison']={'incremental_pnl':boot['incremental_net_pnl'],
                    'annualized_incremental_pnl':boot['annualized_incremental_dollars'],
                    'bootstrap_lower':ci[0] if ci else None,'bootstrap_upper':ci[1] if ci else None}
            metrics['audits']=audits
            metrics['controllable_violations']=sum(a['controllable_violations'] for a in audits.values())
            summary[name]=metrics
            chart(results,dest/'equity.png',f'{"SYNTHETIC fixture" if synthetic else partition}: {name}; $5,000')
        partitions[partition]=summary
        print(f'Completed {partition}: {len(summary)*3} portfolios',flush=True)
    result={'data_kind':'SYNTHETIC' if synthetic else 'HISTORICAL',
        'historical_interpretation':config['historical_interpretation'],
        'initial_equity':5000.,'partitions':partitions,'software_evidence':software_evidence(),
        'incremental_data_api_cost':0.,'incremental_inference_api_cost':0.,
        'hosting_cost':None,'hosting_note':'Not separately metered',
        'model_policy':'Original v1 quarterly predictions reused byte-for-byte; no retraining or tuning'}
    if not synthetic:
        variations={f'cap_{c}':{'entry_cap_multiplier':c}
                    for c in config['nearby_parameter_sensitivity']['entry_cap_multiplier']}
        variations.update({f'atr_{s}_{t}':{'stop_atr':s,'target_atr':t}
            for s,t in config['nearby_parameter_sensitivity']['stop_target_atr_pairs']})
        sensitivities={}
        sessions=dates[(dates>=config['final_start'])&(dates<=config['final_end'])]
        for label,changes in variations.items():
            sensitivities[label]={}
            for name,override in config['scenarios'].items():
                cfg={**config,**override,**changes,'entry_start':str(sessions[10].date()),
                     'entry_end':str(sessions[-6].date())}
                sensitivities[label][name]={}
                for strategy in ['ridge','trend']:
                    _,m,a=execute(features,predictions,cfg,strategy,config['final_start'],config['final_end'],
                        out/'sensitivity'/label/name/strategy)
                    m['audit']=a; sensitivities[label][name][strategy]=m
            print('Completed frozen sensitivity '+label,flush=True)
        write_json(out/'sensitivity.json',sensitivities)
        gates={}
        for risk in ['risk05','risk10']:
            subset={k.removeprefix(risk+'_'):v for k,v in partitions['final'].items() if k.startswith(risk+'_')}
            gates[risk]=evaluate_gates(subset,software_passed=result['software_evidence']['passed'],
                historical_complete=True,years=(sessions[-1]-sessions[0]).days/365.25,
                robustness_reviewed=False,initial_equity=5000.)
        result['gates']=gates
        result['status']='FAIL' if any(g['status']=='FAIL' for g in gates.values()) else 'INCONCLUSIVE'
        write_json(out/'gates.json',gates)
    write_json(out/'metrics.json',result)
    ledger('v2_synthetic_completed' if synthetic else 'v2_historical_completed',
           primary_portfolios=24 if synthetic else 72,sensitivity_portfolios=0 if synthetic else 64,
           config_sha256=hashlib.sha256((ROOT/'frozen_config.json').read_bytes()).hexdigest())
    return result


def report():
    m=json.loads((ROOT/'artifacts/historical/metrics.json').read_text())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=['base_whole','base_fractional','stress_whole','stress_fractional']
    x=np.arange(len(cases)); fig,ax=plt.subplots(figsize=(10,4))
    for i,risk in enumerate(['risk05','risk10']):
        pnl=[m['partitions']['final'][risk+'_'+case]['ridge']['net_pnl'] for case in cases]
        bars=ax.bar(x+(i-.5)*.36,pnl,.36,label='5% cap' if i==0 else '10% cap')
        ax.bar_label(bars,fmt='%.0f',padding=3)
    ax.axhline(0,color='black',linewidth=.7)
    ax.set_xticks(x,[c.replace('_',' ') for c in cases]);ax.set_ylabel('Net P/L (USD)')
    ax.set_title('Ridge: $5,000 initial capital, 2024–2026-10-19')
    ax.legend();fig.tight_layout();fig.savefig(ROOT/'artifacts/historical/ridge_comparison.png',dpi=160);plt.close(fig)
    lines=['# V2: $5,000 and percentage risk', '', '**'+m['status']+'**','',
        'All eight final-period Ridge configurations lost money and underperformed their matched trend baseline.',
        'They completed 53–90 trades each, below the required 100-trade evidence gate; hence the formal INCONCLUSIVE label.',
        'This label does not erase the observed negative P/L or the failed economic/drawdown gates.',
        'None of the primary 95% incremental-performance intervals excludes zero.',
        '', '![Ridge comparison](artifacts/historical/ridge_comparison.png)', '',
        'User-approved comparison: 5% per trade / 15% weekly versus 10% per trade / 30% weekly.',
        'Percentages are caps on planned all-in loss, not position notional or guaranteed realized loss.',
        'Trade limits use current marked equity; session and weekly budgets freeze at the respective start.',
        'Cash/no leverage can prevent using the full risk allowance. One new plan per session remains.',
        'This change was made after seeing v1 results. The reused history is exploratory retrospective evidence.',
        'V1 is preserved separately. Signals, model predictions, dates, costs and universe were not retuned.', '',
        '## Final period: 2024–2026-10-19','',
        '| Risk / scenario | Strategy | End equity $ | Net P/L $ | Trades | Max DD % | Weekly loss breaches |',
        '|---|---|---:|---:|---:|---:|---:|']
    for name,values in m['partitions']['final'].items():
        for strategy in ['cash','trend','ridge']:
            v=values[strategy]
            lines.append(f"| {name} | {strategy} | {v['final_equity']:.2f} | {v['net_pnl']:.2f} | {v['completed_trades']} | {100*v['max_drawdown']:.2f} | {v['weekly_breach_count']} |")
    lines+=['','## Actual admitted Ridge risk','',
        '| Scenario | Mean risk $ | Maximum risk $ | Mean risk / equity % | Maximum risk / equity % |',
        '|---|---:|---:|---:|---:|']
    def fmt(x):return 'undefined' if x is None else f'{x:.2f}'
    for name,values in m['partitions']['final'].items():
        a=values['ridge']['admission_risk']; mean=a['mean_fraction_of_current_equity']; mx=a['maximum_fraction_of_current_equity']
        lines.append(f"| {name} | {fmt(a['mean_planned_dollars'])} | {fmt(a['maximum_planned_dollars'])} | {fmt(mean*100 if mean is not None else None)} | {fmt(mx*100 if mx is not None else None)} |")
    lines+=['','## Ridge versus matched trend: uncertainty','',
        '| Scenario | Total increment $ | Annualized increment $ | 95% annual interval $ |',
        '|---|---:|---:|---|']
    for name,values in m['partitions']['final'].items():
        c=values['comparison']; lines.append(f"| {name} | {fmt(c['incremental_pnl'])} | {fmt(c['annualized_incremental_pnl'])} | [{fmt(c['bootstrap_lower'])}, {fmt(c['bootstrap_upper'])}] |")
    for r in ['risk05','risk10']:
        lines+=['',f"![{r} base whole](artifacts/historical/final/{r}_base_whole/equity.png)"]
    ev=software_evidence()
    lines+=['','## Execution evidence and limitations','',
        f"- Current pytest: {ev.get('tests')} tests, {ev.get('failures')} failures/errors, {ev.get('skipped')} skipped.",
        '- Historical: 72 primary portfolios, plus 64 frozen sensitivity portfolios; 24 synthetic portfolios are separate.',
        '- Bootstrap: 10,000 paired weekly moving-block resamples, lengths 2/4/8, seed 20261020; initial capital $5,000.',
        '- Original 2% annual incremental hurdle is $100/year on $5,000. Original 10% maximum drawdown gate remains.',
        '- Absolute floor remains $160 as originally specified; no automatic replacement with $800 or $4,000.',
        '- All data hashes, source URLs and timestamps are retained in data/manifest.json. Frozen prediction hashes are in inputs/manifest.json.',
        '- Opening/fill/exit/close marks are observed; this is not continuous intraday monitoring. Close-detected protective excess queues a next-open exit.',
        '- Gaps can exceed stops and weekly budgets; losses are retained. Assumed dividend payment lag is 30 calendar days.',
        '- Partial fills are unsupported and explicitly rejected. Full fills assume small-order liquidity; daily OHLC does not establish quote order.',
        '- Incremental data/inference API cost $0; platform hosting was not separately metered.',
        '- No broker, real orders, TradingAgents run, prospective results or monitoring service.',
        '- See artifacts/historical/metrics.json for all yearly/asset/cost/rejection results; sensitivity.json for nearby parameters; gates.json for unmet gates.',
        '- Source and results review is documented in REVIEW_V2.md. Setup and rerun commands are in README.md.',
        '- A positive retrospective result alone cannot establish live readiness. Rules were changed after v1 outcomes were known.']
    (ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['synthetic-smoke','historical','report'])
    args=parser.parse_args()
    if args.stage=='report':report();return 0
    cfg=json.loads((ROOT/'frozen_config.json').read_text())
    ledger('v2_run_requested',stage=args.stage)
    compare(cfg,synthetic=args.stage=='synthetic-smoke')
    if args.stage=='historical':report()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
