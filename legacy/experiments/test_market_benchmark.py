import pandas as pd
import pytest
from experiments.market_benchmark import buy_hold


def test_whole_shares_cash_fees_and_dividend_entitlement():
    f=pd.DataFrame({'open':[100,110,120],'close':[100,110,120],
        'dividends':[10,1,0],'splits':[1,1,1]},index=pd.bdate_range('2024-01-02',periods=3))
    e,q=buy_hold({'A':f},initial=1000,fee=1,slip=0)
    assert q=={'A':9}
    assert e.equity.iloc[0]==999
    assert e.equity.iloc[-1]==1187  #99cash+1080stock+9dividend-1exitfee


def test_equal_initial_sleeves_use_separate_order_fees():
    f=pd.DataFrame({'open':[100,100],'close':[100,100],
        'dividends':[0,0],'splits':[1,1]},index=pd.bdate_range('2024-01-02',periods=2))
    e,q=buy_hold({'A':f,'B':f},initial=1000,fee=1,slip=0)
    assert q=={'A':4,'B':4}
    assert e.equity.iloc[-1]==996


def test_split_requires_adjustment_not_silent_false_return():
    f=pd.DataFrame({'open':[100,50],'close':[100,50],
        'dividends':[0,0],'splits':[1,2]},index=pd.bdate_range('2024-01-02',periods=2))
    with pytest.raises(ValueError,match='Split adjustment'):
        buy_hold({'A':f})
