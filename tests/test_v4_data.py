import json
import shutil

import numpy as np
import pandas as pd
import pytest

from data_pipeline import ROOT, FEATURE, audit_prices, build, normalize_context, sessions, sha256, validate_context


def fixture_calendar():
    return pd.DatetimeIndex(["2009-01-02", "2009-01-05", "2009-01-06", "2009-01-07"])


def test_next_session_availability_and_percent_units():
    frame = normalize_context(pd.DataFrame({"DATE": ["2009-01-02", "2009-01-05"], "CLOSE": [15., 22.]}), fixture_calendar(), "2009-01-06")
    assert frame.available_date.iloc[0] == pd.Timestamp("2009-01-05")
    assert frame[FEATURE].iloc[0] == 15.0
    assert (frame.available_date > frame.date).all()
    validate_context(frame, fixture_calendar())


def test_absent_interior_and_terminal_observations_remain_missing():
    raw = pd.DataFrame({"DATE": ["2009-01-02", "2009-01-06"], "CLOSE": [15., 30.]})
    frame = normalize_context(raw, fixture_calendar(), "2009-01-06")
    assert np.isnan(frame[FEATURE].iloc[1])
    assert frame[FEATURE].iloc[2] == 30.
    # A future observation cannot alter any prior value or availability.
    prefix = normalize_context(raw.iloc[:1], fixture_calendar(), "2009-01-06")
    pd.testing.assert_frame_equal(prefix.iloc[:2], frame.iloc[:2])


def test_duplicate_observations_rejected():
    with pytest.raises(ValueError, match="unique"):
        normalize_context(pd.DataFrame({"DATE": ["2009-01-02"] * 2, "CLOSE": [15., 16.]}), fixture_calendar(), "2009-01-06")


@pytest.mark.parametrize("bad", [-1., 0., np.inf, 1500.])
def test_invalid_context_values_rejected(bad):
    with pytest.raises(ValueError, match="units"):
        normalize_context(pd.DataFrame({"DATE": ["2009-01-02"], "CLOSE": [bad]}), fixture_calendar(), "2009-01-06")


def test_same_day_or_stale_availability_rejected():
    frame = normalize_context(pd.DataFrame({"DATE": ["2009-01-02"], "CLOSE": [15.]}), fixture_calendar(), "2009-01-06")
    frame.loc[0, "available_date"] = frame.loc[0, "date"]
    with pytest.raises(ValueError, match="availability"):
        validate_context(frame, fixture_calendar())


def test_retained_context_missing_tail_and_exact_source_values():
    context = pd.read_csv(ROOT / "data/context.csv", parse_dates=["date", "available_date"])
    raw = pd.read_csv(ROOT / "data/raw/context/20261021T041611Z/vix-daily.csv", index_col="DATE")
    validate_context(context, sessions())
    assert int(context[FEATURE].isna().sum()) == 19
    assert context.loc[context[FEATURE].notna(), "date"].max() == pd.Timestamp("2026-09-22")
    for row in context.loc[context[FEATURE].notna()].itertuples():
        assert getattr(row, FEATURE) == raw.loc[row.date.strftime("%Y-%m-%d"), "CLOSE"]


def test_original_prices_match_raw_manifest_and_calendar():
    report = audit_prices()
    assert report["valid"]
    assert all(x["rows"] == 4476 and x["raw_processed_match"] for x in report["symbols"].values())


def test_altered_processed_price_is_detected(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    path = tmp_path / "data/processed/SPY.csv"
    prices = pd.read_csv(path)
    prices.loc[0, "close"] += 0.01
    prices.to_csv(path, index=False)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        audit_prices(tmp_path)


def test_offline_rebuild_is_byte_identical_and_preserves_acquisition_evidence(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    before = {str(p.relative_to(tmp_path)): sha256(p) for p in (tmp_path / "data").rglob("*") if p.is_file()}
    build(tmp_path)
    after = {str(p.relative_to(tmp_path)): sha256(p) for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert before == after
