# Independent prior-evidence audit

Reviewed 2026-10-21 by independent AI research reviewer. This is an initial evidence review, not the V4 final decision.

`python review/audit_prior.py` independently reconstructs performance from the saved daily equity curves using only the Python standard library. All 35 checked original source and market-data hashes match their frozen manifests. Exact equity hashes and full calculation outputs appear in `prior_independent_metrics.json`.

| Final 2024-01-02 to 2026-10-19 | Ending $ | CAGR | Drawdown |
|---|---:|---:|---:|
| V3 Ridge20, 5% risk/base/whole | 7,449.47 | 15.330% | 13.659% |
| Simple20, same scenario | 8,667.94 | 21.753% | 13.265% |
| SPY executable passive | 8,134.20 | 19.016% | 17.723% |

The independent calculation uses 365.2425 days/year; the original uses 365.25. The negligible rounding difference does not change any conclusion. Initial $5,000 is included in drawdown, and annual returns carry prior year-end equity.

SPY full-year returns are 24.128% in 2024 and 16.615% in 2025, corresponding to desired five-times targets of 120.641% and 83.076%. Ridge returns are 25.093% and 23.599%. In incomplete 2026 through October 19, Ridge loses 3.637% while SPY gains 12.388%. The earlier >10% CAGR outcome is therefore not success under the clarified economic objective.

The passive benchmark buys whole shares, retains residual cash, accumulates cash dividends without reinvestment, and charges entry and exit costs. It includes dividends in economic proceeds, but is not a reinvested total-return index. V4 must use precise naming and avoid implying equivalence.

Original raw data are Yahoo public-chart snapshots retrieved 2026-10-20, with 4,476 sessions per asset from 2009-01-02 to 2026-10-19. The original manifest explicitly discloses possible retrospective revisions, unofficial provenance, unavailable certified point-in-time action history and missing payment dates. None of these properties should be lost when copying the data into V4. A future macro series needs independent release/vintage treatment.

The inherited execution engine separates settled cash from sales/dividend receivables, uses date-dependent T+3/T+2/T+1 settlement, does not spend unsettled cash, credits dividends only to prior holdings, enforces next-session price caps and stop-first daily-bar exits, and reconciles equity to closed/open P&L. Its default dividend payment assumption is 30 calendar days. That is a modeling assumption, not verified payment evidence. Its admission budgets and initial capital floor do not guarantee the desired 10% rolling maximum drawdown, and opening gaps can exceed planned stop risk. The final V4 audit must verify actual exported ledgers rather than rely solely on inherited tests.

No V4 performance acceptance is given at this stage.
