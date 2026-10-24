"""Meaningful replay, stale-input, chronology and cash-control regression checks."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from execution_adapter import make_engine,run_engine,benchmark,submit_candidates
from legacy.research.execution import ExchangeCalendar,ReservationError
from legacy.research.features import build_features
from legacy.research.backtest import run_backtest
from paper import (Refusal, freeze_bundle, decide, load_bundle, validate_bars,
                   asof_session, check_snapshot)

@pytest.fixture
def panel():
    dates=ExchangeCalendar().sessions
    dates=dates[dates>=pd.Timestamp('2024-01-02')][:110]
    close=100+np.arange(len(dates))*.08
    return {s:pd.DataFrame(dict(open=close-.02,high=close+1.,low=close-1.,close=close,
        volume=1e6,dividends=0.,splits=1.),index=pd.DatetimeIndex(dates,name='date')) for s in ['SPY','QQQ','GLD']}

@pytest.fixture
def config():
    return dict(initial_equity=5000.,weekly_budget=750.,capital_floor=160.,
        per_trade_risk_fraction=.05,session_risk_fraction=.05,weekly_risk_fraction=.15,
        session_risk_budget=250.,max_positions=3,max_candidates_per_session=2,max_entries_per_session=1,
        whole_shares=True,fee_per_side=1.09,slippage_bps=5.,entry_cap_multiplier=1.005,
        stop_atr=2.,target_atr=6.,max_holding_sessions=20)

@pytest.fixture
def bundle(tmp_path,panel,config):
    for s,f in panel.items():f.to_csv(tmp_path/(s+'.csv'))
    dates=panel['SPY'].index
    forecasts=pd.DataFrame([dict(date=d,symbol=s,prediction=.05,prediction_low=.01,confidence=.75,
        training_cutoff='2023-11-01',first_decision='2024-01-02') for d in dates for s in panel])
    forecasts.to_csv(tmp_path/'predictions.csv',index=False)
    (tmp_path/'metadata.json').write_text(json.dumps(dict(candidate='TEST_FIXTURE',status='REJECTED_RESEARCH')))
    (tmp_path/'gates.json').write_text(json.dumps(dict(status='FAIL',max_drawdown=False)))
    (tmp_path/'model.bin').write_text('Synthetic test fixture model; never actionable')
    config={**config,'scenarios':{'risk05_base_whole':config}}
    (tmp_path/'config.json').write_text(json.dumps(config))
    freeze_bundle(tmp_path,'metadata.json','predictions.csv','config.json','gates.json','model.bin',
        {s:s+'.csv' for s in panel},start=str(dates[0].date()),end=str(dates[-1].date()),output='bundle.json')
    return tmp_path/'bundle.json'


def test_standalone_driver_matches_original_ledger(panel,config):
    f=build_features(panel);p=pd.DataFrame(.05,index=panel['SPY'].index,columns=panel)
    a=run_engine(f,p,config)
    b=run_backtest(f,p,config)
    for name in ['equity','trades','decisions']:
        pd.testing.assert_frame_equal(a[name],b[name],check_dtype=False)
    assert len(a['trades'])>0


def test_trend_candidate_masks_honored(panel,config):
    f=build_features(panel);p=pd.DataFrame(np.nan,index=panel['SPY'].index,columns=panel)
    result=run_engine(f,p,config,strategy='trend')
    assert result['trades'].empty
    assert not (result['decisions'].status=='admitted').any()
    finite=pd.DataFrame({s:x.return_20 for s,x in f.items()})
    a=run_engine(f,finite,config,strategy='trend')
    b=run_backtest(f,None,config,strategy='trend')
    pd.testing.assert_frame_equal(a['equity'],b['equity'])


def test_replay_real_state_and_machine_fields(bundle,tmp_path,panel):
    date=panel['SPY'].index[65]
    out=decide(bundle,date=str(date.date()),root=tmp_path)
    assert out['status']=='REJECTED_RESEARCH_COUNTERFACTUAL'
    assert out['actionable'] is False and out['broker_connected'] is False
    assert out['account']['equity']!=5000
    assert out['gates']['status']=='FAIL'
    assert out['account']['settled_cash']>=0
    assert out['assumptions']['max_drawdown_guaranteed'] is False
    assert len(out['forecasts'])==3
    assert all('label' not in row and 'label_matured' not in row for row in out['forecasts'])
    check_snapshot(json.loads(json.dumps(out['account'])),out['account'])
    bad={**out['account'],'settled_cash':5001}
    with pytest.raises(Refusal,match='snapshot_ledger'):check_snapshot(bad,out['account'])
    with pytest.raises(Refusal,match='timestamp'):check_snapshot({**out['account'],'as_of':'2099-01-01'},out['account'])


def test_hash_mismatch_and_missing_inputs_refused(bundle,tmp_path):
    (tmp_path/'model.bin').write_text('tampered')
    with pytest.raises(Refusal,match='provenance_hash_mismatch'):load_bundle(bundle,tmp_path)
    (tmp_path/'model.bin').unlink()
    with pytest.raises(Refusal,match='missing_or_outside'):load_bundle(bundle,tmp_path)


def test_current_paper_requires_latest_completed_exchange_session(bundle,tmp_path):
    # Before NY close May6, completed session is Friday May3. After close it is May6.
    assert asof_session('2024-05-06T19:59:00Z',now='2024-05-06T22:00Z')==pd.Timestamp('2024-05-03')
    assert asof_session('2024-05-06T20:00:00Z',now='2024-05-06T22:00Z')==pd.Timestamp('2024-05-06')
    # July3 early close and July4 holiday.
    assert asof_session('2024-07-04T22:00:00Z',now='2024-07-04T22:00Z')==pd.Timestamp('2024-07-03')
    with pytest.raises(Refusal,match='timezone'):asof_session('2024-05-06')
    with pytest.raises(Refusal,match='future_as_of'):asof_session('2099-01-01T00:00Z')
    with pytest.raises(Refusal,match='stale_paper_as_of'):decide(bundle,as_of='2024-05-06T22:00Z',mode='paper',root=tmp_path)
    with pytest.raises(Refusal,match='missing_or_stale_completed_bar'):
        decide(bundle,as_of='2026-10-21T04:00Z',now='2026-10-21T04:00Z',mode='paper',root=tmp_path)


def test_bad_bars_incomplete_missing_held_calendar_nan_future(panel):
    date=panel['SPY'].index[65]
    for transform,reason in [
        (lambda f:f.drop(f.index[30]),'incomplete'),
        (lambda f:f.assign(close=np.nan),'nonfinite'),
        (lambda f:f.assign(high=1.),'invalid_ohlcv')]:
        bad={**panel,'SPY':transform(panel['SPY'])}
        with pytest.raises(Refusal,match=reason):validate_bars(bad,date)
    with pytest.raises(Refusal,match='missing_required'):validate_bars({'SPY':panel['SPY']},date)
    with pytest.raises(Refusal,match='missing_or_stale'):validate_bars(panel,pd.Timestamp('2026-10-20'))


def test_future_model_and_stale_model_refused(bundle,tmp_path,panel):
    date=panel['SPY'].index[65]
    path=tmp_path/'predictions.csv';original=pd.read_csv(path)
    for col,value,reason in [('first_decision','2099-01-01','future_or_missing'),
                             ('training_cutoff','2099-01-01','future_or_missing'),
                             ('first_decision','2020-01-01','stale_model')]:
        df=original.copy();df[col]=value;df.to_csv(path,index=False)
        b=json.loads(bundle.read_text());from paper import sha
        b['files']['predictions']['sha256']=sha(path);bundle.write_text(json.dumps(b))
        with pytest.raises(Refusal,match=reason):decide(bundle,date=str(date.date()),root=tmp_path)


def test_uncalibrated_candidate_may_declare_confidence_unavailable(bundle,tmp_path,panel):
    forecasts=pd.read_csv(tmp_path/'predictions.csv')
    forecasts['confidence']=np.nan
    forecasts['label']=.99
    forecasts['label_matured']='2099-01-01'
    forecasts.to_csv(tmp_path/'predictions.csv',index=False)
    metadata=json.loads((tmp_path/'metadata.json').read_text())
    metadata['candidate']='P01'
    (tmp_path/'metadata.json').write_text(json.dumps(metadata))
    b=json.loads(bundle.read_text());from paper import sha
    b['candidate']='P01'
    b['files']['predictions']['sha256']=sha(tmp_path/'predictions.csv')
    b['files']['metadata']['sha256']=sha(tmp_path/'metadata.json')
    bundle.write_text(json.dumps(b))
    out=decide(bundle,date=str(panel['SPY'].index[65].date()),root=tmp_path)
    assert all(row['confidence'] is None for row in out['forecasts'])
    assert all('label' not in row and 'label_matured' not in row for row in out['forecasts'])


def test_padded_missing_context_tail_does_not_pass_freshness(bundle,tmp_path,panel):
    dates=panel['SPY'].index
    context=pd.DataFrame({'date':dates,'available_date':[ExchangeCalendar().next(d) for d in dates],
                          'vix_close_pct':[20.]+[np.nan]*(len(dates)-1)})
    context.to_csv(tmp_path/'context.csv',index=False)
    b=json.loads(bundle.read_text());from paper import sha
    b['files']['context']={'path':'context.csv','sha256':sha(tmp_path/'context.csv')}
    bundle.write_text(json.dumps(b))
    with pytest.raises(Refusal,match='missing_or_stale_context'):
        decide(bundle,date=str(dates[65].date()),root=tmp_path)


def test_rejected_strategy_refuses_paper_even_fresh(bundle,tmp_path,panel):
    d=panel['SPY'].index[65]
    stamp=str(d.date())+'T22:00Z'
    with pytest.raises(Refusal,match='strategy_not_approved'):
        decide(bundle,as_of=stamp,now=stamp,mode='paper',root=tmp_path)
    with pytest.raises(Refusal,match='live_and_order'):decide(bundle,mode='live',root=tmp_path)


def test_future_bar_mutation_cannot_change_earlier_replay(panel,config):
    f=build_features(panel);p=pd.DataFrame(.05,index=panel['SPY'].index,columns=panel)
    date=panel['SPY'].index[65]
    a=run_engine(f,p,config,replay_through=date)
    changed={s:df.copy() for s,df in panel.items()}
    for df in changed.values():
        df.loc[df.index>date,['open','high','low','close']]*=3
    b=run_engine(build_features(changed),p,config,replay_through=date)
    for key in a:pd.testing.assert_frame_equal(a[key],b[key])


def test_cash_reservation_and_t1_settlement(config):
    e=make_engine(config)
    def bar(price):return {'SPY':dict(open=price,high=price+1,low=price-1,close=price,dividends=0,splits=1)}
    e.process_bar('2024-06-03',bar(100))
    plan=e.propose('SPY',100,2,.05,indicator_date=pd.Timestamp('2024-06-03'))
    assert plan and plan.cash<=5000
    assert plan.planned_risk<=250
    assert e.propose('QQQ',100,2,.05,indicator_date=pd.Timestamp('2024-06-03')) is None
    assert e.propose('GLD',100,2,.05,indicator_date=pd.Timestamp('2024-06-03')) is None
    assert e.decisions[-1]['reason']=='daily_candidate_limit'
    e.process_bar('2024-06-04',bar(100))
    assert e.positions
    # Large opening gap loss remains in ledger, exceeding10%target as expected.
    e.process_bar('2024-06-05',bar(50))
    # The ledger observes the opening gap before intraday stop processing.  Its
    # weekly protective check therefore liquidates at the same open and records
    # that controlling reason while retaining the full gap loss.
    assert e.trades[-1]['reason']=='weekly_protective_risk_open'
    assert e.equity<4500
    assert e.settled<e.cash
    assert e.unsettled[0][0]==pd.Timestamp('2024-06-06')
    cash=e.cash;e.process_bar('2024-06-06',bar(50))
    assert e.settled==pytest.approx(cash) and not e.unsettled
    e.assert_accounting()


def test_pending_tamper_and_partial_fill_rejected(config):
    e=make_engine(config);e.process_bar('2024-06-03',{'SPY':dict(open=100,high=101,low=99,close=100)})
    plan=e.propose('SPY',100,2,.05,indicator_date=pd.Timestamp('2024-06-03'))
    e.pending['SPY']=replace(plan,qty=plan.qty+1)
    with pytest.raises(ReservationError):e.verify()
    with pytest.raises(NotImplementedError):e.partial_fill()


def test_benchmark_dividends_costs_split_and_reinvestment(panel,config):
    f=panel['SPY'].copy();f.loc[f.index[10],'dividends']=2.
    cash=benchmark(f,config,reinvest=False)
    drip=benchmark(f,config,reinvest=True)
    assert np.isfinite(cash['equity'].select_dtypes('number')).all().all()
    assert cash['trades'].dividends.iloc[0]>0
    assert drip['trades'].fees.iloc[0]>cash['trades'].fees.iloc[0]
    assert not cash['equity'].passive_risk_policy_applies.any()
    # Distribution reinvests only after assumed payout, never on ex-date.
    purchases=drip['decisions'].query("reason=='passive_reinvestment'")
    assert purchases.date.iloc[0]>=f.index[10]+pd.Timedelta(days=30)


def test_null_optional_confidence_and_future_outcomes_not_disclosed(bundle,tmp_path,panel):
    path=tmp_path/'predictions.csv';df=pd.read_csv(path)
    df['confidence']=np.nan;df['label']=999.;df['label_matured']='2099-01-01'
    df.to_csv(path,index=False)
    from paper import sha
    b=json.loads(bundle.read_text());b['files']['predictions']['sha256']=sha(path);bundle.write_text(json.dumps(b))
    out=decide(bundle,date=str(panel['SPY'].index[65].date()),root=tmp_path)
    assert all(r['confidence'] is None for r in out['forecasts'])
    assert all('label' not in r and 'label_matured' not in r for r in out['forecasts'])


def test_context_checks_availability_finite_values_and_lagged_change(bundle,tmp_path,panel):
    dates=panel['SPY'].index;date=dates[65]
    ctx=pd.DataFrame(dict(date=dates,available_date=[ExchangeCalendar().next(d) for d in dates],vix_close_pct=20.))
    path=tmp_path/'context.csv'
    from paper import sha
    b=json.loads(bundle.read_text())
    def save(frame):
        frame.to_csv(path,index=False)
        b['files']['context']=dict(path='context.csv',sha256=sha(path))
        bundle.write_text(json.dumps(b))
    save(ctx)
    out=decide(bundle,date=str(date.date()),root=tmp_path)
    assert out['context']['available_date'].startswith(str(date.date()))
    for ix in [64,44]:
        missing=ctx.copy();missing.loc[ix,'vix_close_pct']=np.nan;save(missing)
        with pytest.raises(Refusal,match='missing_or_stale_context'):decide(bundle,date=str(date.date()),root=tmp_path)
    future=ctx.copy();future.loc[64,'available_date']=ExchangeCalendar().next(date,3)
    save(future)
    with pytest.raises(Refusal,match='invalid_context_availability'):decide(bundle,date=str(date.date()),root=tmp_path)


def test_each_risk_policy_and_position_cap(config):
    for fraction,weekly in [(.05,.15),(.10,.30)]:
        e=make_engine({**config,'per_trade_risk_fraction':fraction,'session_risk_fraction':fraction,'weekly_risk_fraction':weekly})
        e.process_bar('2024-06-03',{'SPY':dict(open=100,high=101,low=99,close=100)})
        assert e.risk.session_limit==5000*fraction
        assert e.risk.weekly_limit==5000*weekly
        plan=e.propose('SPY',100,2,.05,indicator_date=pd.Timestamp('2024-06-03'))
        assert plan.planned_risk<=e.equity*fraction
        assert e.risk.session_risk<=e.risk.session_limit
        assert e.risk.check(equity=5000,settled_available=5000,count=3,all_in_cost=100,
            planned_risk=10,net_reward=30,entry_costs=0,remaining_risk=10)=='position_limit'


def test_missing_raw_forecast_is_not_silently_no_entry(bundle,tmp_path,panel):
    path=tmp_path/'predictions.csv';df=pd.read_csv(path)
    date=str(panel['SPY'].index[65].date())
    df.loc[(df.date==date)&(df.symbol=='SPY'),'prediction']=np.nan
    df.to_csv(path,index=False)
    from paper import sha
    b=json.loads(bundle.read_text());b['files']['predictions']['sha256']=sha(path);bundle.write_text(json.dumps(b))
    with pytest.raises(Refusal,match='missing_required_model_prediction'):
        decide(bundle,date=date,root=tmp_path)
    # Only an explicit model no-entry flag can represent an intentional mask.
    df['admitted']=True
    df.loc[(df.date==date)&(df.symbol=='SPY'),'admitted']=False
    df.to_csv(path,index=False);b['files']['predictions']['sha256']=sha(path);bundle.write_text(json.dumps(b))
    assert decide(bundle,date=date,root=tmp_path)['forecasts']
