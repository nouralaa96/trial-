"""Render the manager report from completed frozen results; performs no fitting."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'analysis/model'

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,row))+' |' for row in rows])

def main():
    final=pd.read_csv(MODEL/'final_results.csv')
    dev=pd.read_csv(MODEL/'development_results.csv')
    gates=json.loads((MODEL/'final_gates.json').read_text())
    cid=gates['candidate']
    focus=final[final.scenario.eq('risk05_base_whole')]
    metric_table=table(['Research strategy / reference','CAGR','Net P/L','Maximum DD','Trades'],[
        [r.candidate,f'{r.cagr:.2%}',f'${r.net_pnl:,.2f}',f'{r.max_drawdown:.2%}',r.completed_trades]
        for r in focus.itertuples()])
    policy_table=table(['C03 scenario','CAGR','Net P/L','Maximum DD','Trades'],[
        [r.scenario,f'{r.cagr:.2%}',f'${r.net_pnl:,.2f}',f'{r.max_drawdown:.2%}',r.completed_trades]
        for r in final[final.candidate.eq(cid)].itertuples()])
    annual=table(['Year','C03 return','SPY reference','C03 / positive SPY','5× target'],[
        [str(r['year'])+(' YTD through Oct19' if r['partial'] else ''),f"{r['strategy_return']:.2%}",
         f"{r['spy_total_return']:.2%}",f"{r['positive_market_multiple']:.3f}×" if r['positive_market_multiple'] is not None else 'not defined',
         'not a full-year gate' if r['partial'] else f"{5*r['spy_total_return']:.2%}" if r['spy_total_return']>0 else 'excess percentage points only']
        for r in gates['annual_market_targets'] if r['scenario']=='risk05_base_whole'])
    failed=table(['Acceptance gate','Result'],[[k,'PASS' if v else 'FAIL'] for k,v in gates['checks'].items()])
    development=table(['Candidate','Development CAGR','Maximum DD','Trades'],[
        [r.candidate,f'{r.cagr:.2%}',f'{r.max_drawdown:.2%}',r.completed_trades]
        for r in dev[(dev.scenario=='risk05_base_whole')&dev.candidate.isin(['P01','P02','C03','C04','T05','T06'])].itertuples()])
    report=f'''# V4 result: rejected research strategy

V4 did not produce a strategy that meets the user's goal or is ready to trade. C03, the development-selected Ridge model using executable bracket-return targets plus newly acquired lagged VIX context, returned **9.80% CAGR after modeled costs**, with **13.40% maximum drawdown** and **47 completed trades** in the primary $5,000 whole-share account over 2024-01-02–2026-10-19. The same-horizon simple strategy returned 21.75% CAGR and SPY cash-dividend buy-and-hold returned 19.02%. The retained model is marked `REJECTED_RESEARCH`; no real orders were placed and no broker is connected.

## What was implemented

The three Sol workstreams, managed by Astra, acquired and audited a new VIX context series, implemented six fixed hypotheses and temporal calibration, and delivered a local paper/replay tool. The charter, ownership contracts and registry preceded performance inspection. Candidates were P01 price-only fixed20 Ridge; P02 price-only executable bracket20 Ridge; C03 bracket20 plus VIX level and 20-session change; C04 C03 with a chronological residual-scale entry threshold; T05 simple trend20; T06 trend20 plus VIX≤30. Alpha=100 and holding horizon=20 were fixed. Separate equity/gold models use expanding 2010 onward training, quarterly refits, train-only scaling, matured labels and ten full-session embargoes. Calibration uses a separate chronological historical tail with its own fit embargo.

Selection used 2019–2021 only and compared all eight risk/cost/share scenarios against the maximum of SPY cash-dividend, costed SPY reinvestment and T05. **Every model had zero passing development scenarios.** C03 was only the best-ranked rejected research finalist; its worst penalized increment was −26.45 percentage points. Validation 2022–2023 could reject but did not replace it. Final 2024–2026 results were descriptive only. All 2019 onward history had already been inspected in earlier research, so neither new features nor this split create untouched evidence.

{development}

C04 completed zero development trades: its uncertainty filter removed the available opportunities. The bracket target alone did not improve the price-only control. C03's development rank did not translate into final economic usefulness. Full candidate failures, quarterly fold distributions and forecast diagnostics remain in `analysis/model/`; see `MODEL_REPORT.md` there for details.

## Final comparison and feasibility

Primary scenario is risk05/base/whole; all rows use the same final calendar. CAGR uses elapsed calendar time, not mean trade return.

{metric_table}

`P01_fullhistory` reproduces the prior fixed20 control. T05 with and without the common context mask is identical because all admissible entry dates have context. The no-trend ablation and half-risk-ceiling sensitivity were predeclared and are never selected as replacements. Half-risk ceilings halve trade/session sizing ceilings, not shares mechanically: cash affordability and the entry path also affect final exposure. Its 15.33% CAGR and 9.12% drawdown still trail both primary benchmarks; this does not rescue the five-times objective.

SPY cash-dividend buy-and-hold includes paid and accrued dividends without reinvestment. The separate SPY reinvestment reference uses assumed payment 30 calendar days after ex-date, costs and whole/fractional constraints; it is a constructed executable reference, **not an official reinvested total-return index**. Whole-share dividend cash in this $5,000 final account never funds an additional share, so both whole-share SPY curves coincide. The fractional reference reinvests and differs. All benchmark assumptions and full eight-scenario results are retained.

SPY passive invests most capital and has much less turnover; its final primary mean marked exposure is 94.30%, versus C03 70.87% and T05 72.63%. C03 therefore trails the simple baseline despite similar exposure. Benchmarks are opportunity-cost references, not promises to obey the active strategy's loss budgets or 10% drawdown target. Whole-share capital granularity matters at $5,000; fractional fills depend on broker support that has not been established. Daily OHLC data and small ETF order sizes are not verified live quotes, spread/liquidity or partial-fill guarantees.

{annual}

The 2024 and 2025 five-times goals required approximately **+120.64% and +83.08%** for this whole-share SPY reference. C03 delivered +18.93% and +19.24%; 2026 is incomplete and excluded from the full-calendar-year gate. Positive-market multiples are arithmetic annual-return ratios, not wealth multiples. For nonpositive SPY years the machine-readable comparisons use excess percentage points with no multiple. These observations do not establish that the target is mathematically impossible; they show it is far beyond the results of this bounded, unleveraged ETF study. Neither leverage nor higher risk was introduced to close that gap.

## Risk, costs and stability

Original policies remain 5% trade/session with 15% weekly, and 10% with 30% weekly. Cash-only, no leverage, maximum three positions, two considered candidates and one new entry per session remain enforced. These sizing/admission ceilings do not guarantee a 10% rolling drawdown; opening gaps may exceed planned stop losses. The inherited $160 capital floor is not a 10% peak-to-trough guard.

{policy_table}

Primary C03 spent 182 consecutive marked sessions below its prior equity high at worst, had a longest completed-trade loss streak of four, and incurred $102.46 fees plus $256.77 modeled fill friction. Gross buy-plus-sell turnover was 88.00 times mean marked equity over the complete final period. Stress doubles each-side fees from $1.09 to $2.18 and slippage from 5 to 10 basis points. Every final scenario remains profitable but every maximum drawdown exceeds 10%; completed trades range from 43 to 47, below the predeclared 100 minimum. Cash earns zero interest; taxes, data subscriptions and external operating costs are not estimated.

## Exact acceptance outcome and uncertainty

{failed}

For risk05/base/whole, annualized arithmetic incremental P/L versus SPY is −$580.36; the four-week paired-block exploratory 95% interval is [−$1,467.88, +$303.32]. Versus T05 it is −$769.17 with interval [−$2,033.34, +$291.87]. These are annualized incremental dollar intervals on the initial $5,000 basis, not CAGR intervals. Two-, four- and eight-week block results, 2,000 draws each, are in `final_gates.json`. Intervals do not demonstrate positive incremental value, and selection on repeatedly viewed history further limits inference. Residual confidence is a diagnostic, not a calibrated probability of profit or guarantee.

## Data provenance and availability

The original three ETF snapshots each contain 4,476 sessions and were copied and independently reconstructed from raw Yahoo data with hashes and action/calendar checks. The genuinely new VIX dataset was obtained from an existing public GitHub mirror pinned to commit `3dbea23c70cc2afbeeec8ac232c9ec72ac26ac21`; raw SHA256 is `570e05630c9a5e7350d0c3dbe3acc58e793cb5248181ab0e949c121cc082fb83`. Source metadata identifies CBOE. Exact URLs, retrieval timestamps, units, original bytes and availability rules are preserved. This is a later mirror snapshot, not independent proof of every historical publication vintage; no revision-prone macro series is admitted as vintage-safe evidence. A monthly yield source was excluded and bounded daily rate/credit alternatives were unavailable. No account signup, paid API or policy bypass was used.

VIX has 4,457 admitted XNYS observations, ending 2026-09-22 and usable next session on 2026-09-23. Thirty-three non-XNYS source dates are explicitly excluded. There are 19 missing terminal observation rows and 18 missing decision-available context rows through 2026-10-19. **There are zero missing context rows among actual eligible entry dates**: the 20-session completion rule ends final entry decisions on 2026-09-21 (672 eligible sessions). Thus terminal staleness does not explain the backtest outcome. It does make this snapshot unsuitable for current paper decisions; missing values are not forward-filled.

## Reproducibility, corrections and useful retained work

The valid frozen run completed **196 fits and 168 unique predeclared portfolio evaluations**. Retained failed attempts include an initial date-ambiguity error before a completed portfolio and a week-key bootstrap mismatch after 128 completed fits and 104 portfolio outputs. Total completed computation including retries is therefore **324 fits and 272 portfolio runs**, plus any unlogged interrupted attempted work. The retry-inclusive portfolio count exceeds the charter's 200-run ceiling; this is explicitly disclosed as an execution-budget deviation. The scientific candidate/scenario set stayed fixed, and there was no outcome-driven candidate addition, reselection or weakened gate. Failed attempts remain under `analysis/failed_runs/`; correction records and independent review identify the technical defects.

Independent review reconstructed all 168 portfolio ledgers and all 48 passive reference curves, verified the development ranking and original-project preservation, and reproduced the frozen study into a separate directory. That additional audit rerun performed 196 fits and 168 portfolios; all 526 portfolio/prediction CSVs were byte-identical and metrics, gates, calibration and model coefficients matched. These audit computations are separate from the research/retry totals above; they are verification, not new candidate selection. The reviewer also directly re-solved persisted fit records. See `review/FINAL_REVIEW.md` for exact evidence and limitations.

The primary-model audit independently checks 110 persisted production fit records and 62 calibration records. The 24 P01 full-history sensitivity fits are included in the 196 count but their per-fit scaler logs were not persisted; this audit limitation is explicit in `analysis/model/causal_audit.json`. All primary/finalist fit records are retained.

The retained value is an audited data snapshot, reproducible causal modeling and comparison code, complete failures and uncertainty, and a usable **historical counterfactual replay** with account state, entry/exit rationale and provenance validation. Rejected gates prevent actionable paper recommendations. Live/order modes always refuse, and stale/missing inputs fail closed. The serialized research pipeline is retained for reproducibility, not as an approved profitable deployment. Commands, test results, demonstrations and independent review are linked from `README.md`; full source/output hashes are in `artifacts/full_manifest.json`.

This iteration is complete. A future research claim needs genuinely new prospective data and an explicit new experiment charter; these results do not justify trading C03 or increasing risk.
'''
    (ROOT/'REPORT.md').write_text(report)

if __name__=='__main__':main()
