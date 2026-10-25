# V5 plan: prove usefulness before proposing trades

Status: proposal. V4 remains a frozen, rejected research result. This plan authorizes no live orders and changes no V4 model, data, gates, or results.

Progress on 2026-10-25: the Phase 2 accounting diagnosis is in `analysis/v5/ATTRIBUTION_REPORT.md`. The first Phase 1 source preflight is in `analysis/v5/DATA_REFRESH_REPORT.md`: all three staged ETF feeds reach 2026-10-23 and pass recent-bar checks, while VIX is stale, so the combined input status is `REFUSED`. No prospective paper evaluation has started.

## Starting evidence and objective

On the final V4 period (2024-01-02 to 2026-10-19), the $5,000 whole-share C03 Ridge account returned 9.80% CAGR after modeled costs, with 13.40% maximum drawdown and 47 completed trades. The comparable simple trend T05 returned 21.75% CAGR with 13.26% drawdown; costed SPY buy-and-hold returned 19.02% CAGR. C03 did not add value, and the 10% drawdown target failed. All 2019-2026 history has been examined; it cannot serve as untouched evidence for a new model. The VIX snapshot is stale for current decisions. Historical replay works, but the paper tool correctly refuses current actionable signals.

The practical goal is a reproducible research and paper-trading system that makes fresh, cost-aware decisions and demonstrates positive incremental value over both SPY and a simple, **equally constrained** strategy. Five times a positive annual SPY return remains a stretch objective to report, not a criterion to tune toward on known data or a promise of profit. A strategy that cannot beat the simple control after costs should not be deployed just because its forecasts look accurate.

## Phase 1: make the evidence and paper process current

1. Choose a licensed or otherwise permitted daily source for split/dividend-adjusted and executable OHLCV bars, plus a timely volatility series. Record source, retrieval time, exchange calendar, publication/availability time, adjustment convention, and raw hashes. Never fill missing market context forward for a trading decision. Keep historical snapshots immutable and version every refresh.
2. Add a scheduled, **read-only** daily ingest and health check. Reject incomplete sessions, stale features, inconsistent corporate actions, missing symbols, and unexpected price jumps pending review. Recompute forecasts only from data available by that decision close; save a timestamped decision and model/version hash.
3. Reconcile a paper account against the frozen ledger rules: next-session orders, actual planned shares, whole-share cash, fees, slippage, stops, gaps, dividends, and rejected fills. Report planned versus observed execution assumptions. Keep broker access and live orders disabled during this phase.

Deliverable: a reproducible daily paper log with explicit `NO_TRADE` or rejected status when inputs are stale. Gate: at least 30 consecutive scheduled sessions with no silent missing inputs or accounting discrepancies. This is an operational gate, not evidence of trading edge.

## Phase 2: diagnose where returns are lost

Use V4 as a fixed reference; do not retune against its final results. Compare C03, T05, and SPY on identical dates and capital, and compare active strategies under identical position and risk limits. Break each active strategy's net return into market exposure, entry selection, exit timing, fees, spread/slippage, and idle cash. Analyze losing streaks, underwater duration, gaps, stop/target hits, adverse and favorable excursions, time in trade, and prediction deciles by market regime. Count independent calendar periods, not eight correlated risk/cost scenarios as eight independent samples.

Specific decisions from this diagnostic:

- If Ridge improves forecast error but not after-cost portfolio return, keep it as a research feature and prioritize the simpler trading rule.
- If costs erase gross edge, reduce turnover or reject the idea; do not assume zero-cost fills.
- If exposure explains apparent edge, compare against a matched-exposure SPY/T05 control.
- If drawdown comes from opening gaps, treat the 5%/10% per-trade policies as research stress cases. Design a separate, smaller prospective risk policy; stops alone cannot guarantee a 10% drawdown cap.

Deliverable: one attribution report with a trade ledger and paired daily incremental equity curves. Gate: findings must reconcile exactly to total net P/L.

## Phase 3: bounded new research

Write and timestamp a new charter **before** looking at candidate results. Use an auditable liquid universe beyond three correlated ETFs, for example broad US equity, international equity, Treasuries, gold, and a limited number of sector ETFs, subject to data quality, realistic whole-share affordability, and documented liquidity. More rows of the same market regime are not independent evidence; prefer longer, varied regimes and fresh forward observations. Avoid survivorship bias when changing the universe.

Predeclare at most three mechanisms, each with a matched simple control and one primary risk/cost scenario: (A) a trend/volatility rule with explicit position sizing; (B) a price-only Ridge forecast; (C) Ridge plus a genuinely timely volatility feature. Treat entry thresholds, horizon, and exits as part of the hypothesis budget. Use chronological walk-forward training, matured labels, embargo, train-only transforms, and per-fit provenance. Reserve one historical development period for model choice; report all previously viewed periods as exploratory. Do not repeatedly promote the best variant on known data.

At $5,000, model whole shares, all fees, spreads/slippage, dividends, cash, and stress fills. Rejected or unfilled orders remain in the ledger. Report return, maximum drawdown, turnover, exposure, completed trades, expected shortfall, longest losing streak, and paired incremental dollars versus controls. Include uncertainty intervals across time blocks and a multiple-search sensitivity; do not treat those intervals as proof of a future edge.

Research gate: a candidate must exceed **both** constrained T05 and costed SPY after base and stressed costs, maintain maximum drawdown at or below 10% in the evaluated scenarios, and have a positive lower bound for the predeclared paired incremental-return interval. Otherwise retain the simplest control or no-trade result. The 5x-SPY annual target is reported separately; it cannot waive any safety or evidence gate.

## Phase 4: prospective paper evaluation

Freeze the candidate, source contract, risk policy, and evaluation code before the first new paper decision. Record every scheduled session, including no-trade and failed-data days. Evaluate on future observations that were not available during V4/V5 selection. Use a minimum of 6 calendar months for an initial operational/economic checkpoint and 12 months or enough independent trades/regimes for a stronger decision; a 20-session strategy with three positions may need much longer to reach 100 completed trades. Do not quietly change models after a disappointing month: any change starts a separately labeled paper cohort.

Promotion gate: operational checks pass; net return after measured execution costs beats both matched controls; maximum drawdown stays within the declared limit; paired incremental uncertainty supports a positive edge; enough independent observations exist to make that estimate meaningful. An unfavorable or inconclusive result means continued research or no-trade. A one-year win does not guarantee future returns.

## Phase 5: only if paper gates pass

Before any real order, obtain explicit user approval of the broker, instrument universe, capital, loss limits, and order workflow. Start with a small, separately monitored allocation and a materially lower per-trade risk than the V4 5%/10% research cases. Require hard account-level stop/kill-switch rules, daily reconciliation, alerts for stale data and unexpected fills, and a documented rollback. No automatic increase in size after early wins.

## Work order and stopping rules

Execute Phase 1 and the V4 attribution in Phase 2 first. They make the system useful as an honest paper research tool even if no profitable model emerges. Start Phase 3 only after the attribution identifies a testable economic mechanism and reliable fresh data. Stop expanding the search when the predeclared budget is exhausted. Stop paper decisions whenever data or account state is stale or inconsistent. Archive every rejected candidate and every correction attempt.

The next implementation task is Phase 2's reconciled return attribution, alongside selection of a fresh data source for Phase 1. No new model fit is needed to answer the first diagnostic question.
