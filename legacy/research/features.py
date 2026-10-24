"""Completed-bar indicators and explicitly indexed executable-return labels.

Prices supplied here are raw executable prices. Multiplying history by cumulative
split ratios expresses it in a stable share unit; dividing price indicators by
today's ratio makes each indicator comparable to today's executable close.
No future split or dividend can change an earlier feature.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["return_1", "return_5", "return_20", "close_sma20",
                   "close_sma50", "volatility20", "atr_pct", "volume_relative20"]


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing seeded with the first complete arithmetic mean."""
    out = pd.Series(np.nan, index=series.index, dtype=float)
    values = series.to_numpy(dtype=float)
    first = None
    for i in range(period - 1, len(values)):
        if np.isfinite(values[i-period+1:i+1]).all():
            out.iloc[i] = values[i-period+1:i+1].mean()
            first = i
            break
    if first is not None:
        for i in range(first + 1, len(values)):
            if np.isfinite(values[i]) and np.isfinite(out.iloc[i-1]):
                out.iloc[i] = (out.iloc[i-1] * (period-1) + values[i]) / period
    return out


def executable_labels(frame: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """t label = economic proceeds at close[t+5] / open[t+1] - 1.

    One share is bought at t+1 open. Subsequent splits change share count and
    ex-date cash dividends add to proceeds. A dividend on the entry ex-date is
    excluded because a buyer on that ex-date has no entitlement. Distributions
    are receivables at ex-date; this label does not assume reinvestment.
    """
    result = pd.DataFrame(index=frame.index)
    result["label"] = np.nan
    result["label_matured"] = pd.NaT
    splits = frame.get("splits", pd.Series(0., index=frame.index)).fillna(0).to_numpy()
    dividends = frame.get("dividends", pd.Series(0., index=frame.index)).fillna(0).to_numpy()
    opens, closes = frame.open.to_numpy(), frame.close.to_numpy()
    for t in range(len(frame) - horizon):
        qty, distribution = 1., 0.
        for j in range(t + 2, t + horizon + 1):
            qty *= splits[j] if splits[j] > 0 else 1.
            distribution += qty * dividends[j]
        result.iloc[t, 0] = (qty * closes[t+horizon] + distribution) / opens[t+1] - 1.
        result.iloc[t, 1] = frame.index[t+horizon]
    return result


def instrument_features(frame: pd.DataFrame) -> pd.DataFrame:
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Feature timestamps must be unique and ordered")
    required = ["open", "high", "low", "close", "volume"]
    if frame[required].isna().any().any():
        raise ValueError("Missing OHLCV cannot be filled for indicators")
    f = frame.copy()
    split = f.get("splits", pd.Series(0., index=f.index)).fillna(0).replace(0, 1.)
    unit = split.cumprod()
    close, high, low = f.close * unit, f.high * unit, f.low * unit
    volume = f.volume / unit
    for n in (20, 50):
        f[f"sma{n}"] = close.rolling(n, min_periods=n).mean() / unit
        f[f"close_sma{n}"] = f.close / f[f"sma{n}"] - 1
    for n in (1, 5, 20):
        f[f"return_{n}"] = close.pct_change(n, fill_method=None)
    f["volatility20"] = f.return_1.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(252)
    previous = close.shift(1)
    tr = pd.concat([high-low, (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    f["atr14"] = _wilder(tr, 14) / unit
    f["atr_pct"] = f.atr14 / f.close
    f["volume_relative20"] = volume / volume.rolling(20, min_periods=20).mean()
    delta = close.diff()
    gain, loss = _wilder(delta.clip(lower=0), 14), _wilder((-delta).clip(lower=0), 14)
    rs = gain / loss
    f["rsi14"] = (100 - 100/(1+rs)).where(loss != 0, 100.).where((gain != 0) | (loss != 0), 50.)
    fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = fast - slow
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    f["macd"], f["macd_signal"], f["macd_hist"] = macd/unit, signal/unit, (macd-signal)/unit
    f["indicator_timestamp"] = f.index
    f["features_valid"] = np.isfinite(f[FEATURE_COLUMNS]).all(axis=1)
    return f.join(executable_labels(frame))


def build_features(panel: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {symbol: instrument_features(frame) for symbol, frame in panel.items()}
