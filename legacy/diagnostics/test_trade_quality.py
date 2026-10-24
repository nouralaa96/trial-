from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from diagnostics.trade_quality import drawdowns, loss_streak, trade_path


def test_drawdown_includes_start_and_unrecovered_tail():
    f=pd.DataFrame({'date':pd.date_range('2020-01-01',periods=6),'equity':[90,80,100,120,108,114]})
    episodes,longest=drawdowns(f,100)
    assert longest==2
    assert episodes[0]['drawdown_pct']==pytest.approx(20)
    assert episodes[0]['recovered'] is True
    assert episodes[0]['recovery_date']=='2020-01-03'
    assert episodes[1]['drawdown_pct']==pytest.approx(10)
    assert episodes[1]['recovery_date'] is None
    assert episodes[1]['recovered'] is False


def test_streak_zero_resets_and_order_is_preserved():
    f=pd.DataFrame({'exit_date':pd.date_range('2020-01-01',periods=7),'net_pnl':[-2,-3,0,-1,2,-4,-6]})
    s=loss_streak(f)
    assert s['count']==2 and s['net_pnl']==-10
    assert s['start']=='2020-01-06'


def fixture():
    dates=pd.date_range('2020-01-01',periods=10,freq='B')
    f=pd.DataFrame({'close':[101,104,70,104,105,106,107,108,109,110],
        'dividends':[10,1,0,0,0,0,0,0,0,0],'splits':0},index=dates)
    t=SimpleNamespace(entry_date=dates[0],exit_date=dates[2],qty=2,entry_notional=200,
        net_pnl=-10.,fees=2.,friction=1.)
    return t,f


def test_close_path_excludes_exit_bar_and_entry_ex_dividend():
    t,f=fixture()
    r=trade_path(t,f,1,0,'2020-01-31')
    # day1 2*101-200-2=0; day2 2*104-200+2*1-2=8;
    # exit bar close70 occurs after a stop; use actual -10, not fictitious -60.
    assert r['close_mfe_dollars']==8
    assert r['close_mae_dollars']==10
    assert r['loss_after_positive_close']
    assert r['fixed5_net']==10
    assert r['post5_net_if_held']==16
    assert r['post5_delta']==26


def test_post_exit_does_not_cross_partition_boundary():
    t,f=fixture()
    r=trade_path(t,f,1,0,str(f.index[5].date()))
    assert np.isnan(r['post5_delta'])
    assert r['post5_better'] is None
    assert r['fixed5_net']==10


def test_same_day_exit_has_no_fictitious_close_observation():
    t,f=fixture()
    t.exit_date=t.entry_date
    r=trade_path(t,f,1,0,'2020-01-31')
    assert r['close_observation_count']==0
    assert r['close_mfe_dollars']==0
    assert r['close_mae_dollars']==10


def test_splits_require_explicit_adjustment():
    t,f=fixture()
    f.loc[f.index[3],'splits']=2
    with pytest.raises(ValueError,match='Split-aware'):
        trade_path(t,f,1,0,'2020-01-31')


def test_rolling_training_purges_future_maturity_and_old_history():
    from diagnostics.improvement_trials import rolling_training
    from research.features import FEATURE_COLUMNS
    f=pd.DataFrame({'date':pd.to_datetime(['2017-01-01','2018-06-15','2020-06-01','2021-06-14','2021-06-16']),
        'label_matured':pd.to_datetime(['2017-01-06','2018-06-22','2020-06-08','2021-06-21','2021-06-23']),
        'label':[.1]*5,**{c:[1.]*5 for c in FEATURE_COLUMNS}})
    out=rolling_training(f,pd.Timestamp('2021-06-15'))
    assert list(out.index)==[1,2]
    assert out.label_matured.max()<=pd.Timestamp('2021-06-15')


def test_rolling_training_preserves_partition_purge():
    from diagnostics.improvement_trials import rolling_training
    from research.features import FEATURE_COLUMNS
    f=pd.DataFrame({'date':pd.to_datetime(['2021-12-28','2022-01-03']),
        'label_matured':pd.to_datetime(['2022-01-05','2022-01-10']),
        'label':[.1,.1],**{c:[1.,1.] for c in FEATURE_COLUMNS}})
    assert list(rolling_training(f,pd.Timestamp('2022-03-01')).index)==[1]


def test_roundoff_is_not_mistaken_for_gross_trading_edge():
    t,f=fixture()
    t.net_pnl=-3.0000000000001
    r=trade_path(t,f,1,0,'2020-01-31')
    assert r['gross_flat_net_loss']
    assert not r['gross_losing_trade']
    assert not r['cost_flipped_loss']
