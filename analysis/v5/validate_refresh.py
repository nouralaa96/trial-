"""Validate staged daily ETF and VIX snapshots for a specified XNYS decision close.

This never trades, fills gaps, changes V4 inputs, or upgrades a rejected model.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

SYMBOLS = ("SPY", "QQQ", "GLD")
LOOKBACK = 21  # VIX level plus 20-session change, with next-session availability.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calendar_for(as_of: str):
    end = pd.Timestamp(as_of)
    cal = xcals.get_calendar("XNYS", start=end - pd.Timedelta(days=100),
                             end=end + pd.Timedelta(days=10))
    sessions = cal.sessions_in_range(end - pd.Timedelta(days=100), end)
    sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
    if end not in sessions:
        raise ValueError(f"{as_of} is not an XNYS session")
    return cal, sessions


def inspect_price(path: Path, symbol: str, required: pd.DatetimeIndex) -> dict:
    raw = json.loads(path.read_text())
    if raw.get("chart", {}).get("error") is not None:
        raise ValueError(f"{symbol}: vendor chart error")
    payload = raw["chart"]["result"][0]
    meta = payload["meta"]
    if meta.get("symbol") != symbol or meta.get("currency") != "USD" or meta.get("exchangeTimezoneName") != "America/New_York":
        raise ValueError(f"{symbol}: wrong symbol/currency/timezone")
    times = payload["timestamp"]
    quote = payload["indicators"]["quote"][0]
    fields = ("open", "high", "low", "close", "volume")
    if not times or any(len(quote[k]) != len(times) for k in fields):
        raise ValueError(f"{symbol}: incomplete quote arrays")
    dates = pd.DatetimeIndex([pd.Timestamp(t, unit="s", tz="UTC").tz_convert("America/New_York").date()
                              for t in times])
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError(f"{symbol}: duplicate or unsorted sessions")
    if dates[-1] > required[-1]:
        raise ValueError(f"{symbol}: snapshot contains bars after decision session")
    unexpected = dates[(dates >= required[0]) & (dates <= required[-1])].difference(required)
    if len(unexpected):
        raise ValueError(f"{symbol}: unexpected non-XNYS bars")
    frame = pd.DataFrame({k: quote[k] for k in fields}, index=dates)
    needed = frame.reindex(required)
    if needed.isna().any().any():
        missing = needed[needed.isna().any(axis=1)].index.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"{symbol}: missing required bars: {missing}")
    values = needed[list(fields)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (needed[list(fields[:4])] <= 0).any().any() or (needed.volume < 0).any():
        raise ValueError(f"{symbol}: nonfinite or invalid quote")
    if (needed.high < needed[["open", "low", "close"]].max(axis=1)).any() or (needed.low > needed[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError(f"{symbol}: invalid OHLC ordering")
    for event in payload.get("events", {}).get("dividends", {}).values():
        if not np.isfinite(float(event["amount"])) or float(event["amount"]) < 0:
            raise ValueError(f"{symbol}: invalid dividend")
    for event in payload.get("events", {}).get("splits", {}).values():
        if float(event["numerator"]) <= 0 or float(event["denominator"]) <= 0:
            raise ValueError(f"{symbol}: invalid split")
    return {"file": str(path), "sha256": digest(path), "bytes": path.stat().st_size,
            "first_observation": str(dates[0].date()), "last_observation": str(dates[-1].date()),
            "required_sessions": len(required), "status": "PASS"}


def inspect_vix(path: Path, required: pd.DatetimeIndex, available_session: str) -> dict:
    frame = pd.read_csv(path)
    if not {"DATE", "CLOSE"}.issubset(frame):
        raise ValueError("VIX: DATE/CLOSE columns required")
    dates = pd.DatetimeIndex(pd.to_datetime(frame.DATE, format="%Y-%m-%d", errors="raise"))
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("VIX: duplicate or unsorted observations")
    close = pd.Series(pd.to_numeric(frame.CLOSE, errors="raise").to_numpy(), index=dates)
    needed = close.reindex(required)
    if needed.isna().any():
        missing = needed[needed.isna()].index.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"VIX: missing required observations: {missing}")
    if not np.isfinite(needed).all() or ((needed <= 0) | (needed > 200)).any():
        raise ValueError("VIX: invalid volatility percent units")
    return {"file": str(path), "sha256": digest(path), "bytes": path.stat().st_size,
            "first_observation": str(dates[0].date()), "last_observation": str(dates[-1].date()),
            "last_usable_observation": str(required[-1].date()),
            "usable_from_session": available_session,
            "required_sessions": len(required), "status": "PASS"}


def inspect(as_of: str, prices: dict[str, Path], vix: Path) -> dict:
    _, sessions = calendar_for(as_of)
    required_price = sessions[-LOOKBACK:]
    required_vix = sessions[-(LOOKBACK + 1):-1]  # Never use same-session VIX close.
    if len(required_price) != LOOKBACK or len(required_vix) != LOOKBACK:
        raise ValueError("Insufficient calendar lookback")
    results, errors = {}, []
    for symbol in SYMBOLS:
        try:
            results[symbol] = inspect_price(prices[symbol], symbol, required_price)
        except (ValueError, KeyError, IndexError, TypeError, FileNotFoundError) as exc:
            results[symbol] = {"status": "REFUSED", "reason": str(exc)}
            errors.append(str(exc))
    try:
        results["VIX"] = inspect_vix(vix, required_vix, as_of)
    except (ValueError, KeyError, IndexError, TypeError, FileNotFoundError) as exc:
        results["VIX"] = {"status": "REFUSED", "reason": str(exc)}
        errors.append(str(exc))
    return {"as_of_session": as_of, "status": "VALIDATED_INPUTS_ONLY" if not errors else "REFUSED",
            "actionable": False, "required_price_first": str(required_price[0].date()),
            "required_vix_first": str(required_vix[0].date()), "results": results,
            "reasons": errors,
            "limits": "Recent-bar validation only; provider use rights, exact publication time, older revisions, model refit and strategy acceptance remain separate gates."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", required=True, help="completed XNYS decision session YYYY-MM-DD")
    p.add_argument("--price-dir", type=Path, required=True, help="directory with SPY.json, QQQ.json, GLD.json")
    p.add_argument("--vix", type=Path, required=True, help="daily DATE,CLOSE CSV")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    date.fromisoformat(args.as_of)
    report = inspect(args.as_of, {s: args.price_dir / f"{s}.json" for s in SYMBOLS}, args.vix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "reasons": report["reasons"], "output": str(args.output)}))
    return 0 if report["status"] == "VALIDATED_INPUTS_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
