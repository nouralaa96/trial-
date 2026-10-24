"""Frozen, auditable daily market-data ingestion; never fabricates or fills bars.

Yahoo's chart quote OHLC is split-adjusted, but not dividend-adjusted. We undo
reported future split factors to obtain historical executable nominal prices.
Cash dividends remain separate events; adjclose is retained only in the original
vendor snapshot and is never used for fills. Yahoo is an unofficial public
endpoint, not an exchange-certified or point-in-time corporate-actions feed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

SYMBOLS = ("SPY", "QQQ", "GLD")
START = "2009-01-01"
CUTOFF = "2026-10-19"
FIELDS = ("open", "high", "low", "close", "volume", "dividends", "splits")
VENDOR = "https://query1.finance.yahoo.com"
CALENDAR_SOURCE = "https://github.com/gerrymanoim/exchange_calendars"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def session_index(start: str = START, end: str = CUTOFF) -> pd.DatetimeIndex:
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS", start=pd.Timestamp(start) - pd.Timedelta(days=10),
                             end=pd.Timestamp(end) + pd.Timedelta(days=10))
    index = cal.sessions_in_range(start, end)
    return index.tz_localize(None) if index.tz is not None else index


def _event_date(timestamp: int | str, tz: str) -> pd.Timestamp:
    return pd.Timestamp(int(timestamp), unit="s", tz="UTC").tz_convert(tz).tz_localize(None).normalize()


def normalize_yahoo(payload: dict, symbol: str, start: str = START,
                    cutoff: str = CUTOFF) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"{symbol}: vendor error or empty result")
    result = chart["result"][0]
    if result["meta"].get("symbol", "").upper() != symbol:
        raise ValueError("Vendor symbol mismatch")
    if result["meta"].get("currency") != "USD":
        raise ValueError("Expected USD quote currency")
    tz = result["meta"].get("exchangeTimezoneName", "America/New_York")
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({k: quote[k] for k in FIELDS[:5]},
                         index=pd.DatetimeIndex([_event_date(t, tz) for t in timestamps], name="date"))
    frame["dividends"] = 0.0
    frame["splits"] = 1.0
    events = result.get("events", {})
    # A zero action field means no vendor event reported; it is not an assurance
    # against subsequent corrections or missing events at the public endpoint.
    split_events = []
    for key, event in events.get("splits", {}).items():
        date = _event_date(event.get("date", key), tz)
        numerator, denominator = float(event["numerator"]), float(event["denominator"])
        if numerator <= 0 or denominator <= 0:
            raise ValueError("Invalid corporate split ratio")
        ratio = numerator / denominator
        split_events.append((date, ratio))
        if date in frame.index:
            frame.loc[date, "splits"] = ratio
        elif pd.Timestamp(start) <= date <= pd.Timestamp(cutoff):
            raise ValueError("Split event lacks executable session bar")
    for key, event in events.get("dividends", {}).items():
        date = _event_date(event.get("date", key), tz)
        if date in frame.index:
            frame.loc[date, "dividends"] += float(event["amount"])
        elif pd.Timestamp(start) <= date <= pd.Timestamp(cutoff):
            raise ValueError("Dividend event lacks executable session bar")
    for date, ratio in split_events:
        before = frame.index < date
        frame.loc[before, ["open", "high", "low", "close", "dividends"]] *= ratio
        frame.loc[before, "volume"] /= ratio
    return frame.loc[(frame.index >= start) & (frame.index <= cutoff)].copy()


def validate_frame(frame: pd.DataFrame, start: str = START, cutoff: str = CUTOFF,
                   now: pd.Timestamp | None = None) -> dict:
    expected = session_index(start, cutoff)
    errors, warnings = [], []
    if not isinstance(frame.index, pd.DatetimeIndex):
        return {"valid": False, "errors": ["Index is not a DatetimeIndex"], "warnings": []}
    if frame.index.tz is not None:
        errors.append("Session date index must be timezone-naive")
    if not frame.index.is_unique:
        errors.append("Duplicate session timestamps")
    if not frame.index.is_monotonic_increasing:
        errors.append("Timestamps are not ordered")
    if not frame.index.equals(frame.index.normalize()):
        errors.append("Timestamps must be normalized session dates")
    missing = expected.difference(frame.index)
    extra = frame.index.difference(expected)
    if len(missing):
        errors.append(f"Missing {len(missing)} required XNYS sessions")
    if len(extra):
        errors.append(f"Unexpected/out-of-range sessions: {len(extra)}")
    absent = set(FIELDS).difference(frame.columns)
    if absent:
        errors.append(f"Missing fields: {sorted(absent)}")
    else:
        values = frame[list(FIELDS)].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            errors.append("Nonfinite market data")
        if (frame[list(FIELDS[:4])] <= 0).any().any():
            errors.append("Prices must be positive")
        if (frame.volume < 0).any() or (frame.dividends < 0).any() or (frame.splits <= 0).any():
            errors.append("Invalid volume, dividends, or split ratios")
        if (frame.volume == 0).any():
            warnings.append("Zero-volume session requires review")
        bad_ohlc = ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
                    (frame.low > frame[["open", "close", "high"]].min(axis=1)))
        if bad_ohlc.any():
            errors.append("OHLC high/low inconsistency")
        # New-share close times split ratio versus previous nominal close.
        moves = frame.close * frame.splits / frame.close.shift(1) - 1
        jumps = moves.abs() > 0.20
        if jumps.any():
            warnings.append("Split-aware >20% close discontinuities require review")
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tz is None else now.tz_convert("UTC")
    if len(frame):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS", start=start, end=cutoff)
        completed = [d for d in frame.index.intersection(expected) if cal.session_close(d) > now]
        if completed:
            errors.append("Future or incomplete sessions present")
    warmup = int((frame.index < "2010-01-01").sum())
    if start == START and warmup < 50:
        errors.append("Insufficient pre-2010 indicator warm-up (requires >=50 sessions)")
    return {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "rows": len(frame), "expected_rows": len(expected),
        "first_session": str(frame.index.min().date()) if len(frame) else None,
        "last_session": str(frame.index.max().date()) if len(frame) else None,
        "missing_sessions": [str(d.date()) for d in missing],
        "unexpected_sessions": [str(d.date()) for d in extra],
        "warmup_sessions": warmup,
        "dividend_events": int((frame.dividends > 0).sum()) if "dividends" in frame else None,
        "split_events": int((frame.splits != 1).sum()) if "splits" in frame else None,
        "discontinuities": [str(d.date()) for d in frame.index[jumps]] if not absent else [],
    }


def _fetch(url: str, target: Path) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = {"url": url, "retrieved_at_utc": timestamp, "tls_verification": True}
    req = urllib.request.Request(url, headers={"User-Agent": "reproducible-trading-research/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            record.update(http_status=response.status, content_type=response.headers.get("Content-Type"),
                          final_url=response.geturl(), status="retrieved")
        target.write_bytes(body)
        record.update(path=str(target), sha256=sha256(target), bytes=len(body))
    except urllib.error.HTTPError as error:
        target.write_bytes(error.read())
        record.update(status="blocked", http_status=error.code, error=str(error),
                      path=str(target), sha256=sha256(target))
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        # A CONNECT denial is raised before an origin HTTP response exists.
        record.update(status="blocked", http_status=None, error=str(error))
    return record


def ingest(data_dir: str | Path = "data") -> dict:
    root = Path(data_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw = root / "raw" / stamp
    processed = root / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    sessions = session_index()
    calendar_path = raw / "XNYS_sessions.csv"
    pd.DataFrame({"date": sessions.strftime("%Y-%m-%d")}).to_csv(calendar_path, index=False)
    manifest = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "start": START, "cutoff": CUTOFF, "symbols": list(SYMBOLS),
        "status": "blocked", "source": "Yahoo Finance public chart endpoint",
        "calendar": {"name": "XNYS", "source_url": CALENDAR_SOURCE,
                     "package_version": importlib.metadata.version("exchange-calendars"),
                     "path": str(calendar_path), "sha256": sha256(calendar_path)},
        "methodology": "No dividend adjustment. Reverse vendor split-adjusted quotes and volume using returned split events; book splits and dividends explicitly. No forward fill. Exclude incomplete and post-cutoff sessions.",
        "limitations": ["Unofficial public endpoint; data and actions can be revised.",
                        "No exchange-certified point-in-time action history or dividend payment dates.",
                        "Yahoo redistribution/license rights not established; retain for local research and review vendor terms before sharing snapshots.",
                        "Dividend cash settlement must remain conservative without verified payment dates."],
        "license_reference": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        "retrievals": {}, "validation": {}, "processed": {},
    }
    start_epoch = int(pd.Timestamp(START, tz="UTC").timestamp())
    # Include actions after the frozen cutoff through retrieval day, because
    # vendor split adjustments can include these even in earlier daily quotes.
    end = max(pd.Timestamp(CUTOFF, tz="UTC") + pd.Timedelta(days=1),
              pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=1))
    for symbol in SYMBOLS:
        url = f"{VENDOR}/v8/finance/chart/{symbol}?" + urllib.parse.urlencode({
            "period1": start_epoch, "period2": int(end.timestamp()), "interval": "1d",
            "events": "div,splits", "includeAdjustedClose": "true"})
        path = raw / f"{symbol}.json"
        record = _fetch(url, path)
        manifest["retrievals"][symbol] = record
        if record["status"] == "retrieved":
            try:
                frame = normalize_yahoo(json.loads(path.read_text()), symbol)
                result = validate_frame(frame)
                manifest["validation"][symbol] = result
                if result["valid"]:
                    output = processed / f"{symbol}.csv"
                    frame.to_csv(output, index_label="date", float_format="%.12g")
                    manifest["processed"][symbol] = {"path": str(output), "sha256": sha256(output)}
            except (ValueError, KeyError, TypeError) as error:
                record.update(status="invalid", parse_error=str(error))
        if symbol not in manifest["validation"]:
            manifest["validation"][symbol] = {
                "valid": False, "rows": 0, "expected_rows": len(sessions),
                "errors": ["No validated market snapshot available"],
                "missing_sessions": [str(d.date()) for d in sessions],
                "unverified_actions": True,
            }
    if len(manifest["processed"]) == len(SYMBOLS):
        manifest["status"] = "complete"
    evidence = raw / "retrieval_evidence.json"
    _write_json(evidence, {"retrievals": manifest["retrievals"]})
    manifest["retrieval_evidence"] = {"path": str(evidence), "sha256": sha256(evidence)}
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "validation.json", manifest["validation"])
    return manifest


def load_panel(data_dir: str | Path = "data") -> dict[str, pd.DataFrame]:
    """Refuse partial, stale, tampered or unvalidated historical panels."""
    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Missing data manifest; run python -m research.data ingest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "complete":
        raise ValueError("Historical market data blocked or incomplete; inspect data/manifest.json")
    if manifest.get("cutoff") != CUTOFF or manifest.get("start") != START:
        raise ValueError("Data period differs from frozen specification")
    for entry in [manifest["calendar"], manifest["retrieval_evidence"],
                  *manifest["processed"].values(), *manifest["retrievals"].values()]:
        path = Path(entry["path"])
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {path}")
    panel = {}
    for symbol in SYMBOLS:
        path = Path(manifest["processed"][symbol]["path"])
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        report = validate_frame(frame)
        if not report["valid"]:
            raise ValueError(f"Invalid {symbol} market data: {report['errors']}")
        panel[symbol] = frame
    return panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["ingest", "validate"], nargs="?", default="ingest")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    if args.command == "ingest":
        manifest = ingest(args.data_dir)
        print(json.dumps({"status": manifest["status"], "manifest": str(Path(args.data_dir) / "manifest.json"),
                          "retrievals": {k: {"status": v["status"], "error": v.get("error")}
                                         for k, v in manifest["retrievals"].items()}}, indent=2))
        return 0 if manifest["status"] == "complete" else 2
    try:
        panel = load_panel(args.data_dir)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}))
        return 2
    print(json.dumps({"status": "complete", "rows": {s: len(f) for s, f in panel.items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
