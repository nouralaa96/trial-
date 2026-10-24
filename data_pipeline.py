"""Offline, deterministic provenance audit and causal context normalization.

Run `python data_pipeline.py` from this folder. No network is used by rebuilds.
Raw context is an immutable public mirror snapshot, not vintage-certified data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
START, CUTOFF = "2009-01-01", "2026-10-19"
SYMBOLS = ("SPY", "QQQ", "GLD")
FIELDS = ("open", "high", "low", "close", "volume", "dividends", "splits")
SNAPSHOT = Path("data/raw/context/20261021T041611Z")
FEATURE = "vix_close_pct"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sessions(start: str = START, end: str = "2026-10-23") -> pd.DatetimeIndex:
    import exchange_calendars as xcals
    index = xcals.get_calendar("XNYS", start=pd.Timestamp(start) - pd.Timedelta(days=10),
                               end=pd.Timestamp(end) + pd.Timedelta(days=10)).sessions_in_range(start, end)
    return index.tz_localize(None) if index.tz is not None else index


def normalize_context(raw: pd.DataFrame, calendar: pd.DatetimeIndex,
                      cutoff: str = CUTOFF) -> pd.DataFrame:
    """Exact observation-date grid; no interpolation, backfill or stale carry."""
    required = {"DATE", "CLOSE"}
    if not required.issubset(raw):
        raise ValueError("VIX requires DATE and CLOSE")
    dates = pd.to_datetime(raw.DATE, format="%Y-%m-%d", errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("VIX observation dates must be unique and ordered")
    close = pd.to_numeric(raw.CLOSE, errors="raise")
    if (~np.isfinite(close) | (close <= 0) | (close > 200)).any():
        raise ValueError("VIX units must be annualized volatility percent in (0,200]")
    # 15 means 15%, not 0.15 or 1500 basis points. The source's units are
    # independently documented in the contract; a magnitude check is secondary.
    observations = pd.Series(close.to_numpy(), index=dates, name=FEATURE)
    grid = calendar[(calendar >= START) & (calendar <= cutoff)]
    positions = calendar.get_indexer(grid)
    if len(grid) and positions[-1] + 1 >= len(calendar):
        raise ValueError("Calendar must include next session after cutoff")
    return pd.DataFrame({"date": grid, "available_date": calendar[positions + 1],
                         FEATURE: observations.reindex(grid).to_numpy()})


def validate_context(frame: pd.DataFrame, calendar: pd.DatetimeIndex) -> None:
    dates, usable = pd.to_datetime(frame.date), pd.to_datetime(frame.available_date)
    if dates.duplicated().any() or usable.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Context timestamps must be unique and ordered")
    positions = calendar.get_indexer(dates)
    if (positions < 0).any() or (positions + 1 >= len(calendar)).any():
        raise ValueError("Unknown observation session")
    if not np.array_equal(usable.to_numpy(), calendar[positions + 1].to_numpy()):
        raise ValueError("Context availability must be strictly next XNYS session")
    values = pd.to_numeric(frame[FEATURE], errors="raise").dropna()
    if (~np.isfinite(values) | (values <= 0) | (values > 200)).any():
        raise ValueError("Invalid VIX percent units")


def _date(timestamp: int, tz: str) -> pd.Timestamp:
    return pd.Timestamp(timestamp, unit="s", tz="UTC").tz_convert(tz).tz_localize(None).normalize()


def audit_prices(root: Path = ROOT) -> dict:
    manifest = json.loads((root / "data/original_manifest.json").read_text())
    expected = pd.DatetimeIndex(pd.read_csv(root / manifest["calendar"]["path"], parse_dates=["date"]).date)
    errors, reports = [], {}
    for symbol in SYMBOLS:
        raw_meta, processed_meta = manifest["retrievals"][symbol], manifest["processed"][symbol]
        for meta in [raw_meta, processed_meta, manifest["calendar"], manifest["retrieval_evidence"]]:
            if sha256(root / meta["path"]) != meta["sha256"]:
                errors.append(f"{symbol}: source SHA256 mismatch: {meta['path']}")
        payload = json.loads((root / raw_meta["path"]).read_text())["chart"]["result"][0]
        if payload["meta"]["symbol"] != symbol or payload["meta"]["currency"] != "USD":
            errors.append(f"{symbol}: incorrect symbol/currency")
        tz = payload["meta"]["exchangeTimezoneName"]
        index = pd.DatetimeIndex([_date(t, tz) for t in payload["timestamp"]], name="date")
        quote = payload["indicators"]["quote"][0]
        reconstructed = pd.DataFrame({key: quote[key] for key in FIELDS[:5]}, index=index)
        reconstructed["dividends"], reconstructed["splits"] = 0.0, 1.0
        events = payload.get("events", {})
        split_events = []
        for key, event in events.get("splits", {}).items():
            d, ratio = _date(int(event.get("date", key)), tz), float(event["numerator"]) / float(event["denominator"])
            split_events.append((d, ratio))
            if d in reconstructed.index:
                reconstructed.loc[d, "splits"] = ratio
        for key, event in events.get("dividends", {}).items():
            d = _date(int(event.get("date", key)), tz)
            if d in reconstructed.index:
                reconstructed.loc[d, "dividends"] += float(event["amount"])
        for d, ratio in split_events:
            prior = reconstructed.index < d
            reconstructed.loc[prior, ["open", "high", "low", "close", "dividends"]] *= ratio
            reconstructed.loc[prior, "volume"] /= ratio
        reconstructed = reconstructed.loc[START:CUTOFF]
        processed = pd.read_csv(root / processed_meta["path"], index_col="date", parse_dates=True)
        duplicates = int(processed.index.duplicated().sum())
        missing = expected.difference(processed.index)
        unexpected = processed.index.difference(expected)
        finite = bool(np.isfinite(processed[list(FIELDS)].to_numpy()).all())
        bad_ohlc = (processed.high < processed[["open", "low", "close"]].max(axis=1)) | (processed.low > processed[["open", "high", "close"]].min(axis=1))
        mismatch = not reconstructed.index.equals(processed.index) or not np.allclose(reconstructed[list(FIELDS)], processed[list(FIELDS)], rtol=0, atol=1e-7)
        invalid = duplicates or len(missing) or len(unexpected) or not finite or bool(bad_ohlc.any()) or mismatch
        if invalid:
            errors.append(f"{symbol}: failed raw/processed/calendar audit")
        reports[symbol] = {"rows": len(processed), "first_session": str(processed.index.min().date()), "last_session": str(processed.index.max().date()), "duplicate_dates": duplicates, "missing_sessions": [str(x.date()) for x in missing], "unexpected_sessions": [str(x.date()) for x in unexpected], "nonfinite_values": int((~np.isfinite(processed[list(FIELDS)].to_numpy())).sum()), "invalid_ohlc_rows": int(bad_ohlc.sum()), "raw_processed_match_atol": 1e-7, "raw_processed_match": not mismatch, "dividend_events": int((processed.dividends > 0).sum()), "split_events": int((processed.splits != 1).sum()), "max_split_aware_abs_daily_return": float((processed.close * processed.splits / processed.close.shift(1) - 1).abs().max()), "units": {"prices_and_dividends": "USD per share", "volume": "shares", "splits": "new/old shares;1=no event"}}
    report = {"valid": not errors, "errors": errors, "symbols": reports, "limitation": "Recomputing the vendor snapshot establishes internal consistency, not independent truth or a vintage-safe corporate action feed."}
    if errors:
        raise ValueError(str(report))
    return report


def build(root: Path = ROOT) -> None:
    raw = pd.read_csv(root / SNAPSHOT / "vix-daily.csv")
    evidence = json.loads((root / SNAPSHOT / "retrieval_evidence.json").read_text())
    for record in evidence["records"]:
        if sha256(root / record["path"]) != record["sha256"]:
            raise ValueError("Context raw evidence hash mismatch")
    calendar = sessions()
    context = normalize_context(raw, calendar)
    validate_context(context, calendar)
    context.to_csv(root / "data/context.csv", index=False, date_format="%Y-%m-%d", float_format="%.6f")
    audit = audit_prices(root)
    write_json(root / "data/price_audit.json", audit)
    present = context[FEATURE].notna()
    non_session = pd.DatetimeIndex(pd.to_datetime(raw.DATE)).difference(calendar)
    in_period = non_session[(non_session >= START) & (non_session <= CUTOFF)]
    summary = {"raw_rows": len(raw), "raw_first_observation": str(raw.DATE.iloc[0]), "raw_last_observation": str(raw.DATE.iloc[-1]), "grid_rows": len(context), "nonmissing_rows": int(present.sum()), "missing_rows": int((~present).sum()), "first_nonmissing_observation": str(context.loc[present, "date"].min().date()), "last_nonmissing_observation": str(context.loc[present, "date"].max().date()), "last_available_date": str(context.loc[present, "available_date"].max().date()), "min_vix_close_pct": float(context.loc[present, FEATURE].min()), "max_vix_close_pct": float(context.loc[present, FEATURE].max()), "non_XNYS_source_dates_in_research_range": [str(x.date()) for x in in_period], "missing_observation_dates": context.loc[~present, "date"].dt.strftime("%Y-%m-%d").tolist()}
    write_json(root / "data/context_audit.json", summary)
    paths = sorted(p for p in (root / "data").rglob("*") if p.is_file() and p.name != "manifest.json")
    write_json(root / "data/manifest.json", {"schema_version": 4, "cutoff": CUTOFF, "context_series_count": 1, "context_features": [FEATURE], "context_revision": evidence["revision"], "price_audit_valid": audit["valid"], "context_audit": summary, "files": {str(p.relative_to(root)): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in paths}})
    print(json.dumps({"price_audit_valid": audit["valid"], "context": summary}, indent=2))


if __name__ == "__main__":
    build()
