"""Explicit cash-account kernel. Backtrader is an event clock, not this ledger's broker.

No partial fills: any requested partial-fill event raises NotImplementedError.
Dividends accrue on ex-date and settle after an assumed 30-calendar-day lag.
"""
from dataclasses import dataclass, asdict, replace
import hashlib
import json
import math
import numpy as np
import pandas as pd
from .risk import RiskController, weekly_required, riyadh_week


class ReservationError(ValueError):
    pass


@dataclass(frozen=True)
class EntryPlan:
    symbol: str
    submitted: pd.Timestamp
    execute: pd.Timestamp
    qty: float
    cap: float
    stop: float
    target: float
    planned_risk: float
    cash: float
    entry_cost: float
    prediction: float = 0.

    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), default=str, sort_keys=True).encode()).hexdigest()


@dataclass
class Position:
    symbol: str
    qty: float
    entry: float
    stop: float
    target: float
    entry_date: pd.Timestamp
    entry_fee: float
    entry_friction: float
    initial_risk: float
    cost_basis: float
    sessions: int = 0
    dividends: float = 0.


class ExchangeCalendar:
    def __init__(self):
        import exchange_calendars as xc
        self.calendar = xc.get_calendar('XNYS', start='2009-01-01', end='2028-12-31')
        self.sessions = self.calendar.sessions.tz_localize(None)

    def next(self, date, n=1):
        date = pd.Timestamp(date).normalize().tz_localize(None)
        idx = self.sessions.searchsorted(date, side='right') + n - 1
        if idx >= len(self.sessions):
            raise ValueError('Exchange calendar exhausted')
        return self.sessions[idx]

    def on_or_after(self, date):
        return self.sessions[self.sessions.searchsorted(pd.Timestamp(date).normalize().tz_localize(None))]

    def settlement(self, date):
        date = pd.Timestamp(date).normalize()
        lag = 3 if date < pd.Timestamp('2017-09-05') else (2 if date < pd.Timestamp('2024-05-28') else 1)
        return self.next(date, lag)


