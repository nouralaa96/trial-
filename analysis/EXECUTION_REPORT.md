# Execution audit and paper replay

The frozen finalist is **C03, REJECTED_RESEARCH**. The paper tool never emits an actionable order. Its successful historical output is explicitly `REJECTED_RESEARCH_COUNTERFACTUAL`, with `actionable:false`, the complete final gate results, and no broker connection. Current paper inspection fails closed. No strategy approval was manufactured to demonstrate the CLI.

## Reproducible commands

Run from the V4 directory:

```bash
.venv/bin/python paper.py --help
.venv/bin/python paper.py status
.venv/bin/python paper.py replay --date 2024-03-08 --output artifacts/paper_demo/historical_replay.json --snapshot-out artifacts/paper_demo/snapshot.json
.venv/bin/python paper.py replay --date 2024-03-08 --snapshot artifacts/paper_demo/snapshot.json --output artifacts/paper_demo/snapshot_check.json
.venv/bin/python paper.py replay --date 2024-03-06 --output artifacts/paper_demo/historical_exit.json
.venv/bin/python paper.py paper --as-of 2026-10-24T05:09:25Z --output artifacts/paper_demo/current_refusal.json
.venv/bin/python paper.py live --output artifacts/paper_demo/live_refusal.json
.venv/bin/python paper.py order --output artifacts/paper_demo/order_refusal.json
.venv/bin/python -m pytest tests/test_v4_paper.py -q
```

`replay`, `paper`, `live`, `order`, and `status` are the positional modes. Options are `--bundle`, `--date`, `--as-of`, `--scenario`, `--snapshot`, `--snapshot-out`, and `--output`. Defaults are the local frozen bundle and `risk05_base_whole`. Successful inspection exits 0; refusals exit 2 and write a machine-readable reason. `live` and `order` always refuse before any broker action. Exact help and executed argument arrays are saved in `artifacts/paper_demo/help.txt` and `commands.json`.

`.venv/bin/python artifacts/paper_demo/reproduce.py` rebuilds the research bundle and all demonstration outputs from the already finalized research artifacts, checks exit codes, and checks replay equity against the frozen evaluation curve. It neither refits a model nor changes candidate definitions or gate decisions. Its current-paper timestamp is generated from the UTC clock. This is local replay machinery, not a recurring signal service.

## Actual demonstration results

The 2024-03-08 replay reconstructs the carried account from the beginning of the final partition, using that date's stored forecast from its historical fit. It does not initialize a fictional fresh $5,000 account on the requested day and does not use the saved 2026 pipeline to predict a 2024 date. Marked equity is **$5,435.040346804608**, exactly equal to the frozen C03 evaluation curve; `parity.json` records zero difference.

Its counterfactual QQQ plan is 12 shares, next execution session 2024-03-11, cap $441.215089, stop $429.042014, target $477.734313, all-in reserved cash $5,295.671068 and planned loss $150.831149. Available settled cash is $5,435.040347; the trade/session cap is $271.752017. Cash capacity binds. The output also explains the filtered GLD forecast and the rejected second SPY candidate, rather than hiding unsuccessful decisions. The 2024-03-06 replay contains the actual historical 27-share GLD target exit at $198.876004. Snapshot export and reimport produce the same validated ledger.

At the actual 2026-10-24 UTC demonstration time the last completed XNYS session is 2026-10-23. ETF bars end 2026-10-19, so current paper mode returns `missing_or_stale_completed_bar: SPY`. An explicitly old paper timestamp returns `stale_paper_as_of_use_historical_replay`; live/order return `live_and_order_actions_unsupported`. The VIX source independently ends at observation 2026-09-22, usable 2026-09-23. Its padded October grid rows contain missing values and cannot count as fresh context.

## Provenance, completeness and chronology

`artifacts/paper_bundle.json` binds model metadata, the saved pipeline, full dated forecasts, final gates, frozen execution configuration, all three raw executable price files, context, registry, and paper/execution source files by SHA256. Loading additionally checks the model metadata's original data and source hashes and candidate identity. A missing file, changed file, mismatched candidate or changed model input refuses. Hashes provide reproducibility and accidental-tamper detection; there is no claim of cryptographic publisher authentication.

Replay uses the fixed partition valuation calendar and endpoint entry embargo, processing only bars at or before the requested session. The original final-period entry cutoff remains in effect. Future corporate actions or prices cannot change earlier replay decisions; this is regression-tested. Historical forecasts retain their own training cutoff and first available decision, which must precede or equal the decision as appropriate. Quarterly refit age is bounded at 110 calendar days. The final saved pipeline is provenance material, never a substitute for historical forecasts.

Paper requires a timezone-explicit known timestamp, rejects future timestamps, derives the latest completed session from actual XNYS closing times, and requires that same completed session as the current clock. This includes holidays, daylight-saving offsets and early closes. Old timestamps belong in `replay` mode. For SPY, QQQ and GLD every required session from the beginning of available history through the decision must be present, ordered and unique; at least 60 bars must exist; OHLCV/actions must be finite and internally valid. All three same-session forecast records are required. Missing raw predictions require an explicit no-entry flag and cannot silently become a positive forecast.

Context requires an exact `available_date` match, an earlier observation date, finite VIX level and finite 20-session change. There is no unrestricted carry-forward over a stale or padded grid. Null confidence is legitimate for P01/P02, which have no confidence layer; C03/C04 require their declared residual diagnostic. This diagnostic is not a calibrated probability of profit. Future label/outcome fields in research forecast CSVs are excluded from decision JSON by an explicit column whitelist.

