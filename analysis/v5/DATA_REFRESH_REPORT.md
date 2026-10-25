# V5 data refresh preflight — 2026-10-25

The new V5 validator is independent of frozen V4 inputs and models. It checks 21 consecutive XNYS sessions of SPY, QQQ and GLD daily bars and the 21 prior VIX observations needed for a 20-session VIX change under the next-session availability rule. It validates the Yahoo symbol, USD currency, New York timezone, array lengths, finite/positive prices, OHLC ordering, volume, split/dividend signs, dates and duplicates. It hashes each input and always reports `actionable: false`; passing inputs alone never approves the rejected C03 model.

The archived Yahoo source probe under `data/raw/20261025_yahoo_probe/` returned HTTP 200 for each ETF and contains daily bars through the last completed XNYS session, **2026-10-23**. The exact request URLs, response statuses, byte counts and hashes are in `retrieval_evidence.json`. A separate short Yahoo query returned HTTP 429, so source availability is intermittent. These were research-source probes; provider terms, historical corrections, and long-term reliability remain to be evaluated before scheduled use.

The official CBOE VIX host returned proxy `CONNECT 403`. The reachable existing GitHub mirror still ends on **2026-09-22**. For an October 23 decision close, 21 prior VIX observations from September 24 through October 22 are absent. The combined validation therefore returns **`REFUSED`** in `probe_validation.json`. No VIX value was invented or carried forward; the existing `paper.py` also remains non-actionable.

Reproduce the current preflight from the project root:

```bash
.venv/bin/python analysis/v5/validate_refresh.py \
  --as-of 2026-10-23 \
  --price-dir analysis/v5/data/raw/20261025_yahoo_probe \
  --vix data/raw/context/20261021T041611Z/vix-daily.csv \
  --output /tmp/v5-preflight.json
```

Exit code 2 is the expected refusal for these real inputs. Four operational tests in `analysis/v5/test_validate_refresh.py` check the archived source hashes, this stale VIX refusal, a **test-only synthetic** complete VIX continuation that exercises validation without becoming research data or an actionable signal, and refusal after removing a price bar. The next prerequisite is a permitted, timely VIX source with complete provenance and a refreshed full lookback; network access to `cdn.cboe.com` has been saved in the cloud environment draft. Draft saving does not apply the change to the running machine. Once the user reviews and publishes it, recheck the official source and use rights, then repeat this preflight with preserved raw bytes before considering any further paper workflow.
