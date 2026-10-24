# V4 original-data audit and newly acquired context

The original three ETF snapshots passed the independent local consistency audit.
The new context is one daily VIX series from an existing public GitHub mirror,
with strictly next-session availability. No model results informed admission.

| Price source | Rows | Period | Missing / duplicates | Dividends / splits |
| --- | ---: | --- | --- | ---: |
| SPY | 4,476 | 2009-01-02–2026-10-19 | 0 / 0 | 71 / 0 |
| QQQ | 4,476 | 2009-01-02–2026-10-19 | 0 / 0 | 74 / 0 |
| GLD | 4,476 | 2009-01-02–2026-10-19 | 0 / 0 | 0 / 0 |

`data/original_manifest.json` and `original_validation.json` retain the v2
manifest and validation byte-for-byte. `data/raw/20261020T180119866454Z/` retains
the complete raw Yahoo JSON, original retrieval evidence and frozen XNYS calendar;
`data/processed/` contains byte-identical original CSVs. SHA256 was verified
against every original raw/processed/calendar/evidence manifest entry. Original
URLs and timestamps remain in that manifest, not reassigned to the v4 copy date.

The audit independently reconstructs OHLCV, reported dividends and split ratios
from raw timestamps in the vendor's exchange timezone, reverses any reported split
adjustment, and compares all seven processed numeric fields at absolute tolerance
1e-7. All fields match. All three match the 4,476-session frozen XNYS calendar,
have finite values and valid OHLC bounds. No prices or labels were filled or
fabricated. The full machine-readable audit is `data/price_audit.json`.

Prices/dividends are USD per share, volume is shares, split ratios are new/old
shares with 1 meaning no reported event. Raw adjusted closes remain raw and are
not executable fill prices. Dividend events are vendor ex-date records, not
verified payment dates. Snapshot reconstruction confirms internal consistency;
it does not certify vendor truth, historical revisions or complete corporate
actions. Any cash-settlement or total-return calculation must retain the original
conservative dividend assumptions. Direct Yahoo refresh is outside the current
managed network allowlist and was not attempted.

The new raw VIX CSV has 9,278 observations from 1990-01-02 through 2026-09-22.
Its frozen SHA256 is
`570e05630c9a5e7350d0c3dbe3acc58e793cb5248181ab0e949c121cc082fb83`.
The mirror commit is `3dbea23c70cc2afbeeec8ac232c9ec72ac26ac21`, resolved via
`git ls-remote` for HEAD/main. Three pinned immutable files were actually
downloaded at 2026-10-21T04:16:11.881669+00:00 through
2026-10-21T04:16:12.733246+00:00: raw CSV, metadata and README. Exact per-file
URLs, timestamps, ETags, content lengths and hashes are retained beside them.

VIX is an annualized implied-volatility percentage derived from options-market
prices. On the 2009–cutoff XNYS grid, 4,457 closes are present, range 9.14–82.69;
there are no interior missing values before 2026-09-22. Source dates are unique;
raw values are finite and raw research-period OHLC bounds pass. Thirty-three raw
dates fall outside XNYS (including holidays); they are explicitly excluded,
preserved in raw data and listed in `data/context_audit.json`. This calendar
alignment does not claim the source's additional dates are invalid CBOE dates.

There are **19 missing observation rows**, dated 2026-09-23 through 2026-10-19.
The last usable decision date is 2026-09-23, one XNYS session after the last
observed close. After that availability shift, there are **18 missing decision
dates within the evaluation calendar**, 2026-09-24 through 2026-10-19. The final
missing observation row would become available on 2026-10-20, outside that
calendar; this explains the different counts. Later context remains missing.

`analysis/model/availability_frozen.json` confirms **zero missing context values
on admissible decisions** in development, validation and final evaluation. The
final period's last admissible decision is 2026-09-21 because a complete
20-session outcome must mature by the data cutoff; thus the missing context tail
removes no admissible decision in this evaluation. Portfolio valuation continues
through the full phase calendar. The exact join and units contract is
`data/CONTEXT_CONTRACT.md`. Context-dependent candidates must abstain when required
features are missing. New feature history does not make previously inspected
periods untouched.

The mirror declares CBOE as its original source, but the official domain is
outside the allowlist, so the CSV was not independently authenticated against
CBOE. The current mirror snapshot is not a historical vintage archive. The
next-session lag is an explicit conservative historical availability assumption,
not certified mirror-release timing. The source is stale for present-day paper
decisions. Mirror PDDL metadata also does not establish upstream license rights;
its README explicitly acknowledges uncertainty. These are research limitations.

The bounded rate search found `datasets/bond-yields-us-10y` explicitly monthly,
which was excluded without forward filling; three obvious daily-yield/fedfund
repository metadata paths were unavailable (404). No suitable established daily
credit mirror was identified, and no revision-prone macro series was admitted.
`data/source_selection.json` records successful/failed probes and policy-restricted
official sources. No policy bypass, paid API or account signup was used.

Reproduce offline: `.venv/bin/python data_pipeline.py`. Verify:
`.venv/bin/python -m pytest -q tests/test_v4_data.py` (12 passed). Tests cover
next-session availability including a weekend, explicit missingness, no future
observation backfill, duplicate dates, percent scale preservation, invalid values,
same-day rejection, complete retained source correspondence, raw/processed audit,
and detection of a deliberately altered processed price. A rebuild on a separate
copy also preserves every data file byte-for-byte, including acquisition evidence,
timestamps, context.csv and the manifest. Data/output SHA256
inventory is `data/manifest.json`; optional pinned reacquisition code is
`data/acquire_context.py`. Original v2 files were only read and remain unchanged.
