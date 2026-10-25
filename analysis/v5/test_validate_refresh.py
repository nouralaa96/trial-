"""Operational input checks; synthetic VIX continuation is test data only."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.v5.validate_refresh import digest, inspect


ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "analysis/v5/data/raw/20261025_yahoo_probe"
OLD_VIX = ROOT / "data/raw/context/20261021T041611Z/vix-daily.csv"
AS_OF = "2026-10-23"


def price_paths(directory=PRICES):
    return {symbol: directory / f"{symbol}.json" for symbol in ("SPY", "QQQ", "GLD")}


def test_archived_price_hashes_match_retrieval_evidence():
    evidence = json.loads((PRICES / "retrieval_evidence.json").read_text())
    for symbol, entry in evidence["responses"].items():
        path = PRICES / entry["file"]
        assert path.stat().st_size == entry["bytes"]
        assert digest(path) == entry["sha256"]


def test_stale_real_vix_refuses():
    result = inspect(AS_OF, price_paths(), OLD_VIX)
    assert result["status"] == "REFUSED"
    assert all(result["results"][s]["status"] == "PASS" for s in price_paths())
    assert result["results"]["VIX"]["status"] == "REFUSED"
    assert "2026-10-22" in result["reasons"][0]
    assert result["actionable"] is False


def test_complete_synthetic_vix_then_missing_bar_refuses(tmp_path):
    raw = pd.read_csv(OLD_VIX)
    missing = pd.bdate_range("2026-09-23", "2026-10-22")
    # This fills a fixture for validator behavior; it is never an admitted market series.
    synthetic = pd.DataFrame({"DATE": missing.strftime("%Y-%m-%d"), "OPEN": 15.0,
                              "HIGH": 15.0, "LOW": 15.0, "CLOSE": 15.0})
    vix = tmp_path / "synthetic-vix.csv"
    pd.concat([raw, synthetic], ignore_index=True).to_csv(vix, index=False)
    complete = inspect(AS_OF, price_paths(), vix)
    assert complete["status"] == "VALIDATED_INPUTS_ONLY"
    assert complete["actionable"] is False
    assert complete["results"]["VIX"]["last_usable_observation"] == "2026-10-22"

    truncated = tmp_path / "short-vix.csv"
    pd.concat([raw, synthetic.iloc[:-1]], ignore_index=True).to_csv(truncated, index=False)
    assert inspect(AS_OF, price_paths(), truncated)["status"] == "REFUSED"


def test_missing_or_future_price_bar_refuses(tmp_path):
    for symbol in ("SPY", "QQQ", "GLD"):
        (tmp_path / f"{symbol}.json").write_bytes((PRICES / f"{symbol}.json").read_bytes())
    spy = tmp_path / "SPY.json"
    payload = json.loads(spy.read_text())
    chart = payload["chart"]["result"][0]
    chart["timestamp"].pop()
    for values in chart["indicators"]["quote"][0].values():
        values.pop()
    spy.write_text(json.dumps(payload))
    result = inspect(AS_OF, price_paths(tmp_path), OLD_VIX)
    assert result["results"]["SPY"]["status"] == "REFUSED"
    assert "missing required bars" in result["results"]["SPY"]["reason"]
