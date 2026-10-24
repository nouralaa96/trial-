# Independent V4 audit — 2026-10-24

**Historical research integrity: PASS, with disclosed protocol and provenance limitations. Economic strategy acceptance: FAIL. No unresolved blocking implementation defect was found in the frozen reviewed artifacts.** This signoff does not approve trading, guarantee returns, establish prospective performance, or certify source data as historical vintages.

Signed role: independent AI research reviewer with modeling, markets and finance scrutiny. The reviewer did not implement or select the strategy, wrote only `review/` files, and is not claiming professional licensure. Design requirements and defects were sent to the manager; corrections were independently checked against exact artifacts. The main strategy remains `REJECTED_RESEARCH`.

## Independent financial result

Same $5,000 account, 2024-01-02 through 2026-10-19, risk05/base/whole. CAGR uses elapsed days/365.25; drawdown includes initial capital. Daily cash/equity curves and trade records, rather than reported summary numbers alone, were independently recomputed.

| Strategy/reference | Ending capital | Net P/L | CAGR | Maximum drawdown | Trades |
|---|---:|---:|---:|---:|---:|
| C03 finalist | $6,493.55 | $1,493.55 | 9.8013% | 13.3999% | 47 |
| T05, same holding horizon | $8,667.94 | $3,667.94 | 21.7531% | 13.2648% | 58 |
| SPY cash-dividend passive | $8,134.20 | $3,134.20 | 19.0162% | 17.7229% | 1 |
| Prior fixed20 price control | $7,449.47 | $2,449.47 | 15.3305% | 13.6585% | 53 |

C03's carried full-calendar-year returns were 18.9329% in 2024 and 19.2425% in 2025. SPY returned 24.1282% and 16.6152%, implying desired five-times targets of 120.6409% and 83.0762%. C03 misses both. Its 2026 partial-year return is −8.4245%, versus SPY +12.3877%; that incomplete year is correctly excluded from the full-year target gate. Nonpositive benchmark years have no return multiple and instead report excess percentage points.

All eight final C03 configurations remain profitable after the specified fees/friction, but none meets the 10% drawdown requirement. Final trade counts range43–47, below100. Incremental value against passive SPY and the same-horizon simple strategy is not demonstrated. The favorable half-risk-ceiling sensitivity remains unselected and cannot replace the failed finalist. Loss-budget admission controls and the inherited $160 capital floor do not enforce a 10% rolling drawdown ceiling; gap losses are retained.

## What was independently verified

- **All168 portfolio outputs:** endpoint dollars, CAGR, drawdown, carried annual returns, cash = settled + unsettled, equity = cash + marked exposure, closed-trade P/L, fees/friction, reservations, whole-share quantities, position limits, next-session orders and recorded admission budgets. No reconciliation errors. Immediate fill-revalidation round trips legitimately have zero holding-counter sessions and are checked separately from normal1–20-session holds.
- **All48 passive reference curves:** rebuilt independently from raw executable SPY bars, costs, rounding, dividends and payout-lag reinvestment. Both references have identical dates/capital and terminal liquidation. The whole-share final curves coincide because distributions cannot fund an additional share; fractional reinvestment differs. These are constructed costed references, not an official reinvested total-return index.
- **172 persisted fits:** independently reconstructed training rows, boundary purge, feature scaling and closed-form Ridge solutions for110 production and62 chronological calibration fits. Every cutoff respects ten full intervening sessions; model maturity and train-only scaling match. Independently coded bracket labels agree across12,325 mature executable labels. All10,218 checked stored forecasts match independent solutions within1.47e−16. Calibration residual quantiles independently match; they are not probabilities of profit.
- **All196 fits and168 portfolios reproduced:** a separate verification run under `review/reproduction/` produced526 byte-identical CSV files, identical metric/gate/calibration JSON, and exact saved-model coefficients. This covers the24 price-control sensitivity fits whose individual logs were not retained.
- **Selection and search history:** independently recalculated the frozen development ranking; C03 has zero passing development scenarios and is only the best-ranked rejected finalist. Its lock precedes validation/final events. The retained failed attempt has exactly the same ranking and selection. No final-result reselection, new candidate, increased risk or changed gate was found.
- **28 uncertainty comparisons and all gates:** independently rebuilt weekly P/L pairing and2/4/8-week circular-block intervals,2,000 draws each. Every stored interval and annual target result matches. These intervals concern annual arithmetic incremental dollars, not CAGR, and do not correct repeated-history selection or establish independent samples.
- **Data/provenance:** all20 data-manifest entries match; all1,579 inventoried original-project files remain unchanged. VIX normalized values exactly match the pinned raw snapshot on observation dates:4,457 observed sessions,19 terminal missing observations. It uses next-session availability and no carry-forward. There are zero missing context values on eligible final entry dates, whose last decision is September21. VIX remains stale for present use.
- **Paper/replay:** independently replayed2024-03-06,2024-03-08 and2026-09-21; account equity exactly matches frozen evaluation. Snapshot validation passes, forecast output excludes future label fields, and no output is actionable. Live/order commands return refusal; current and stale-as-of paper requests refuse. The tool is a retrospective counterfactual with final evaluation gates, not a contemporaneous historical approval record.
- **Tests:** final frozen suite40 passed. Dependency deprecation warnings do not change the result. A first audit run caught an obsolete same-day-availability fixture after validation was strengthened; it was corrected without weakening rejection, then independently rerun.

