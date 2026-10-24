"""Standalone V4 event driver over the byte-preserved V2 cash ledger.

No broker connection. Imports are rooted in the local legacy namespace so the
module works independently of any original project or current working directory.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import pandas as pd
from legacy.research.execution import ExecutionEngine, ExchangeCalendar
from legacy.research.risk import RiskController

ROOT = Path(__file__).resolve().parent


def make_engine(config=None):
    c = config or {}
    risk = RiskController(weekly_limit=c.get('weekly_budget', 750.),
        floor=c.get('capital_floor', 160.),
        max_trade_fraction=c.get('per_trade_risk_fraction', .05),
        max_positions=c.get('max_positions', 3),
        max_candidates=c.get('max_candidates_per_session', 2),
        session_limit=c.get('session_risk_budget', 250.),
        max_admissions=c.get('max_entries_per_session', 1),
        session_risk_fraction=c.get('session_risk_fraction', .05),
        weekly_risk_fraction=c.get('weekly_risk_fraction', .15))
    return ExecutionEngine(initial_cash=c.get('initial_equity', 5000.),
        fee=c.get('fee_per_side', 1.09), slippage=c.get('slippage_bps', 5.)/10000,
        fractional=not c.get('whole_shares', True), precision=c.get('fractional_precision', 6),
        risk=risk, entry_cap_multiplier=c.get('entry_cap_multiplier', 1.005),
        stop_atr=c.get('stop_atr', 2.), target_atr=c.get('target_atr', 6.),
        max_holding_sessions=c.get('max_holding_sessions', 20),
        dividend_payment_lag_days=c.get('dividend_payment_lag_days', 30))


def normalize_panel(panel):
    normalized = {}
    for symbol, frame in panel.items():
        f = frame.copy()
        f.index = pd.DatetimeIndex(f.index).tz_localize(None).normalize()
        if not f.index.is_unique or not f.index.is_monotonic_increasing:
            raise ValueError('Data must have ordered unique session dates')
        normalized[symbol] = f
    return normalized


def submit_candidates(engine, bars, predictions, date, strategy='ridge', trend_filter=True):
    """Completed-close decisions; at most two considered, one admitted per session."""
    candidates = []
    for symbol, b in bars.items():
        try:
            stamp = b.get('indicator_timestamp')
            valid = (stamp is not None and not pd.isna(stamp) and bool(b.get('features_valid', False))
                and pd.Timestamp(stamp).normalize() == date)
            required = ('SPY', 'QQQ') if symbol in ('SPY', 'QQQ') else ('GLD',)
            own = float(b['close']) > float(b['sma50'])
            trend = all(s in bars and float(bars[s]['close']) > float(bars[s]['sma50']) and
                bars[s].get('indicator_timestamp') is not None and
                not pd.isna(bars[s].get('indicator_timestamp')) and
                pd.Timestamp(bars[s]['indicator_timestamp']).normalize() == date and
                bool(bars[s].get('features_valid', False)) for s in required)
            atr = float(b['atr14'])
            if strategy == 'ridge' or predictions is not None:
                pred = float(predictions.loc[date, symbol]) if predictions is not None and date in predictions.index and symbol in predictions else float('nan')
            else:
                pred = float(b.get('return_20', b.get('return_20d', b.get('ret20', float('nan')))))
            if not valid or not math.isfinite(atr) or atr <= 0:
                engine.log(symbol, 'filtered', 'missing_stale_or_invalid_inputs')
            elif trend_filter and (not own or not trend):
                engine.log(symbol, 'filtered', 'trend_filter')
            elif not math.isfinite(pred) or pred <= 0:
                engine.log(symbol, 'filtered', 'missing_or_nonpositive_prediction')
            else:
                candidates.append((pred/(atr/float(b['close'])), symbol, pred, b))
        except (ValueError, TypeError, KeyError):
            engine.log(symbol, 'filtered', 'missing_or_invalid_inputs')
    for _, symbol, pred, b in sorted(candidates, key=lambda x: (-x[0], x[1]))[:engine.risk.max_candidates]:
        engine.propose(symbol, float(b['close']), float(b['atr14']), pred,
            indicator_date=b.get('indicator_timestamp'), event=bool(b.get('earnings_event', False)))


def run_engine(panel, predictions=None, config=None, strategy='ridge', start=None, end=None,
               trend_filter=True, return_engine=False, replay_through=None):
    """Same bar ordering, endpoint embargo and outputs as inherited run_backtest.

    Forecast gating is represented by NaN predictions. An explicitly declared
    entry-filter ablation may pass trend_filter=False. No fitting happens here.
    """
    if strategy not in ('ridge', 'trend', 'cash'):
        raise ValueError('Unknown strategy')
    c = config or {}
    engine = make_engine(c)
    panel = normalize_panel(panel)
    dates = pd.DatetimeIndex(sorted(set().union(*(set(f.index) for f in panel.values()))))
    dates = dates[(dates >= pd.Timestamp(start or dates[0])) & (dates <= pd.Timestamp(end or dates[-1]))]
    for ix, date in enumerate(dates):
        if replay_through is not None and date > pd.Timestamp(replay_through):
            break
        bars = {s: f.loc[date].to_dict() for s, f in panel.items() if date in f.index}
        engine.process_bar(date, bars)
        if (strategy != 'cash' and ix >= 10 and ix < len(dates)-engine.max_holding_sessions
                and date >= pd.Timestamp(c.get('entry_start', dates[0]))
                and date <= pd.Timestamp(c.get('entry_end', dates[-1]))):
            submit_candidates(engine, bars, predictions, date, strategy, trend_filter)
        engine.snapshot()
    result = dict(equity=pd.DataFrame(engine.equity_log), trades=pd.DataFrame(engine.trades),
                  decisions=pd.DataFrame(engine.decisions))
    if return_engine:
        result['engine'] = engine
    return result


def benchmark(panelSPY, config=None, start=None, end=None, reinvest=False):
    """Cash-only SPY passive reference, entry/final liquidation costs, dividends.

    Reinvestment uses cash after assumed 30-calendar-day payout at that day's open,
    charges a fresh buy fee and respects whole/fractional shares. Ex-date entitlement
    belongs only to shares held before the opening purchase. No future adjusted
    prices or instantaneous ex-date reinvestment is used. Historical splits apply.
    """
    c = config or {}
    frame = panelSPY['SPY'] if isinstance(panelSPY, dict) else panelSPY
    f = frame.loc[start:end].copy()
    if f.empty:
        return dict(equity=pd.DataFrame(), trades=pd.DataFrame(), decisions=pd.DataFrame())
    initial = float(c.get('initial_equity', 5000.))
    fee, slip = c.get('fee_per_side', 1.09), c.get('slippage_bps', 5.)/10000
    cash, qty, fees, friction, dividends = initial, 0., 0., 0., 0.
    unsettled, logs, decisions = [], [], []
    cal = ExchangeCalendar()
    precision = 1 if c.get('whole_shares', True) else 10**c.get('fractional_precision', 6)
    for i, (date, b) in enumerate(f.iterrows()):
        date = pd.Timestamp(date)
        split = float(b.get('splits', 0.) or 0.)
        if split and split != 1:
            qty *= split
        div = qty*float(b.get('dividends', 0.) or 0.)
        if div:
            dividends += div
            pay = cal.on_or_after(date+pd.Timedelta(days=c.get('dividend_payment_lag_days', 30)))
            unsettled.append((pay, div))
        matured = sum(v for d, v in unsettled if d <= date)
        cash += matured
        unsettled = [(d, v) for d, v in unsettled if d > date]
        if i == 0 or (reinvest and matured > 0):
            raw, fill = float(b['open']), float(b['open'])*(1+slip)
            buy = math.floor(max(0., cash-fee)/fill*precision)/precision
            if buy > 0:
                qty += buy
                cash -= buy*fill+fee
                fees += fee
                friction += buy*(fill-raw)
                decisions.append(dict(date=date, symbol='SPY', status='filled', reason='passive_reinvestment' if i else 'passive_entry', qty=buy, fill=fill))
        equity = cash+sum(v for _, v in unsettled)+qty*float(b['close'])
        if i == len(f)-1 and qty:
            raw, fill = float(b['close']), float(b['close'])*(1-slip)
            cash += qty*fill-fee
            fees += fee
            friction += qty*(raw-fill)
            decisions.append(dict(date=date, symbol='SPY', status='exited', reason='passive_terminal_liquidation', qty=qty, fill=fill))
            qty = 0.
            equity = cash+sum(v for _, v in unsettled)
        logs.append(dict(date=date, equity=equity, cash=cash+sum(v for _, v in unsettled), settled_cash=cash,
                         unsettled_cash=sum(v for _, v in unsettled), exposure=qty*float(b['close']),
                         open_positions=int(qty > 0), pending_positions=0, fees=fees, friction=friction,
                         weekly_loss=0., weekly_required=0., weekly_limit=initial, passive_risk_policy_applies=False))
    trade = dict(symbol='SPY', entry_date=f.index[0], exit_date=f.index[-1], net_pnl=equity-initial,
                 pnl=equity-initial, fees=fees, friction=friction, dividends=dividends,
                 reason='passive_terminal_liquidation', holding_sessions=len(f))
    return dict(equity=pd.DataFrame(logs), trades=pd.DataFrame([trade]), decisions=pd.DataFrame(decisions))
