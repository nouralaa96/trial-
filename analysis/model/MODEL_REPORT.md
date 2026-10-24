# V4 model and causal-validation findings

C03 is a **rejected research artifact**. It ranked first using development only, with **0 of 8** development scenarios meeting the joint benchmark/drawdown condition. Validation could reject it and did; no replacement or parameter rescue followed. All history from 2019 onward had already been inspected. Final results are descriptive reused-history evidence.

## Frozen candidate results

| Candidate | Development CAGR range | Maximum DD range | Completed trades range | Interpretation |
|---|---:|---:|---:|---|
| P01 | 6.21%–12.66% | 8.17%–13.46% | 44–55 | Price-only fixed 20 control |
| P02 | 2.78%–7.03% | 12.68%–21.22% | 43–53 | Price-only bracket 20 alignment |
| C03 | 7.27%–9.77% | 11.59%–14.41% | 48–55 | Bracket20 plus lagged VIX level/change |
| C04 | 0.00%–0.00% | -0.00%–-0.00% | 0–0 | C03 with temporal residual confidence entry rule |
| T05 | 0.67%–6.46% | 20.82%–29.52% | 47–58 | Simple trend 20 comparator |
| T06 | 2.30%–4.16% | 21.64%–23.45% | 44–49 | Trend20 plus VIX<=30 filter |

P02 did not improve the economic outcome over fixed 20 P01 across these scenarios. Adding VIX improved C03 relative to bracket 20 P02 in all eight development CAGR comparisons, but did not establish value over passive SPY or pass the 10% drawdown gate. Every candidate and failed quarterly return is retained; comparison is a bounded retrospective association, not proof that VIX caused an edge.

## Fold distributions and selection chronology

| Phase, C03 | Quarter/scenario observations | Positive | Quarter return minimum / median / maximum | CAGR across 8 scenarios | DD across 8 scenarios |
|---|---:|---:|---:|---:|---:|
| development | 96 | 56 | -4.36% / 1.38% / 15.17% | 7.27%–9.77% | 11.59%–14.41% |
| validation | 64 | 34 | -5.20% / 0.76% / 13.81% | 12.08%–16.81% | 10.81%–11.51% |
| final | 96 | 60 | -12.68% / 2.95% / 10.85% | 8.47%–10.08% | 13.20%–14.70% |

These rows repeat correlated market quarters across risk/cost/share scenarios and are not independent samples. The lock file precedes validation and final fit events. Development ranking was C03, C04, P01, P02; all had zero passing scenarios. The frozen worst-scenario criterion retained C03 despite that failure.

## Confidence and entry/exposure ablations

C04 used C03 forecasts minus the median absolute residual from a separate chronological 252-session calibration tail. Each calibration model used matured labels with 10 full sessions before its first tail decision. The statistic is not a calibrated success probability or a distribution-free confidence guarantee. C04 made **zero completed development trades** in all 8 scenarios. Its zero drawdown reflects zero exposure and cannot establish economic usefulness.

| C03 group/phase | Mature forecast labels | Median absolute error | Realized lower-bound coverage | Positive lower forecasts |
|---|---:|---:|---:|---:|
| equity / development | 1341 | 2.81% | 85.68% | 2 |
| gold / development | 656 | 2.25% | 74.85% | 1 |
| equity / validation | 887 | 4.08% | 67.64% | 41 |
| gold / validation | 439 | 2.23% | 77.68% | 0 |
| equity / final | 1239 | 2.47% | 76.35% | 3 |
| gold / final | 554 | 3.05% | 76.53% | 0 |

Final and validation confidence diagnostics describe the locked C03 model; C04 was rejected on development and was not reintroduced as a selectable strategy. Tail-label diagnostics condition on executable/mature bracket labels and differ from actual portfolio admissions.

| Final 5% base whole-share case | Net P/L | CAGR | Max DD | Trades | Mean marked exposure/equity |
|---|---:|---:|---:|---:|---:|
| C03 | $1,493.55 | 9.80% | 13.40% | 47 | 70.87% |
| T05 | $3,667.94 | 21.75% | 13.26% | 58 | 72.63% |
| T06 | $2,493.79 | 15.58% | 12.99% | 71 | 70.66% |
| SPY_cash_dividend | $3,134.20 | 19.02% | 17.72% | 1 | 94.30% |
| SPY_reinvested_total_return | $3,134.20 | 19.02% | 17.72% | 1 | 94.30% |
| P01_fullhistory | $2,449.47 | 15.33% | 13.66% | 53 | 73.22% |
| T05_fullhistory | $3,667.94 | 21.75% | 13.26% | 58 | 72.63% |
| C03_no_trend | $1,777.99 | 11.50% | 12.50% | 78 | 77.39% |
| C03_half_risk_ceilings | $2,449.97 | 15.33% | 9.12% | 65 | 68.39% |

