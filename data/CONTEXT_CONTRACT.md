# Frozen context admission and availability contract

Admission decided 2026-10-21 UTC before candidate performance. One new source
series is admitted: `vix_close_pct`. No credit, yield or macro series is admitted.
The limit was four; source quality and availability, never model performance,
determined this one-series subset. Development dates remain previously inspected.

`data/context.csv` has exactly these columns:

| Column | Meaning |
| --- | --- |
| `date` | Observation date, XNYS session in YYYY-MM-DD, timezone-naive session identifier |
| `available_date` | Strictly the next XNYS session; first allowed decision session |
| `vix_close_pct` | CBOE VIX closing index level, annualized implied volatility in percent; 15.0 means 15%, not 0.15 or 1500 basis points |

The observation grid is 2009-01-02 through 2026-10-19, with 2009 retained as warmup.
There are 4,476 rows, 4,457 nonmissing VIX closes, and 19 terminal missing values.
The final VIX observation is 2026-09-22; its available date is 2026-09-23.
No interior XNYS gaps occur before that observation. The final grid row has
available_date 2026-10-20 and no value. Non-XNYS raw records are excluded from
the grid, with dates reported in `context_audit.json`.

Join decisions **exactly on `available_date`**, checking the observation precedes
the decision. Do not perform an unrestricted as-of join, forward fill, interpolate,
backfill, replace absent values with zero, or carry September VIX into October.
A context-dependent prediction requires all its context fields present. Compute
any predeclared 20-session change on this observation-session grid before joining;
missing lagged/current observations must keep that derived value missing. This
contract supplies one level field, not fitted transformations or model targets.

The next-session lag is a conservative modeling rule for a market-close measure,
not proof of historical mirror publication time. Same-day use is prohibited.
The mirror is a present-day historical snapshot, not a vintage archive; CBOE or
mirror corrections and publication timing cannot be independently certified here.
It supports descriptive research, with that limitation, and is stale for current
paper decisions after 2026-09-23. All later required context must fail closed.

The frozen bytes come from the existing public DataHub/datasets GitHub mirror,
repository `https://github.com/datasets/finance-vix`, revision
`3dbea23c70cc2afbeeec8ac232c9ec72ac26ac21`. Exact immutable raw URLs, retrieval
timestamps, status, ETag, bytes and SHA256 are retained in
`raw/context/20261021T041611Z/retrieval_evidence.json`. The source declaration
points to CBOE's `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`.
This is mirror provenance; direct CBOE contents were not fetched or independently
compared because that host is outside the managed allowlist. Metadata declares
PDDL, while the mirror README acknowledges uncertainty over upstream licensing;
that declaration does not independently establish upstream redistribution rights.

Rebuild offline with `.venv/bin/python data_pipeline.py`. Optional pinned
reacquisition is `.venv/bin/python data/acquire_context.py`; it preserves new
retrieval evidence separately and refuses unexpected hashes. Use the managed
runtime/network procedure before reacquisition. It does not update the frozen
model inputs or replace retained evidence.