A supplied snapshot must have the exact decision date, bundle identity and full reconstructed ledger/risk state. Missing/stale/future timestamps, altered cash, positions, unsettled cash, marks, reservations or risk counters refuse. Snapshot JSON roundtrip is tested. This deliberately supports deterministic frozen paper/replay state, not arbitrary brokerage account import.

## Cash and risk audit

The adapter imports the copied ledger via `legacy.research`, with no path injection or dependency on the original V2 directory. Original V2 source is unchanged. The reusable interfaces are `run_engine(panel, predictions, config, strategy, start, end, ...)`, `make_engine(config)`, and `benchmark(SPY_frame, config, start, end, reinvest=False)`. Results contain equity, trades and decisions DataFrames. The adapter's event driver matches the inherited Backtrader driver exactly on a meaningful trading fixture, including all three output frames. Supplied trend forecast masks are honored; an all-NaN trend forecast produces no admissions, while finite original trend forecasts preserve parity.

| Control | Audited behavior |
|---|---|
| Capital and leverage | $5,000 initial cash; long purchases bounded by settled cash net of existing reservations; no borrowing/short positions |
| Trade/session loss budgets | 5%/5% or 10%/10%; trade cap uses current marked equity; session cap freezes at session-start equity |
| Weekly budget | 15% or 30% of week-start equity; Riyadh Monday–Sunday week; realized losses, costs and outstanding risk enter admission/protection |
| Counts | Maximum three held plus pending positions; two considered candidates per session; one admitted plan per session; cancellation does not recycle consumed daily allowance |
| Cash settlement | Historical T+3 before 2017-09-05, T+2 through 2024-05-27, T+1 thereafter; unsettled sales cannot fund same-day purchases |
| Entry | Completed-close decision; next-session capped buy at close ×1.005; full fill or cancellation; cash/risk reservation sealed against mutation |
| Bracket | Stop 2 ATR, target 6 ATR; at least 2:1 reward/risk after modeled fees/slippage; actual fill revalidation; maximum 20 holding sessions |
| Ambiguous bars/gaps | Stop first if stop and target both touched; gap stops use opening price; intraday capped entry cannot claim an earlier target touch |
| Costs | Base $1.09 per side and 5 bps; stress $2.18 and 10 bps; whole/fractional rounding retained |
| Corporate actions | Split-adjusted share counts/brackets; ex-date dividend receivables; assumed payout after 30 calendar days |
| Liquidity | Full small-order fills inferred from daily bars; partial fills unsupported; no historical quote queue, spread or volume participation constraint |
| Capital floor | Inherited absolute $160 floor; it is not a $4,500 or trailing drawdown floor |

The 10% peak drawdown requirement is an acceptance target, **not a guaranteed engine stop**. The 5%/15% and 10%/30% budgets do not imply it. Opening gaps can exceed planned trade loss, weekly budget and drawdown target. A regression deliberately opens a large gap, verifies the resulting protective exit and loss above 10%, and retains that loss in the ledger. Close-detected protective breaches queue next-open exits; continuous intraday protection is not simulated. Liquidity and assumed dividend payout dates remain economic limitations, even though accounting tests pass.

The frozen lower-risk sensitivity halves trade/session risk ceilings; it is labeled `half_risk_ceilings`. It is not exact half share sizing: cash or whole-share rounding may bind and fixed costs remain. Its weekly budget is unchanged under the recorded clarification. No extra risk variant was introduced by this workflow.

## Passive references

Both SPY references use the same valuation dates, $5,000 cash, raw executable prices, scenario costs and rounding, including initial purchase and terminal liquidation costs. One retains distributions as cash/receivables; the other reinvests only when assumed dividend payout cash becomes available, at that session's open with another buy fee. Ex-date opening buyers do not receive that distribution. Split events update quantities. The reinvested reference is an investable approximation with an explicit assumed 30-day payout lag, not an ideal instantaneous ex-date adjusted-price series. Both passive curves are explicitly labeled as outside the active strategy's risk policy; their lack of protective stops is not reported as active risk compliance.

## Verification and defects

`tests/test_v4_paper.py`: **18 passed**. Backtrader emits dependency deprecation warnings; there are no failures. Checks cover original-driver parity, trend masks, partial replay state, future-bar mutation, cash reservation, both risk policies, candidate/entry/position limits, T+1 proceeds, retained gap losses, sealed reservation tampering, rejected partial fills, dividend reinvestment timing, stale/future/missing inputs, context availability and padded NaNs, optional confidence, outcome-field exclusion, snapshot JSON roundtrip and missing raw predictions. Final demonstration CLI exit codes and exact frozen-curve parity are separately checked by the reproduction script.

Defects corrected before final paper freeze: supplied trend masks initially did not override the deterministic return input; passive risk metadata initially contained an infinite sentinel; paper freshness initially relied on padded observation dates rather than finite exact availability; optional uncalibrated confidence initially refused; raw research outcome columns initially risked disclosure in decision JSON; and Python date objects initially broke snapshot JSON roundtrip equality. None required a strategy change. The execution-adapter fixes affecting economic evaluation preceded the final 196-fit/168-portfolio research outputs. Paper-only context, confidence, disclosure and snapshot fixes were finalized afterward and did not change economic evaluation source or results. No candidate definition or risk policy was altered to fix them. Final paper demonstration reconstruction adds no candidate selection or new full-period performance ranking.

Future paper use requires fresh complete ETF and context observations with documented availability, causal feature/forecast generation from a valid refit, refreshed provenance and explicit strategy acceptance under the frozen gates. Merely editing a timestamp, copying old VIX values or changing `REJECTED_RESEARCH` to an approval label cannot make the present research strategy valid. There is no broker adapter, live order route, unattended scheduler or prospective evidence in this deliverable.