The VIX trend filter T06 lowered mean exposure relative to T05, yet produced a lower final CAGR than T05 in 7 of 8 scenarios (the 5% stressed whole-share case improved by 2.92 percentage points). Removing the inherited trend filter from C03 increased 5% base whole-share exposure and trades and slightly improved CAGR, but remained below T05 and SPY and exceeded 10% drawdown. Across other cases, this ablation sometimes worsened drawdown substantially (maximum 25.98%). The predeclared half-risk-ceilings sensitivity improved the displayed5% case but is unselected, changed the cash/risk path, and does not guarantee shares or exposure are halved; some other sensitivity scenarios still exceeded 10% DD.

## Final gates and market-year objective

| Gate | Final result |
|---|---|
| base_profitable | PASS |
| stress_profitable | PASS |
| base_drawdown_at_most_10pct | FAIL |
| stress_drawdown_at_most_10pct | FAIL |
| minimum_100_completed_trades | FAIL |
| positive_increment_over_both_baselines_each_base_scenario | FAIL |
| exploratory_paired_CI_lower_positive_all_block_lengths | FAIL |
| five_times_positive_SPY_full_calendar_years | FAIL |

C03 final completed 43–47 trades per primary scenario, below 100. SPY cash-dividend and after-cost dividend-reinvested references are separately named; whole-share reinvestment can make no purchases when each payout cannot buy a share, so the two whole-share paths can coincide. The reinvested series uses an assumed 30-day payout lag and is an investable approximation, not a published total-return index.

| 5% base whole-share calendar period | C03 | SPY reinvested | Multiple if SPY positive | 5x gate |
|---|---:|---:|---:|---|
| 2024 | 18.93% | 24.13% | 0.78 | FAIL |
| 2025 | 19.24% | 16.62% | 1.16 | FAIL |
| 2026 partial YTD | -8.42% | 12.39% | -0.68 | excluded partial |

Paired weekly block-bootstrap comparisons retain 2/4/8-week block sensitivity and 2000 resamples each. Their lower 95% bounds did not establish positive increment against both baselines. They remain exploratory after repeated historical inspection and candidate selection.

## Causal and availability audit

Exact available-date VIX joins exclude missing observations; no context value is carried past its observed availability. The context feature window spans 2009-02-03–2026-09-23. Eighteen terminal valuation sessions have missing derived decision context, while the source has19 terminal missing observation rows. The 20-session outcome runway already ends final eligibility on2026-09-21, so missing terminal VIX removed **zero eligible entry dates** in all phases. T05 and T05_fullhistory final equity paths are identical; terminal missingness does not explain final underperformance.

| Phase | Eligible first / last decision | Eligible sessions | Missing context among eligible |
|---|---|---:|---:|
| development | 2019-01-16 / 2021-12-02 | 727 | 0 |
| validation | 2022-01-18 / 2023-11-30 | 471 | 0 |
| final | 2024-01-17 / 2026-09-21 | 672 | 0 |

The persisted audit verifies 110 production fit records and 62 temporal-calibration fit records: every recorded maturity cutoff precedes use by 10 full sessions; all scaler parameters are finite. Scaling is fitted inside each training pipeline. The additional 24 P01_fullhistory sensitivity fits are counted in the ledger but their scaler/fit logs were discarded by that sensitivity branch; this limits persisted audit coverage for that control only. Prefix invariance, future-extreme scaling, maturity/boundary purge, stop ambiguity, missing cap fill, confidence masking, calibration embargo and selection chronology tests pass (10 tests). See causal_audit.json.

## Reproduction and retained failures

The valid completed run used **196 fits and 168 portfolio evaluations**, within its frozen 1000/200 limits. Before correction, an initial date-index ambiguity failed before any completed logged fit/run; a retained week-key mismatch attempt completed 128 logged fits and 104 portfolios before bootstrap failed. Across correction attempts, physical completed work is therefore **324 logged fits and272 portfolio evaluations**, rather than 168 total. The invalid attempts remain under analysis/failed_runs, with defects recorded by management; no additional candidate or retuning was introduced. The physical portfolio total exceeds the charter budget when correction reruns are included.

Run `.venv/bin/python -m pytest -q tests/test_v4_model.py` for causal checks. `evaluate.py --run --output /tmp/v4-reproduction-unique` accepts a fresh nonexistent output directory, copies the frozen registry byte-for-byte, and isolates rerun models/predictions beneath that output. An existing output directory is refused before fitting, verified without changing primary files. The full fresh rerun was not executed again, avoiding an additional experiment; code-path support was reviewed.