class ExecutionEngine:
    def __init__(self, initial_cash=1000., fee=1.09, slippage=.0005,
                 fractional=False, precision=6, calendar=None, risk=None,
                 entry_cap_multiplier=1.005, stop_atr=2., target_atr=6.,
                 max_holding_sessions=5, dividend_payment_lag_days=30):
        if fee < 0 or not 0 <= slippage < 1:
            raise ValueError('Invalid costs')
        if not (entry_cap_multiplier >= 1 and 0 < stop_atr < target_atr and max_holding_sessions >= 1):
            raise ValueError('Invalid frozen execution parameters')
        self.entry_cap_multiplier, self.stop_atr, self.target_atr = entry_cap_multiplier, stop_atr, target_atr
        self.max_holding_sessions, self.dividend_payment_lag_days = max_holding_sessions, dividend_payment_lag_days
        self.initial_cash = float(initial_cash)
        self.settled = float(initial_cash)
        self.unsettled = []
        self.fee, self.slippage = float(fee), float(slippage)
        self.fractional, self.precision = fractional, precision
        self.calendar = calendar or ExchangeCalendar()
        self.risk = risk or RiskController(week_start=initial_cash)
        self.positions, self.pending, self.seals, self.marks = {}, {}, {}, {}
        self.trades, self.decisions, self.equity_log = [], [], []
        self.total_fees = self.total_friction = self.external_flows = 0.
        self.date = None
        self.session_max_weekly_loss = 0.
        self.mandatory_exit = None
        self.session_max_weekly_required = 0.

    @property
    def cash(self):
        return self.settled + sum(x[1] for x in self.unsettled)

    @property
    def equity(self):
        return self.cash + sum(p.qty * self.marks.get(s, p.entry) for s, p in self.positions.items())

    def verify(self):
        if set(self.pending) != set(self.seals):
            raise ReservationError('Reservation registry mismatch')
        for s, p in self.pending.items():
            if p.digest() != self.seals[s]:
                raise ReservationError('Tampered reservation')
            risk = p.qty * (p.cap - p.stop * (1-self.slippage)) + 2*self.fee
            cash = p.qty * p.cap + self.fee
            cost = self.fee + p.qty * (p.cap-p.cap/(1+self.slippage))
            if not (p.qty > 0 and 0 < p.stop < p.cap < p.target and
                    abs(p.planned_risk-risk) < 1e-7 and abs(p.cash-cash) < 1e-7 and
                    abs(p.entry_cost-cost) < 1e-7):
                raise ReservationError('Inconsistent reservation')
        if sum(p.cash for p in self.pending.values()) > self.settled + 1e-7:
            raise ReservationError('Reservations exceed settled cash')

    def remaining(self):
        open_risk = sum(max(0., p.qty*(self.marks.get(s, p.entry)-p.stop*(1-self.slippage))+self.fee)
                        for s,p in self.positions.items())
        costs = sum(p.entry_cost for p in self.pending.values())
        pending_risk = sum(p.planned_risk-p.entry_cost for p in self.pending.values())
        return costs, open_risk+pending_risk

    def external_flow(self, amount):
        if self.settled + amount < 0:
            raise ValueError('Withdrawal exceeds settled cash')
        self.settled += amount
        self.external_flows += amount
        self.risk.external_flow(amount)

    def log(self, symbol, status, reason, **kwargs):
        self.decisions.append(dict(date=self.date, symbol=symbol, status=status, reason=reason, **kwargs))

    def cancel(self, symbol, reason='cancelled'):
        self.verify()
        plan = self.pending.pop(symbol)
        self.seals.pop(symbol)
        self.log(symbol, 'cancelled', reason, qty=plan.qty)
        # Session admission and risk allowances deliberately remain consumed.

    def partial_fill(self, *args, **kwargs):
        raise NotImplementedError('Partial fills are unsupported; only full fills or cancellation')

    def propose(self, symbol, close, atr, prediction=1., indicator_date=None, event=False):
        self.verify()
        rejected = self.risk.consider()
        if rejected:
            self.log(symbol, 'rejected', rejected)
            return None
        if indicator_date is None or pd.Timestamp(indicator_date).normalize() != self.date:
            rejected = 'stale_missing_or_future_indicator'
        elif event:
            rejected = 'earnings_or_event'
        elif symbol in self.positions or symbol in self.pending:
            rejected = 'already_held_or_pending'
        elif not all(math.isfinite(x) and x > 0 for x in (close, atr, prediction)):
            rejected = 'invalid_indicator_or_prediction'
        else:
            rejected = None
        if rejected:
            self.log(symbol, 'rejected', rejected)
            return None
        cap = close*self.entry_cap_multiplier
        stop, target = cap-self.stop_atr*atr, cap+self.target_atr*atr
        if not 0 < stop < cap < target:
            self.log(symbol, 'rejected', 'invalid_bracket')
            return None
        available = self.settled - sum(p.cash for p in self.pending.values())
        costs, remaining = self.remaining()
        loss_per = cap-stop*(1-self.slippage)
        entry_cost_per = cap-cap/(1+self.slippage)
        room = min(self.risk.session_limit-self.risk.session_risk,
                   self.risk.max_trade_fraction*self.equity,
                   self.risk.weekly_limit-weekly_required(self.risk.week_start,self.equity,costs,remaining))
        # Cash capacity can bind before the allowed risk budget is exhausted.
        cash_qty = (available-self.fee)/cap
        risk_qty = (room-2*self.fee)/loss_per
        floor_qty = (self.equity-self.risk.floor-2*self.fee-remaining-costs)/loss_per
        cash_constrained = cash_qty < min(risk_qty, floor_qty)-1e-9
        qty = min(cash_qty, risk_qty, floor_qty)
        scale = 10**self.precision if self.fractional else 1
        qty = math.floor(max(0., qty)*scale+1e-10)/scale
        planned = qty*loss_per+2*self.fee
        reward = qty*(target*(1-self.slippage)-cap)-2*self.fee
        entry_cost = self.fee+qty*entry_cost_per
        if qty <= 0:
            rejected = 'insufficient_cash_or_risk_capacity'
        elif prediction * qty * cap <= 2*self.fee + qty*cap*2*self.slippage:
            rejected = 'nonpositive_net_prediction'
        else:
            rejected = self.risk.check(equity=self.equity, settled_available=available,
                count=len(self.positions)+len(self.pending), all_in_cost=qty*cap+self.fee,
                planned_risk=planned, net_reward=reward,
                entry_costs=costs+entry_cost, remaining_risk=remaining+planned-entry_cost)
        if rejected:
            self.log(symbol, 'rejected', rejected, qty=qty, planned_risk=planned)
            return None
        p = EntryPlan(symbol,self.date,self.calendar.next(self.date),qty,cap,stop,target,planned,
                      qty*cap+self.fee,entry_cost,prediction)
        self.pending[symbol], self.seals[symbol] = p, p.digest()
        self.risk.admit(planned)
        self.log(symbol,'admitted','price_capped_next_session',
            equity_at_admission=self.equity,settled_available=available,net_reward=reward,
            session_budget_at_admission=self.risk.session_limit,
            weekly_budget_at_admission=self.risk.weekly_limit,
            session_start_equity=self.risk.session_start,week_start_equity=self.risk.week_start,
            per_trade_budget_at_admission=self.risk.max_trade_fraction*self.equity,
            risk_room_at_admission=room,cash_constrained=cash_constrained,
            existing_count=len(self.positions)+len(self.pending)-1,
            projected_weekly_required=weekly_required(self.risk.week_start,self.equity,
                costs+entry_cost,remaining+planned-entry_cost),
            session_risk_after=self.risk.session_risk,session_admissions_after=self.risk.admitted,
            considered_today=self.risk.considered,
            **{k:v for k,v in asdict(p).items() if k not in ('symbol',)})
        self.verify()
        return p

    def _observe(self):
        self.risk.update(self.date,self.equity)
        self.session_max_weekly_loss = max(self.session_max_weekly_loss,
            max(0.,self.risk.week_start-self.equity))

    def _sell(self, symbol, raw_price, reason, limit=None):
        p = self.positions.pop(symbol)
        fill = raw_price*(1-self.slippage)
        if limit is not None:
            fill = max(limit, fill)
        proceeds = p.qty*fill-self.fee
        self.unsettled.append((self.calendar.settlement(self.date),proceeds,'sale'))
        friction = p.qty*max(0.,raw_price-fill)
        self.total_fees += self.fee
        self.total_friction += friction
        pnl = proceeds-p.cost_basis+p.dividends
        self.trades.append(dict(symbol=symbol,entry_date=p.entry_date,exit_date=self.date,
            qty=p.qty,entry_price=p.entry,exit_price=fill,pnl=pnl,net_pnl=pnl,
            fees=p.entry_fee+self.fee,friction=p.entry_friction+friction,
            dividends=p.dividends,holding_sessions=p.sessions,reason=reason,initial_risk=p.initial_risk,
            entry_notional=p.cost_basis-p.entry_fee,exit_notional=p.qty*fill))
        self.log(symbol,'exited',reason,fill=fill,qty=p.qty)
        self._observe()

    def _risk_breach(self):
        costs,remaining=self.remaining()
        required = weekly_required(self.risk.week_start,self.equity,costs,remaining)
        self.session_max_weekly_required = max(self.session_max_weekly_required,required)
        weekly = required>self.risk.weekly_limit+1e-8
        floor = self.risk.floor_locked or self.equity-costs-remaining <= self.risk.floor+1e-9
        if weekly:
            self.risk.weekly_locked=True
        if floor:
            self.risk.floor_locked=True
        return weekly, floor

    def _enforce_open(self, bars):
        weekly,floor=self._risk_breach()
        reason = self.mandatory_exit or ('capital_floor_open' if floor else 'weekly_protective_risk_open')
        must_exit = bool(self.mandatory_exit) or weekly or floor or self.risk.weekly_locked
        if must_exit:
            self.log('', 'risk_control',reason,observed_equity=self.equity,
                observed_weekly_required=weekly_required(self.risk.week_start,self.equity,*self.remaining()),
                projected_risk_excess=max(0.,weekly_required(self.risk.week_start,self.equity,*self.remaining())-self.risk.weekly_limit))
            for symbol in list(self.pending):
                self.cancel(symbol,'pre_fill_risk_revalidation')
            for symbol in list(self.positions):
                self.positions[symbol].sessions += 1
                self._sell(symbol,float(bars[symbol]['open']),reason)
            self.mandatory_exit=None

    def _enforce_close(self):
        weekly,floor=self._risk_breach()
        if weekly or floor or self.risk.weekly_locked:
            for symbol in list(self.pending):
                self.cancel(symbol,'close_risk_revalidation')
            if self.positions:
                self.mandatory_exit='capital_floor_next_open' if floor else 'weekly_protective_risk_next_open'
                self.log('', 'mandatory_exit_queued',self.mandatory_exit,
                    observed_equity=self.equity,observed_weekly_required=weekly_required(
                        self.risk.week_start,self.equity,*self.remaining()))

    def _corporate_actions(self, bars):
        for symbol,bar in bars.items():
            split = float(bar.get('splits', bar.get('stock_splits', 0.)) or 0.)
            if split and split != 1:
                if not math.isfinite(split) or split <= 0:
                    raise ValueError('Invalid split')
                if symbol in self.positions:
                    p = self.positions[symbol]
                    p.qty *= split
                    p.entry /= split
                    p.stop /= split
                    p.target /= split
                    self.marks[symbol] = self.marks.get(symbol,p.entry*split)/split
                if symbol in self.pending:
                    p = self.pending[symbol]
                    p = replace(p,qty=p.qty*split,cap=p.cap/split,stop=p.stop/split,target=p.target/split)
                    self.pending[symbol],self.seals[symbol] = p,p.digest()
            div = float(bar.get('dividends',0.) or 0.)
            if div and symbol in self.positions:
                amount = self.positions[symbol].qty*div
                self.positions[symbol].dividends += amount
                pay = self.calendar.on_or_after(self.date+pd.Timedelta(days=self.dividend_payment_lag_days))
                self.unsettled.append((pay,amount,'dividend_receivable'))

    def process_bar(self, date, bars):
        """Process only completed OHLC bars; future decisions are submitted afterward."""
        self.verify()
        self.date = pd.Timestamp(date).normalize().tz_localize(None)
        self.session_max_weekly_loss = 0.
        self.session_max_weekly_required = 0.
        matured = [x for x in self.unsettled if x[0] <= self.date]
        self.settled += sum(x[1] for x in matured)
        self.unsettled = [x for x in self.unsettled if x[0] > self.date]
        # Reset reference at prior marked equity before today's prices or actions.
        self.risk.update(self.date,self.equity)
        self._corporate_actions(bars)
        for symbol, p in self.positions.items():
            if symbol not in bars:
                raise ValueError(f'Missing held-asset bar for {symbol} on {self.date}')
            self.marks[symbol] = float(bars[symbol]['open'])
        self._observe()
        self._enforce_open(bars)
        entered_intraday = set()
        for symbol in list(self.pending):
            p = self.pending[symbol]
            if p.execute > self.date:
                continue
            if p.execute < self.date or symbol not in bars:
                self.cancel(symbol,'expired_missing_session')
                continue
            b=bars[symbol]
            if float(b['low']) > p.cap:
                self.cancel(symbol,'unfilled_price_cap')
                continue
            if float(b['open']) > p.cap:
                entered_intraday.add(symbol)
            raw = float(b['open']) if float(b['open']) <= p.cap else p.cap
            fill = min(p.cap,raw*(1+self.slippage))
            self.pending.pop(symbol)
            self.seals.pop(symbol)
            self.settled -= p.qty*fill+self.fee
            friction = p.qty*max(0.,fill-raw)
            self.total_fees += self.fee
            self.total_friction += friction
            pos = Position(symbol,p.qty,fill,p.stop,p.target,self.date,self.fee,friction,
                           p.planned_risk,p.qty*fill+self.fee)
            self.positions[symbol]=pos
            self.marks[symbol]=raw
            actual_risk = p.qty*(fill-p.stop*(1-self.slippage))+2*self.fee
            reward = p.qty*(p.target*(1-self.slippage)-fill)-2*self.fee
            self._observe()
            actual_trade_limit = self.risk.max_trade_fraction*self.equity
            self.log(symbol,'filled','entry',fill=fill,qty=p.qty,actual_risk=actual_risk,
                equity_at_fill=self.equity,per_trade_budget_at_fill=actual_trade_limit)
            costs,remaining=self.remaining()
            invalid = not p.stop < fill < p.target or reward+1e-9 < 2*actual_risk
            if (invalid or actual_risk>p.planned_risk+1e-8 or
                actual_risk>actual_trade_limit+1e-8 or
                weekly_required(self.risk.week_start,self.equity,costs,remaining)>self.risk.weekly_limit+1e-8):
                self._sell(symbol,raw,'actual_fill_revalidation_exit')
        for symbol in list(self.positions):
            p=self.positions[symbol]
            if symbol not in bars:
                raise ValueError(f'Missing held-asset bar for {symbol} on {self.date}')
            b=bars[symbol]
            p.sessions += 1
            op,lo,hi,cl = (float(b[k]) for k in ('open','low','high','close'))
            # Stop-first even if a target also touched, including entry bars.
            if op <= p.stop and symbol not in entered_intraday:
                self._sell(symbol,op,'opening_gap_stop')
            elif lo <= p.stop:
                self._sell(symbol,p.stop,'stop')
            elif op >= p.target and symbol not in entered_intraday:
                self._sell(symbol,op,'opening_gap_target',limit=p.target)
            elif hi >= p.target and symbol not in entered_intraday:
                self._sell(symbol,p.target,'target',limit=p.target)
            elif p.sessions >= self.max_holding_sessions:
                self._sell(symbol,cl,'time_exit')
            else:
                self.marks[symbol]=cl
        self._observe()
        self._enforce_close()
        self.verify()
        return self.equity

    def assert_accounting(self):
        expected = self.initial_cash+self.external_flows+sum(t['net_pnl'] for t in self.trades)
        expected += sum(p.qty*self.marks.get(s,p.entry)-p.cost_basis+p.dividends
                        for s,p in self.positions.items())
        if not math.isfinite(self.equity) or abs(self.equity-expected)>1e-6:
            raise AssertionError(f'Ledger mismatch: marked equity {self.equity}, reconciliation {expected}')
        return expected

    def snapshot(self):
        self.assert_accounting()
        costs,remaining=self.remaining()
        record=dict(date=self.date,week=str(riyadh_week(self.date)),equity=self.equity,cash=self.cash,settled_cash=self.settled,
            unsettled_cash=sum(x[1] for x in self.unsettled),reserved_cash=sum(p.cash for p in self.pending.values()),
            open_positions=len(self.positions),pending_positions=len(self.pending),
            exposure=sum(p.qty*self.marks[s] for s,p in self.positions.items()),
            fees=self.total_fees,friction=self.total_friction,external_flows=self.external_flows,
            week_start_equity=self.risk.week_start,weekly_loss=self.session_max_weekly_loss,
            weekly_limit=self.risk.weekly_limit,session_limit=self.risk.session_limit,
            session_start_equity=self.risk.session_start,
            close_weekly_loss=max(0.,self.risk.week_start-self.equity),
            weekly_required=weekly_required(self.risk.week_start,self.equity,costs,remaining),
            weekly_locked=self.risk.weekly_locked,floor_locked=self.risk.floor_locked,
            mandatory_exit_pending=bool(self.mandatory_exit),mandatory_exit_reason=self.mandatory_exit,
            observed_weekly_required=self.session_max_weekly_required,
            projected_risk_excess=max(0.,self.session_max_weekly_required-self.risk.weekly_limit))
        self.equity_log.append(record)
        return record
