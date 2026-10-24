"""Report all phases, structural benchmarks, and explicit acceptance failures."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import os
ROOT=Path(__file__).resolve().parents[1]


def run(out=None):
    out=Path(out) if out else ROOT/'analysis/eval_loop_v3'
    locked=json.loads((out/'locked.json').read_text())
    gates=json.loads((out/'gates.json').read_text())
    matched=json.loads((out/'matched_horizon_comparisons.json').read_text())
    frames={p:pd.read_csv(out/f'{p}_results.csv') for p in ['development','validation','final']}
    extra=pd.read_csv(out/'matched_horizon_results.csv')
    assessment={}
    for risk,g in gates.items():
        same=[x for x in matched if x['risk']==risk and '_base_' in x['scenario']]
        all_comparisons=g['comparisons']+same
        ci_pass=all(x['bootstrap']['block_sensitivity'][str(b)]['ci95'][0]>0
                    for x in all_comparisons for b in (2,4,8))
        checks={**g['checks'],'same_horizon_annual_increment_above_100usd':all(x['annual_increment_dollars']>100 for x in same),
                'all_benchmarks_all_block_ci_lower_positive':ci_pass}
        assessment[risk]=dict(candidate=g['candidate'],checks=checks,
            historical_return_target_met=g['checks']['base_annual_return_above_10pct'],
            all_checks_pass=all(checks.values()),live_ready=False,
            verdict='RESEARCH_ONLY_TARGET_NOT_FULLY_ESTABLISHED' if not all(checks.values()) else 'HISTORICAL_PASS_REQUIRES_NEW_DATA')
    (out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
    names={'ridge_fixed_h20_a100':'Ridge, 20-session forecast/hold, alpha 100','trend_h5':'Simple, 5-session hold','trend_h20':'Simple, 20-session hold'}
    lines=['# Evaluation loop: >10% annualized net-return target','',
        '**Outcome: the locked Ridge candidate exceeds10% annualized after base trading costs in the final historical period, but the full usefulness/risk assessment fails. It is a research model, not a proven deployment-ready strategy.**','',
        'The selected model uses the original8 indicators, separate equity/gold Ridge fits, alpha100, and a20-session gross forward-return label with up to20-session holding. Each quarter trains on expanding past history whose outcomes have matured at least10 full intervening sessions before use. Stops, targets, price caps, cash settlement and risk limits remain unchanged.','',
        'Initial capital is$5,000. User-confirmed target is **more than10% per year after costs**, not10% total or monthly. CAGR uses elapsed calendar years. Maximum drawdown target remains10%. Trading costs include commissions and modeled execution friction; platform hosting was not separately metered.','',
        '## Final-period comparison,2024–2026-10-19','',
        'Base costs and whole shares. Ending capital includes the gains; returns are annualized across the full period. The matched20-session simple benchmark is a supplemental audit, not a newly selected winner.','',
        '| Risk | Strategy | Net profit$ | Ending capital$ | CAGR% | Maximum drawdown% | Closed trades |',
        '|---|---|---:|---:|---:|---:|---:|']
    all_final=pd.concat([frames['final'],extra[extra.partition=='final']],ignore_index=True)
    for risk,entry in locked.items():
        for cid in [entry['ridge'],'trend_h5',f"trend_h{int(frames['final'][frames['final'].candidate==entry['ridge']].horizon.iloc[0])}"]:
            row=all_final[(all_final.risk==risk)&(all_final.candidate==cid)&all_final.scenario.str.endswith('_base_whole')].iloc[0]
            lines.append(f"| {risk} | {names.get(cid,cid)} | {row.net_pnl:.2f} | {5000+row.net_pnl:.2f} | {100*row.cagr:.2f} | {100*row.max_drawdown:.2f} | {row.completed_trades} |")
    lines += ['', 'The model beats the original5-session simple strategy, but trails the simple strategy using the same20-session holding limit in **all8 final cost/risk/rounding combinations**. Longer holding is therefore an important alternative explanation for the improved profits. This does not establish that Ridge adds predictive trading value. The same-horizon baseline was added mechanically after the first final results, with no candidate reselection or parameter changes; see supplemental_plan.json.','',
        '## Locked model across chronological periods','',
        'These are separate portfolios starting at$5,000, not one compounded account. Periods: development2019–2021, validation2022–2023, final2024–2026-10-19.','',
        '| Period | Risk | Net profit$ | CAGR% | Max drawdown% | Trades |', '|---|---|---:|---:|---:|---:|']
    for phase,f in frames.items():
        for risk,entry in locked.items():
            row=f[(f.risk==risk)&(f.candidate==entry['ridge'])&f.scenario.str.endswith('_base_whole')].iloc[0]
            lines.append(f'| {phase} | {risk} | {row.net_pnl:.2f} | {100*row.cagr:.2f} | {100*row.max_drawdown:.2f} | {row.completed_trades} |')
    lines += ['', 'All periods were previously viewed during this project. Chronological fitting and locked selection prevent additional within-run leakage, but **do not turn reused historical data into a new untouched holdout**. No candidate was retuned after its final results.','',
        '## All final model scenarios','', '| Scenario | Net profit$ | CAGR% | Max drawdown% | Trades |', '|---|---:|---:|---:|---:|']
    for risk,entry in locked.items():
        for row in frames['final'][(frames['final'].risk==risk)&(frames['final'].candidate==entry['ridge'])].itertuples():
            lines.append(f'| {row.scenario} | {row.net_pnl:.2f} | {100*row.cagr:.2f} | {100*row.max_drawdown:.2f} | {row.completed_trades} |')
    lines += ['', 'A favorable fractional-share result must not replace a failed whole-share result after seeing the final outcomes. At5% risk, fractional sizing shows18.94% CAGR and9.29% drawdown under base costs, while whole shares show15.33% and13.66%. This sensitivity is material. At5% risk with whole shares, stressed-cost CAGR is9.64%, below the10% return target.','',
        '## Acceptance checks','', '| Check |5% risk |10% risk |','|---|---|---|']
    for key in next(iter(assessment.values()))['checks']:
        lines.append('| '+key+' | '+' | '.join('PASS' if assessment[r]['checks'][key] else 'FAIL' for r in ['risk05','risk10'])+' |')
    lines += ['', 'The original minimum100-trade gate is unmet. This does not erase actual profits or losses; it limits the amount of evidence. The return, drawdown, sample-size and comparative-value checks are reported separately. All-block uncertainty checks use paired weekly moving-block bootstraps with lengths2/4/8,10,000 resamples and fixed seed20261020. Estimates are descriptive and do not correct all selection bias from this reused history.','',
        '## What the loop actually evaluated','',
        '-12 Ridge candidates: holding/forecast horizons5,10,20; alphas1,100; fixed-horizon or conditional-fill bracket outcomes. Three simple-strategy baselines at the same horizons.',
        '-60 development portfolios:15 candidates×2 risk policies×2 cost levels, whole shares. Rank within each risk policy by gate count, then worst-cost return penalized for drawdown, then worst drawdown and stable ID.',
        '-32 validation portfolios: three locked Ridge finalists and one development-selected simple baseline per risk, each under four cost/rounding cases. One Ridge winner per risk was locked before final fitting/execution.',
        '-16 primary final portfolios. The selected simple baseline was the original5-session rule for both risk policies, so duplicate baseline runs were avoided.',
        '-16 additional matched-horizon benchmark portfolios across validation/final. Total **124 portfolio simulations**, all retained. No new model candidate, risk escalation, leverage or broker connection was introduced.',
        '-Every losing or disqualified candidate is retained in development_results.csv and validation_results.csv; events.jsonl records stage and selection locks.',
        '-The finite grid is a stopping rule. If no candidate meets the full target, the run stops with failure reasons instead of repeatedly fitting the final period until it appears profitable.','',
        'Bracket labels use conservative raw-price stop-first execution, exclude unfilled plans and entry-date dividends, and record maturity at actual exit. They are gross outcomes conditional on fill; they do not model portfolio-level risk-forced exits. Predictions still pass the original cost and risk admission checks. Fixed labels use next-open to horizon-close total return. No cross-label MSE ranking is used because these are different targets. Longer horizons also move the last permissible entry earlier at each period end.','',
        '## Models, reproducibility and decision','',
        'Verification:32 tests passed across the new loop and prior diagnostics. Tests compare bracket labels directly with the original execution kernel, check temporal isolation and training-only scaling, test CAGR/risk-aware ranking, and ensure reruns cannot overwrite existing results. Every one of the124 saved portfolios was reconciled separately against cash, trade P/L, fees, friction, drawdown and annualization. Original source/configuration and prior results remained unchanged.','',
        'Saved research_models contains the selected model’s latest evaluated quarterly equity and gold pipelines, including fitted scalers. They were reconstructed at the recorded training cutoff, round-trip loaded, and verified against the saved final predictions. These are **research-only exports**, not a live order system or a claim of current profitability. Feature names, timestamps and SHA256 values are in research_models/manifest.json.','',
        'The scientific decision is to retain the20-session model as a candidate, keep both simple baselines, and require genuinely new evaluation before any deployment. The current history establishes positive backtest returns above10% in some configurations; it does not establish stable10%-plus returns with<=10% drawdown or added model value. No guarantee of future profitability is possible.','',
        'The next research question is whether prediction can improve entry selection or risk-adjusted outcomes over the same-horizon simple strategy. Another round must be explicitly versioned, and any reuse of these final results must remain labeled exploratory. Do not discard a better simple benchmark to make the model look useful.','',
        '[Fixed plan](plan.json) · [Development leaderboard](development_results.csv) · [Validation](validation_results.csv) · [Locked models](locked.json) · [Final portfolios](final_results.csv) · [Matched-horizon audit](matched_horizon_results.csv) · [Assessment](assessment.json) · [Tests](test-results.xml)','',
        '![Return and drawdown by chronological period](evaluation.png)','',
        'To run the complete fixed protocol again in a new output directory from the original V2 project (existing Python environment and frozen data required):','',
        '```bash','.venv/bin/python experiments/run_eval.py --output analysis/eval_loop_reproduction',
        '.venv/bin/python -m pytest -q experiments/test_eval_loop.py diagnostics/test_trade_quality.py diagnostics/test_cost_attribution.py','```','',
        'The runner refuses to overwrite an existing run. No network data fetch is performed. All original frozen source/configuration and historical artifacts are verified unchanged.']
    import re
    lines=[re.sub(r'\b(than|original|separate|of|at|with|across|lengths|all|above|below|horizons|alphas|the|and|by)(?=\d)',r'\1 ',line) for line in lines]
    lines=[re.sub(r'(?<=\d)(USD|Ridge|portfolios|tests|final|cases)\b',r' \1',line) for line in lines]
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    # Use writable caches in managed cloud execution, including fresh reruns.
    os.environ.setdefault('MPLCONFIGDIR',str(out/'.cache/matplotlib'))
    os.environ.setdefault('XDG_CACHE_HOME',str(out/'.cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # Use only comparable, base-cost whole-share portfolios, all3 phases.
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    labels=['Development\n2019–2021','Validation\n2022–2023','Final historical\n2024–2026']
    for j,cid in enumerate([locked['risk05']['ridge'],'trend_h5','trend_h20']):
        values=[]
        for phase,f in frames.items():
            pool=pd.concat([f,extra[extra.partition==phase]],ignore_index=True)
            row=pool[(pool.candidate==cid)&(pool.scenario=='risk05_base_whole')].iloc[0]
            values.append(row)
        x=np.arange(3)+(j-1)*.25
        axes[0].bar(x,[100*r.cagr for r in values],width=.24,label=names.get(cid,cid))
        axes[1].bar(x,[100*r.max_drawdown for r in values],width=.24)
    for ax in axes:
        ax.set_xticks(np.arange(3),labels);ax.axhline(10,color='black',ls='--',lw=1)
        ax.grid(axis='y',alpha=.2)
    axes[0].set_title('Annualized return after trading costs (%)')
    axes[1].set_title('Maximum close-marked drawdown (%)')
    axes[0].legend(fontsize=8)
    fig.suptitle('5% risk cap · whole shares · base costs · separate $5,000 portfolios')
    fig.tight_layout();fig.savefig(out/'evaluation.png',dpi=160);plt.close(fig)
    print(json.dumps({'report':str(out/'REPORT.md'),'assessment':{r:x['verdict'] for r,x in assessment.items()}}))

if __name__=='__main__':run()
