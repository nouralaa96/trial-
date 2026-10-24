# V4 cash-account research and paper replay

This project is an exploratory strategy study, with local paper replay only. It has no broker connection and cannot place real orders. A five-times positive annual SPY return is an acceptance target, not an expected return or promise. The 10% drawdown threshold is a target and evaluation gate; the trade/session/week risk limits do not guarantee it.

**Result: C03 is rejected.** Primary final CAGR is 9.80%, maximum drawdown 13.40%, and 47 trades; SPY returned 19.02% CAGR and the same-horizon simple strategy 21.75%. The annual five-times goal, drawdown, sample size and benchmark-increment gates failed.

Read `REPORT.md` for the result, `CHARTER.md` for the rules frozen before experiments, and `analysis/model/registry.json` for the exact six-candidate search. All 2019–2026 evaluation history was previously inspected; these results are not independent prospective evidence.

## Environment

Python 3.12 was used. The isolated environment included in the working directory is disposable and excluded from delivery manifests. Install the pinned dependencies in your own environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pytest tests -q
```

No credentials, account signup or paid APIs are required. The raw data snapshot is included; evaluation does not need network access. Data refresh is a separate explicit action and must preserve its new acquisition provenance.

## Inspect and reproduce

From this directory:

```bash
.venv/bin/python reproduce.py --check-only
.venv/bin/python paper.py status
.venv/bin/python paper.py replay --date 2024-03-08 --snapshot-out /tmp/v4-account.json
.venv/bin/python paper.py replay --date 2024-03-08 --snapshot /tmp/v4-account.json
```

Replay reconstructs the carried historical account from the frozen evaluation start; it returns cash, open positions, forecasts known by the chosen close, entry plans and exits. Its status is `REJECTED_RESEARCH_COUNTERFACTUAL`, and `actionable` is always false. Future outcome labels are excluded. The snapshot is a consistency check for that reconstructed account, not an arbitrary live brokerage account import. This rejected strategy refuses actionable paper use, while `live` and `order` always refuse. `paper --as-of` requires a current timezone-aware timestamp and complete fresh inputs; the included October 19 ETF / September 22 VIX snapshot is stale today.

To reproduce the exact frozen scientific experiment, choose a fresh **external** output directory:

```bash
.venv/bin/python reproduce.py --output /tmp/v4-fresh-reproduction
```

This repeats the fixed six-candidate study with no new search or retuning and preserves the supplied outputs. Existing destinations are refused. It adds computation beyond the original research run; see `REPORT.md` for the distinction between the valid 168-portfolio/196-fit run and defect retries. Verification and tests do not refit. The standalone evaluator is also available as `evaluate.py --run --output PATH`. `build_report.py` renders the manager report from existing results without fitting; changing any delivered file requires intentionally regenerating the manifest afterward.

## Evidence and limitations

- `data/` contains original ETF data copies, the newly acquired VIX mirror snapshot, source URLs, hashes, timestamps, units, and availability rules. VIX observation dates end on 2026-09-22. It is stale for present paper operation; missing context is never forward-filled.
- `legacy/` contains the preserved prior cash ledger and reference implementation. The new adapter drives the ledger locally; it does not call a broker.
- `analysis/model/` holds frozen registry, complete candidate/fold/scenario results, selection lock, model diagnostics, benchmarks, sensitivity tests, and acceptance gates.
- `analysis/DATA_REPORT.md` and `analysis/EXECUTION_REPORT.md` explain provenance and executable assumptions. Dividend cash is distinguished from reinvestment. Cash earns zero interest; taxes and any external operating costs are not estimated.
- `artifacts/models/` holds serialized local research pipelines. Load only trusted local artifacts; they are not an approved trading deployment.
- `review/` is the independent review, separate from candidate selection. `oversight/` contains original-project preservation checks.

The starting account is $5,000, cash-only with no leverage. Both original policies are retained: 5% trade/session and 15% weekly, or 10% trade/session and 30% weekly. At most three positions, two considered candidates per session, and one new entry per session are allowed. Whole shares are the primary practical account reference; fractional shares require broker support that is not assumed available. Historical daily bars do not establish real-time liquidity or executable spread quotes.

Run `python manifest.py --verify` to check the complete source/output inventory. The manifest excludes itself, virtual environments, caches, temporary pytest fixtures and archives. The original V2 hash inventory is verified when that original location is present. See [REPORT.md](REPORT.md), [model diagnostics](analysis/model/MODEL_REPORT.md), [data report](analysis/DATA_REPORT.md), and [execution report](analysis/EXECUTION_REPORT.md) for interpretation and limitations.

Frozen demonstrations are in [artifacts/paper_demo](artifacts/paper_demo/commands.json): March 8, 2024 shows a QQQ entry plan and March 6 shows an actual historical GLD exit. Snapshot roundtrip, exact equity parity, current/stale-input refusal, and unsupported live/order refusal are saved alongside their commands.

Final verification: **40 tests passed** (12 data, 10 model, 18 execution/paper). The inherited Backtrader parity test emits datetime.utcnow deprecation warnings. [Independent review](review/FINAL_REVIEW.md) rebuilt all 168 ledgers and 48 passive curves and reproduced 526 CSV outputs exactly.