## Findings and remaining limitations

No open blocker remains for delivering an honest rejected research study. The initial high-severity trend-mask bypass, padded-context freshness error and future outcome fields in replay forecasts were corrected and regression-tested. Optional confidence handling, registry timestamps and stale-context fixture were also corrected. Exact status/evidence is retained in `findings.json`.

**Medium: execution-budget deviation.** The clean study used196 fits/168 portfolios. A retained interrupted attempt completed128 fits/104 portfolios, giving324 fits/272 research-and-retry portfolio executions, plus unlogged interrupted work. This exceeds the charter's literal200-portfolio ceiling. The report discloses that deviation; it must not be described as strict budget compliance. The candidate set remained fixed and failed outputs were preserved. The independent reproduction added196 fits/168 portfolios solely for verification; the direct independent fit solves are additional audit computation, not candidate selection.

**Medium: incomplete sensitivity fit logs.** The24 P01_fullhistory fit/scaler logs were not persisted. Exact full-run reproduction substantially supports the sensitivity result but does not retroactively create those original records. All finalist/primary logs are present. The limitation is confined to a nonselected control and is explicitly disclosed.

**High economic limitation:** neither the five-times annual objective nor incremental model value, drawdown control, minimum sample gate or prospective usefulness is established. Every year2019–2026 has been inspected before; neither new VIX features nor chronological refitting creates an untouched holdout. Overlapping labels, correlated equity assets, common market periods and repeated strategy search limit effective sample size. Cash interest, tax and external operating costs are absent; adding positive costs would reduce returns.

The Yahoo and VIX mirror data are later historical snapshots with possible corrections, not exchange-certified point-in-time archives. The one-session VIX lag is a conservative modeled availability assumption, not proof of each historical publication time. No revised macroeconomic series was admitted. Thirty-day dividend payment lag, daily-bar stop-first ordering, capped fills and full small-order liquidity are disclosed assumptions; real spreads, queue priority, partial fills and exact payment dates are not established. No live-readiness conclusion follows from deterministic ledger correctness.

## Commands and exact evidence

Executed with the isolated Python3.12 environment, bytecode disabled, and reviewer outputs confined to `review/`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/audit_final.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/audit_models.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/audit_gates.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python evaluate.py --run --output review/reproduction
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/audit_paper.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider --basetemp=review/pytest_final --junitxml=review/test-results-final.xml
```

`independent_recomputation.json` contains every recomputed portfolio, benchmark discrepancy, frozen-input match, original-preservation result and exact reviewed source/result SHA256. `model_chronology_recomputation.json`, `gate_recomputation.json`, `data_recomputation.json`, `paper_recomputation.json`, `reproduction_comparison.json` and `test-results-final.xml` contain detailed checks. `integration_hashes.json` binds the final reports, tests and integration files. Temporary synthetic pytest directories were removed after completion; logs and test results remain.

Key reviewed hashes:

| Artifact | SHA256 |
|---|---|
| Frozen registry | b8320d3ec42512d2cfeded25159ec140fb97d7df5d41caedd1a8a1c87d2daebd |
| Final gates | 3b4605d5e8aaae1b6bb4711e6d9988a9333f8a7f3282fddd2942a61fe9ee2a83 |
| Saved finalist model | 6ec246e71e55dcdbb51b74f9527c1947f31dd977cbda015b5e4e847824f7c642 |
| Frozen paper bundle | f9ea45280708959df6b2164b3f94dcda56e9bf89064856cafede92dd4f47db3e |
| Paper implementation | c741281c31b0cffc07dc0fa48043fe49cd46307ef34353a33fece7494982ed1d |
| Execution adapter | eec99994da45dfc10e577c7cda9de54fef0c6de5f226c17fd3653492f61694bf |

The self-inclusive release inventory is generated after these review artifacts are frozen; its final read-only verification is separate from the source/input inventories already checked here. Any material change to the reviewed implementation or result hashes requires renewed verification.
