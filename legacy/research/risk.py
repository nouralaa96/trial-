"""Pure admission checks. Dollars are simulated USD; losses are never clipped."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd


def riyadh_week(session):
    """US closing session interpreted at 16:00 New York, then Riyadh Mon–Sun."""
    date = pd.Timestamp(session).date()
    close = datetime.combine(date, datetime.min.time()).replace(hour=16, tzinfo=ZoneInfo('America/New_York'))
    local = pd.Timestamp(close.astimezone(ZoneInfo('Asia/Riyadh')))
    return (local - pd.Timedelta(days=local.weekday())).date()


def weekly_required(week_start, equity, entry_costs=0., remaining_risk=0.):
    return max(0., week_start - (equity - entry_costs)) + max(0., remaining_risk)


@dataclass
class RiskController:
    weekly_limit: float = 20.
    floor: float = 160.
    max_trade_fraction: float = .05
    max_positions: int = 3
    max_candidates: int = 2
    session_limit: float = 10.
    max_admissions: int = 1
    week: object = None
    week_start: float = 1000.
    weekly_locked: bool = False
    floor_locked: bool = False
    session: object = None
    considered: int = 0
    admitted: int = 0
    session_risk: float = 0.
    session_risk_fraction: float | None = None
    weekly_risk_fraction: float | None = None
    session_start: float = 1000.

    def __post_init__(self):
        for value in (self.session_risk_fraction, self.weekly_risk_fraction):
            if value is not None and (not math.isfinite(value) or not 0 < value <= 1):
                raise ValueError('Risk budget fractions must be finite and in (0, 1]')

    def update(self, session, equity):
        key = riyadh_week(session)
        if key != self.week:
            self.week, self.week_start, self.weekly_locked = key, equity, False
            if self.weekly_risk_fraction is not None:
                self.weekly_limit = max(0., equity) * self.weekly_risk_fraction
        if pd.Timestamp(session).date() != self.session:
            self.session = pd.Timestamp(session).date()
            self.session_start = equity
            if self.session_risk_fraction is not None:
                self.session_limit = max(0., equity) * self.session_risk_fraction
            self.considered = self.admitted = 0
            self.session_risk = 0.
        if equity <= self.floor + 1e-9:
            self.floor_locked = True
        if self.week_start - equity >= self.weekly_limit - 1e-9:
            self.weekly_locked = True

    def external_flow(self, amount):
        """Adjust weekly reference by deposits/withdrawals, preserving trading P/L."""
        self.week_start += amount

    def consider(self):
        if self.considered >= self.max_candidates:
            return 'daily_candidate_limit'
        self.considered += 1
        return None

    def check(self, *, equity, settled_available, count, all_in_cost, planned_risk,
              net_reward, entry_costs, remaining_risk):
        values = [equity, settled_available, all_in_cost, planned_risk, net_reward,
                  entry_costs, remaining_risk]
        if not all(math.isfinite(x) for x in values) or planned_risk <= 0:
            return 'invalid_risk'
        if self.floor_locked or equity <= self.floor:
            return 'capital_floor'
        if self.weekly_locked:
            return 'weekly_lock'
        if count >= self.max_positions:
            return 'position_limit'
        if self.admitted >= self.max_admissions:
            return 'session_entry_limit'
        if self.session_risk + planned_risk > self.session_limit + 1e-9:
            return 'session_risk_limit'
        if planned_risk > self.max_trade_fraction * equity + 1e-9:
            return 'per_trade_risk'
        if net_reward + 1e-9 < 2 * planned_risk:
            return 'reward_risk'
        if all_in_cost > settled_available + 1e-9:
            return 'settled_cash'
        total = weekly_required(self.week_start, equity, entry_costs, remaining_risk)
        if total > self.weekly_limit + 1e-9:
            return 'weekly_risk'
        if equity - entry_costs - remaining_risk <= self.floor + 1e-9:
            return 'projected_capital_floor'
        return None

    def admit(self, planned_risk):
        self.admitted += 1
        self.session_risk += planned_risk
