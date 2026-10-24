import numpy as np
import pandas as pd
import pytest
from experiments.eval_loop import bracket_labels, annual_return, rank_candidates, training_rows, fit_predict
from research.features import FEATURE_COLUMNS


def bars(n=5):
    return pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'atr14':1.,
        'dividends':0.,'splits':0.},index=pd.bdate_range('2020-01-01',periods=n))


def test_bracket_stop_before_target_on_same_bar():
    f=bars();f.loc[f.index[1],['high','low']]=[108,97]
    y=bracket_labels(f,2)
    assert y.label.iloc[0]==pytest.approx(98.5/100-1)
    assert y.label_matured.iloc[0]==f.index[1]


def test_bracket_gap_and_dividend_entitlement():
    f=bars();f.loc[f.index[1],'dividends']=10
    f.loc[f.index[2],['open','low','high','dividends']]=[95,94,101,.5]
    y=bracket_labels(f,2)
    assert y.label.iloc[0]==pytest.approx(95.5/100-1)
    assert y.label_matured.iloc[0]==f.index[2]


def test_bracket_unfilled_is_not_a_zero_return_trade():
    f=bars();f.loc[f.index[1],['open','low','high']]=[105,102,108]
    assert np.isnan(bracket_labels(f,2).label.iloc[0])


def test_intraday_entry_cannot_claim_earlier_target_touch():
    f=bars();f.loc[f.index[1],['open','low','high','close']]=[108,100,110,102]
    f.loc[f.index[2],['open','low','high','close']]=[102,101,103,102]
    y=bracket_labels(f,2)
    assert y.label.iloc[0]==pytest.approx(102/100.5-1)
    assert y.label_matured.iloc[0]==f.index[2]


def test_bracket_bad_entry_immediately_revalidates():
    f=bars();f.loc[f.index[1],['open','low']]=[90,89]
    y=bracket_labels(f,2)
    assert y.label.iloc[0]==0
    assert y.label_matured.iloc[0]==f.index[1]


def test_no_future_labels_fabricated_and_splits_rejected():
    f=bars()
    assert bracket_labels(f,2).label.iloc[-2:].isna().all()
    f.loc[f.index[1],'splits']=2
    with pytest.raises(ValueError,match='split-free'):
        bracket_labels(f,2)


def test_cagr_is_annualized_not_total_return():
    e=pd.DataFrame({'date':['2020-01-01','2022-01-01'],'equity':[100,121]})
    cagr,years=annual_return(e,100)
    assert years==731/365.25
    assert cagr==pytest.approx(1.21**(1/years)-1)
    assert cagr<.11


def test_ranking_penalizes_profit_bought_with_drawdown():
    f=pd.DataFrame({'candidate':['risky','risky','safer','safer'],'cagr':[.25,.20,.12,.11],
        'max_drawdown':[.4,.4,.08,.09]})
    ranked=rank_candidates(f)
    assert list(ranked.candidate)==['safer','risky']
    assert ranked.pass_count.tolist()==[2,0]


def test_training_and_scaling_ignore_future_outcomes():
    dates=pd.bdate_range('2020-01-01',periods=150)
    rng=np.random.default_rng(42)
    rows=pd.DataFrame(rng.normal(size=(150,len(FEATURE_COLUMNS))),columns=FEATURE_COLUMNS)
    rows['date']=dates;rows['label_matured']=pd.Series(dates).shift(-5)
    rows['label']=rows.return_1*.01
    cutoff=dates[100]
    train=training_rows(rows,cutoff)
    p,m=fit_predict(train,rows.iloc[[110]],100)
    changed=rows.copy();changed.loc[changed.date>cutoff,'label']=1000000
    changed.loc[changed.date>cutoff,FEATURE_COLUMNS]=1000000
    train2=training_rows(changed,cutoff)
    p2,m2=fit_predict(train2,rows.iloc[[110]],100)
    assert train.label_matured.max()<=cutoff
    pd.testing.assert_frame_equal(train,train2)
    np.testing.assert_allclose(p,p2,rtol=0,atol=1e-15)
    np.testing.assert_allclose(m.named_steps['scale'].mean_,m2.named_steps['scale'].mean_,rtol=0,atol=1e-15)


def test_label_maturity_purges_partition_crossing_outcomes():
    dates=pd.to_datetime(['2021-12-28','2022-01-03'])
    f=pd.DataFrame({c:[1.,1.] for c in FEATURE_COLUMNS})
    f['date']=dates;f['label_matured']=pd.to_datetime(['2022-01-05','2022-01-10']);f['label']=[.1,.1]
    assert list(training_rows(f,pd.Timestamp('2022-03-01')).index)==[1]


@pytest.mark.parametrize('case',['stop','gap_dividend','intraday','target','time'])
def test_bracket_labels_match_original_execution_kernel_without_costs(case):
    from research.execution import ExecutionEngine
    from research.risk import RiskController
    f=bars();f.index=pd.bdate_range('2020-01-02',periods=len(f))
    if case=='stop':f.loc[f.index[1],['high','low']]=[108,97]
    elif case=='gap_dividend':
        f.loc[f.index[1],'dividends']=10
        f.loc[f.index[2],['open','high','low','close','dividends']]=[95,96,94,95,.5]
    elif case=='intraday':
        f.loc[f.index[1],['open','low','high','close']]=[108,100,110,102]
        f.loc[f.index[2],['open','low','high','close']]=[102,101,103,102]
    elif case=='target':f.loc[f.index[1],'high']=108
    engine=ExecutionEngine(initial_cash=5000,fee=0,slippage=0,max_holding_sessions=2,
        risk=RiskController(week_start=5000,weekly_limit=5000,session_limit=5000,max_trade_fraction=1,floor=0))
    engine.process_bar(f.index[0],{'SPY':f.iloc[0].to_dict()})
    plan=engine.propose('SPY',100,1,1,indicator_date=f.index[0])
    assert plan is not None
    for date,row in f.iloc[1:3].iterrows():engine.process_bar(date,{'SPY':row.to_dict()})
    assert len(engine.trades)==1
    trade=engine.trades[0]
    label=bracket_labels(f,2)
    assert label.label.iloc[0]==pytest.approx(trade['net_pnl']/trade['entry_notional'],abs=1e-12)
    assert label.label_matured.iloc[0]==trade['exit_date']


def test_runner_refuses_to_overwrite_existing_results(tmp_path):
    import subprocess,sys
    from pathlib import Path
    sentinel=tmp_path/'keep.txt';sentinel.write_text('preserve')
    script=Path(__file__).resolve().parent/'run_eval.py'
    result=subprocess.run([sys.executable,str(script),'--output',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==2
    assert 'already exists' in result.stderr
    assert sentinel.read_text()=='preserve'
    assert list(tmp_path.iterdir())==[sentinel]
