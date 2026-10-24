"""Marked-portfolio metrics; undefined denominators are JSON-safe nulls."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _equity(frame) -> pd.DataFrame:
    if isinstance(frame, pd.Series):
        frame = frame.to_frame("equity")
    frame = pd.DataFrame(frame).copy()
    if "date" in frame:
        frame.index = pd.to_datetime(frame.pop("date"))
    if not frame.empty:
        frame.index = pd.to_datetime(frame.index)
        if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
            raise ValueError("Equity sessions must be unique and ordered")
        if not np.isfinite(frame.equity).all():
            raise ValueError("Nonfinite equity")
    return frame


def _adjusted(frame: pd.DataFrame) -> pd.Series:
    flows = frame.get("external_flows", pd.Series(0., index=frame.index))
    return frame.equity - flows


def _week_keys(frame: pd.DataFrame):
    if "week" in frame:
        return frame.week.to_numpy()
    return frame.index.to_period("W-SUN")


def weekly_dollar_pnl(equity, initial_equity=1000.) -> pd.Series:
    f = _equity(equity)
    if f.empty:
        return pd.Series(dtype=float)
    adjusted = _adjusted(f)
    daily = adjusted.diff()
    daily.iloc[0] = adjusted.iloc[0] - initial_equity
    return daily.groupby(_week_keys(f)).sum()


def _trade_stats(trades: pd.DataFrame) -> dict:
    pnl = trades.get("net_pnl", trades.get("pnl", pd.Series(dtype=float))).astype(float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_loss = float(-losses.sum())
    return {"completed_trades": len(pnl),
            "net_expectancy_per_trade": float(pnl.mean()) if len(pnl) else None,
            "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
            "average_win": float(wins.mean()) if len(wins) else None,
            "average_loss": float(losses.mean()) if len(losses) else None,
            "profit_factor": float(wins.sum()/gross_loss) if gross_loss else None,
            "profit_factor_status": "defined" if gross_loss else "undefined_no_losing_trades",
            "holding_sessions_mean": float(trades.holding_sessions.mean())
                if len(trades) and "holding_sessions" in trades else None,
            "closed_trade_net_pnl": float(pnl.sum())}


def portfolio_metrics(equity, trades, decisions=None, initial_equity=1000.,
                      operating_cost=0., weekly_limit=20.) -> dict:
    f, trades = _equity(equity), pd.DataFrame(trades)
    out = {"initial_equity": float(initial_equity), "sessions": len(f),
           "operating_cost": float(operating_cost), **_trade_stats(trades)}
    if f.empty:
        out.update({"final_equity": float(initial_equity-operating_cost),
                    "net_pnl": float(-operating_cost), "net_return": -operating_cost/initial_equity if initial_equity else None,
                    "max_drawdown": None, "max_drawdown_dollars": None,
                    "max_drawdown_duration_sessions": 0, "worst_marked_weekly_loss": None,
                    "weekly_breach_count": 0, "weekly_breach_max_magnitude": 0.,
                    "weekly_breach_total_magnitude": 0., "fees": 0., "friction": 0.,
                    "exposure_fraction_sessions": None, "mean_exposure_fraction_equity": None,
                    "turnover": None, "by_year": {}, "by_asset": {},
                    "rejections_by_reason": {}, "unfilled_by_reason": {}})
        return out
    adjusted = _adjusted(f)
    # Include starting capital, even if the first recorded session has a loss.
    values = np.r_[initial_equity, adjusted.to_numpy()]
    peaks = np.maximum.accumulate(values)
    dd = values/peaks - 1
    dd_dollars = values-peaks
    longest = current = 0
    for under_water in dd[1:] < -1e-12:
        current = current + 1 if under_water else 0
        longest = max(current, longest)
    weekly = weekly_dollar_pnl(f, initial_equity)
    if "weekly_loss" in f:
        # IntrawEEK marked loss, not only Friday-to-Friday loss.
        losses = f.weekly_loss.groupby(_week_keys(f)).max().clip(lower=0)
    else:
        daily_delta = adjusted.diff()
        daily_delta.iloc[0] = adjusted.iloc[0] - initial_equity
        losses = (-daily_delta.groupby(_week_keys(f)).cumsum()).groupby(_week_keys(f)).max().clip(lower=0)
    if "weekly_limit" in f:
        budgets = f.weekly_limit.groupby(_week_keys(f))
        if (not np.isfinite(f.weekly_limit).all() or (f.weekly_limit < 0).any() or
            (budgets.nunique() != 1).any()):
            raise ValueError("Weekly budgets must be finite, nonnegative and fixed within each week")
        weekly_budgets = budgets.first()
    else:
        weekly_budgets = pd.Series(float(weekly_limit), index=losses.index)
    breaches = (losses-weekly_budgets).clip(lower=0)
    final = float(adjusted.iloc[-1]-operating_cost)
    fees = float(f.fees.iloc[-1]) if "fees" in f else float(trades.get("fees",pd.Series(dtype=float)).sum())
    friction = float(f.friction.iloc[-1]) if "friction" in f else float(trades.get("friction",pd.Series(dtype=float)).sum())
    notionals = sum(float(trades.get(c,pd.Series(dtype=float)).sum()) for c in ("entry_notional","exit_notional"))
    if decisions is not None and len(decisions):
        fills = pd.DataFrame(decisions)
        if {"status", "fill", "qty"}.issubset(fills.columns):
            fills = fills[fills.status.isin(["filled", "exited"])]
            # Includes buys still open at the evaluation end.
            notionals = float((fills.fill*fills.qty).sum())
    average_equity = float(f.equity.mean())
    out.update({"final_equity": final, "net_pnl": final-initial_equity,
                "net_return": final/initial_equity-1 if initial_equity else None,
                "max_drawdown": float(-dd.min()), "max_drawdown_dollars": float(-dd_dollars.min()),
                "max_drawdown_duration_sessions": longest,
                "worst_marked_weekly_loss": float(losses.max()),
                "weekly_breach_count": int((breaches>1e-8).sum()),
                "weekly_breach_max_magnitude": float(breaches.max()),
                "weekly_breach_total_magnitude": float(breaches.sum()),
                "weekly_risk_budgets": {str(k): float(v) for k,v in weekly_budgets.items()},
                "fees": fees, "friction": friction,
                "exposure_fraction_sessions": float((f.open_positions>0).mean()) if "open_positions" in f else None,
                "mean_exposure_fraction_equity": float((f.exposure/f.equity.replace(0,np.nan)).mean())
                    if "exposure" in f and (f.equity != 0).any() else None,
                "turnover": notionals/average_equity if average_equity else None,
                "turnover_definition": "gross executed buy plus sell notional / mean marked equity",
                "exposure_definition": "daily close marked positions; intraday round trips excluded",
                "asset_attribution_definition": "completed trades only; open marked P/L is portfolio-only",
                "weekly_pnl": {str(k): float(v) for k,v in weekly.items()},
                "by_year": {}, "by_asset": {}, "rejections_by_reason": {}, "unfilled_by_reason": {}})
    prior = float(initial_equity)
    for year, group in adjusted.groupby(adjusted.index.year):
        year_end = float(group.iloc[-1])
        out["by_year"][str(year)] = {"net_pnl": year_end-prior,
                                      "return": year_end/prior-1 if prior else None,
                                      "sessions": len(group)}
        prior = year_end
    if "symbol" in trades:
        out["by_asset"] = {str(k): _trade_stats(g) for k,g in trades.groupby("symbol")}
    if decisions is not None and len(decisions):
        d = pd.DataFrame(decisions)
        if {"status", "reason"}.issubset(d.columns):
            for statuses, key in [(["rejected"], "rejections_by_reason"),
                                   (["unfilled", "cancelled", "expired"], "unfilled_by_reason")]:
                out[key] = {str(k): int(v) for k,v in d[d.status.isin(statuses)].reason.value_counts().items()}
    years = len(f)/252.
    out["annualized_net_dollar_pnl"] = (final-initial_equity)/years if years else None
    out["break_even_annual_operating_cost"] = max(0., (float(adjusted.iloc[-1])-initial_equity)/years)
    return out


def paired_weekly_bootstrap(ridge_equity, trend_equity, initial_equity=1000.,
                            resamples=10000, seed=20261020,
                            block_lengths=(2,4,8)) -> dict:
    """Paired circular moving blocks of portfolio calendar-week dollar P/L.

    Estimand is annualized arithmetic incremental dollars on the original
    starting-capital basis. Weeks (including all-cash weeks) are paired before
    sampling, preserving cross-asset dependence and temporal blocks. Circular
    wraparound avoids systematic underweighting of the beginning/end weeks.
    """
    if resamples <= 0 or any(b <= 0 for b in block_lengths):
        raise ValueError("Resamples and block lengths must be positive")
    r, t = _equity(ridge_equity), _equity(trend_equity)
    if not r.index.equals(t.index):
        raise ValueError("Paired portfolios must have identical session calendars")
    paired = pd.concat([weekly_dollar_pnl(r,initial_equity).rename("ridge"),
                        weekly_dollar_pnl(t,initial_equity).rename("trend")],axis=1)
    if paired.isna().any().any():
        raise ValueError("Paired portfolios must have matching calendar weeks")
    n = len(paired)
    out = {"weeks": n, "resamples": resamples, "seed": seed,
           "method": "paired_circular_calendar_week_moving_block",
           "estimand": "annualized_incremental_dollars_arithmetic_52_weeks",
           "initial_capital_basis": initial_equity, "block_sensitivity": {}}
    difference = (paired.ridge-paired.trend).to_numpy() if n else np.array([])
    out["incremental_net_pnl"] = float(difference.sum())
    out["annualized_incremental_dollars"] = float(difference.mean()*52) if n else None
    out["break_even_annual_incremental_operating_cost"] = max(0.,float(difference.mean()*52)) if n else None
    for block in block_lengths:
        if n < max(2*block, 12):
            out["block_sensitivity"][str(block)] = {"status": "insufficient_weeks", "ci95": None}
            continue
        rng = np.random.default_rng(seed+block)
        # Bound temporary memory, preserving deterministic results across batches.
        statistics = []
        blocks_needed = int(np.ceil(n/block))
        for begin in range(0, resamples, 250):
            count = min(250,resamples-begin)
            starts = rng.integers(0,n,size=(count,blocks_needed))
            indices = ((starts[:,:,None]+np.arange(block)) % n).reshape(count,-1)[:,:n]
            statistics.extend((difference[indices].mean(axis=1)*52).tolist())
        low, high = np.quantile(statistics,[.025,.975])
        out["block_sensitivity"][str(block)] = {"status": "computed", "ci95": [float(low),float(high)]}
    primary = out["block_sensitivity"].get("4", {})
    out["ci95_annualized_incremental_dollars"] = primary.get("ci95")
    out["status"] = primary.get("status", "no_primary_block")
    return out
