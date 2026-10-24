# Independent review contract

Reviewer role: independent AI research reviewer, with modeling, markets and finance scrutiny. This is not a claim of professional licensure. The reviewer is separate from implementation and candidate selection and writes only review/ artifacts. No real orders are authorized.

The research objective is approximately five times SPY's positive annual buy-and-hold return after modeled costs, with an initial $5,000 cash account and maximum drawdown target 10%. A 10% SPY year implies a 50% strategy target; 10% strategy CAGR alone is not success. Evaluate full calendar years individually; report incomplete years separately. For nonpositive or near-zero market years, report excess percentage points and downside behavior rather than unstable return multiples. Also report full-window CAGR, absolute dollars and matched-date SPY total-return evidence. The specified 5%/15% and 10%/30% trade/session/weekly limits do not mathematically guarantee a 10% peak-to-trough drawdown ceiling.

## Evidence required

1. Frozen finite search plan, complete unsuccessful-trial ledger, pre-final candidate lock, and no performance-driven reselection after final results. Reused 2019–2026 data must remain exploratory; additional features or sources do not restore untouched-holdout status.
2. Source URLs, retrieval timestamps, raw-file hashes, processing rules, raw executable prices and explicit splits/dividends. Retrospective vendor corrections and unavailable dividend payment dates must be disclosed. Macro data need actual release availability and vintage/revision treatment; a long lag alone does not turn revised historical data into vintage data.
3. Features use information available before the order decision; fit/scaling/imputation use training data only; labels mature before fit with documented purge and embargo; overlapping labels and serial/cross-asset dependence enter uncertainty interpretation. Temporal mutation tests should preserve earlier features, fits and predictions.
4. Same-date, same-capital, cost-aware SPY passive reference including dividends; cash and matched-horizon simple active baselines; carried calendar returns rather than hidden annual resets. Costs and rounding remain explicit. A frictionless total-return reference can supplement the executable reference if clearly identified.
5. Independently recomputed endpoint dollars, CAGR, drawdown including initial capital, annual returns, risk/cash/trade reconciliation and target outcomes. Report every risk/cost/rounding sensitivity without cherry-picking.
6. Executable next-session chronology, conservative daily-bar stop/target ambiguity, opening gaps, fee/spread/slippage assumptions, dividends, settlement and unavailable cash; at most three positions, two daily candidates and one new entry per day. No leverage or negative available cash.
7. Complete deterministic reproduction instructions, environment/dependency details and source/result hashes. Independent checks use read-only source imports with bytecode/cache writes disabled or confined to review/.
8. Research/paper outputs must distinguish signals from approved orders, reject stale or incomplete data, carry exact model/data timestamps, and reveal all execution/risk assumptions. No implied live readiness.

## Decision rules

A material causality, accounting, benchmark or reproducibility defect blocks scientific acceptance until corrected and rerun without performance-driven model changes. Correctly reported failure of the economic objective can pass research-artifact integrity review while the strategy objective remains FAIL. Performance evidence is assessed separately from software integrity. Review approval never authorizes live trading or promises future returns.

Prior evidence already reviewed: V3 REPORT.md, market_benchmark/REPORT.md, original data manifest and source manifest, and raw-feature/execution implementation. V3's 15.33% CAGR and 13.66% drawdown at base whole-share 5% risk are below the simple matched-horizon 21.75% CAGR and passive SPY 19.02% CAGR; model utility and the new 5× target were not established.
