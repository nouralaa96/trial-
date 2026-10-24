"""Backtrader completed-bar event driver using the explicit, tested cash ledger.

Cerebro's default broker is deliberately unused. All entries, protection, costs,
settlement and marks are produced by ExecutionEngine; no live broker exists here.
"""
import math
import pandas as pd
import backtrader as bt
from .execution import ExecutionEngine
from .risk import RiskController


def run_backtest(panel, predictions=None, config=None, strategy='ridge', start=None, end=None):
    config = config or {}
    if strategy not in ('ridge','trend','cash'):
        raise ValueError('Unknown strategy')
    fractional = not config.get('whole_shares', not config.get('fractional',False))
    risk = RiskController(weekly_limit=config.get('weekly_budget',20.),
        floor=config.get('capital_floor',160.),max_trade_fraction=config.get('per_trade_risk_fraction',.05),
        max_positions=config.get('max_positions',3),max_candidates=config.get('max_candidates_per_session',2),
        session_limit=config.get('session_risk_budget',10.),max_admissions=config.get('max_entries_per_session',1),
        session_risk_fraction=config.get('session_risk_fraction'),
        weekly_risk_fraction=config.get('weekly_risk_fraction'))
    engine=ExecutionEngine(initial_cash=config.get('initial_equity',config.get('initial_cash',1000.)),
        fee=config.get('fee_per_side',1.09),slippage=config.get('slippage_bps',5.)/10000,
        fractional=fractional,precision=config.get('fractional_precision',6),risk=risk,
        entry_cap_multiplier=config.get('entry_cap_multiplier',1.005),stop_atr=config.get('stop_atr',2.),
        target_atr=config.get('target_atr',6.),max_holding_sessions=config.get('max_holding_sessions',5),
        dividend_payment_lag_days=config.get('dividend_payment_lag_days',30))
    normalized={}
    for symbol, frame in panel.items():
        f=frame.copy()
        f.index=pd.DatetimeIndex(f.index).tz_localize(None).normalize()
        if not f.index.is_unique or not f.index.is_monotonic_increasing:
            raise ValueError('Data must have ordered unique session dates')
        normalized[symbol]=f
    dates=sorted(set().union(*(set(f.index) for f in normalized.values())))
    dates=pd.DatetimeIndex([d for d in dates if (start is None or d>=pd.Timestamp(start)) and (end is None or d<=pd.Timestamp(end))])
    if len(dates)==0:
        return {'equity':pd.DataFrame(), 'trades':pd.DataFrame(), 'decisions':pd.DataFrame()}
    # A union-session clock does not forward-fill or fabricate tradable market bars.
    clock=pd.DataFrame({'open':1.,'high':1.,'low':1.,'close':1.,'volume':0.},index=dates)
    class ResearchStrategy(bt.Strategy):
        def next(self):
            date=pd.Timestamp(self.data.datetime.date(0))
            bars={s:f.loc[date].to_dict() for s,f in normalized.items() if date in f.index}
            engine.process_bar(date,bars)
            ix=dates.get_loc(date)
            # Ten-session separation and five-session full outcome at the endpoint.
            if (strategy!='cash' and ix>=10 and ix<len(dates)-engine.max_holding_sessions and
                date>=pd.Timestamp(config.get('entry_start',dates[0])) and
                date<=pd.Timestamp(config.get('entry_end',dates[-1]))):
                candidates=[]
                for symbol,b in bars.items():
                    try:
                        stamp=b.get('indicator_timestamp')
                        valid=(stamp is not None and not pd.isna(stamp) and
                            bool(b.get('features_valid',False)) and pd.Timestamp(stamp).normalize()==date)
                        own=float(b['close'])>float(b['sma50'])
                        required=('SPY','QQQ') if symbol in ('SPY','QQQ') else ('GLD',)
                        trend=all(s in bars and float(bars[s]['close'])>float(bars[s]['sma50']) and
                            bars[s].get('indicator_timestamp') is not None and
                            not pd.isna(bars[s].get('indicator_timestamp')) and
                            pd.Timestamp(bars[s]['indicator_timestamp']).normalize()==date and
                            bool(bars[s].get('features_valid',False)) for s in required)
                        atr=float(b['atr14'])
                        ret20=float(b.get('return_20',b.get('return_20d',b.get('ret20',float('nan')))))
                        if strategy=='ridge':
                            pred=float(predictions.loc[date,symbol]) if predictions is not None and date in predictions.index and symbol in predictions.columns else float('nan')
                        else:
                            pred=ret20
                        if not valid or not math.isfinite(atr) or atr<=0:
                            engine.log(symbol,'filtered','missing_stale_or_invalid_inputs')
                            continue
                        if not own or not trend:
                            engine.log(symbol,'filtered','trend_filter')
                            continue
                        if not math.isfinite(pred) or pred<=0:
                            engine.log(symbol,'filtered','missing_or_nonpositive_prediction')
                            continue
                        candidates.append((pred/(atr/float(b['close'])),symbol,pred,b))
                    except (ValueError,TypeError,KeyError):
                        engine.log(symbol,'filtered','missing_or_invalid_inputs')
                        continue
                for _,symbol,pred,b in sorted(candidates,key=lambda x:(-x[0],x[1]))[:risk.max_candidates]:
                    engine.propose(symbol,float(b['close']),float(b['atr14']),pred,
                        indicator_date=b.get('indicator_timestamp'),event=bool(b.get('earnings_event',False)))
            engine.snapshot()
    cerebro=bt.Cerebro(stdstats=False)
    cerebro.adddata(bt.feeds.PandasData(dataname=clock))
    cerebro.addstrategy(ResearchStrategy)
    cerebro.run(runonce=False,preload=True)
    # No terminal forced sale: full equity includes any marked holdings/receivables.
    return {'equity':pd.DataFrame(engine.equity_log), 'trades':pd.DataFrame(engine.trades),
            'decisions':pd.DataFrame(engine.decisions)}
