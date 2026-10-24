import pandas as pd
import pytest
from diagnostics.cost_attribution import attribute,difference


def fixture():
    # 2 shares: underlying100->105 and$1 dividends yields$11 gross.
    # Fills100.10/104.90 cost$0.40 friction; $2 commissions leave$8.60.
    t=pd.DataFrame([dict(qty=2.,entry_price=100.1,exit_price=104.9,
        dividends=1.,fees=2.,friction=.4,net_pnl=8.6)])
    e=pd.DataFrame([dict(equity=5008.6,open_positions=0,pending_positions=0,fees=2.,friction=.4)])
    return t,e


def test_known_prices_dividend_and_separate_costs():
    s,t=attribute(*fixture())
    assert s['gross_same_trades']==pytest.approx(11.)
    assert s['before_commissions_after_friction']==pytest.approx(10.6)
    assert s['net_pnl']==pytest.approx(8.6)
    assert t.gross_same_trades.iloc[0]==pytest.approx(11.)


def test_cash_no_trades():
    e=pd.DataFrame([dict(equity=5000.,open_positions=0,pending_positions=0,fees=0.,friction=0.)])
    s,_=attribute(pd.DataFrame(),e)
    assert s['gross_same_trades']==0 and s['net_expectancy'] is None


@pytest.mark.parametrize('field,value',[('equity',5000.),('fees',3.),('friction',1.),('open_positions',1)])
def test_inconsistent_or_unfinished_ledger_is_rejected(field,value):
    t,e=fixture();e[field]=value
    with pytest.raises(ValueError):attribute(t,e)


def test_difference_is_gross_gap_minus_cost_gap():
    r={'gross_same_trades':20.,'total_direct_cost':30.,'net_pnl':-10.}
    t={'gross_same_trades':100.,'total_direct_cost':50.,'net_pnl':50.}
    d=difference(r,t)
    assert d['ridge_minus_trend_gross']==-80.
    assert d['ridge_minus_trend_cost']==-20.
    assert d['ridge_minus_trend_net']==-60.
