"""Causal invariants, not performance targets."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_pipeline import bracket_labels,calibration_split,eligible,new_model,confidence_records,load_inputs,CONTEXT
from evaluate import rank_candidates,comparison_curve

def test_bracket_stop_wins_ambiguous_target():
    idx=pd.bdate_range('2020-01-01',periods=30)
    f=pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,atr14=1.,dividends=0.,splits=1.),index=idx)
    f.loc[idx[1],['high','low']]=[110.,95.]
    labels=bracket_labels(f)
    assert labels.label_matured.iloc[0]==idx[1]
    assert labels.label.iloc[0]==pytest.approx((100.*1.005-2)/100.-1)

def test_no_cap_fill_has_no_label():
    idx=pd.bdate_range('2020-01-01',periods=30)
    f=pd.DataFrame(dict(open=103.,high=104.,low=102.,close=100.,atr14=1.,dividends=0.,splits=1.),index=idx)
    assert np.isnan(bracket_labels(f).label.iloc[0])

def test_train_scale_cannot_see_future_extreme():
    x=pd.DataFrame({'x':[0.,1.,2.]});m=new_model();m.fit(x,[0.,.1,.2]);before=m.named_steps['standardscaler'].mean_.copy()
    m.predict(pd.DataFrame({'x':[1e99]}))
    assert np.array_equal(before,[1.]);assert np.array_equal(m.named_steps['standardscaler'].mean_,before)

def test_maturity_and_boundary_purge():
    rows=pd.DataFrame(dict(date=pd.to_datetime(['2018-12-20','2019-01-02','2019-01-03']),label_matured=pd.to_datetime(['2019-01-03','2019-01-08','2019-02-10']),label=[.1,.2,.3],x=[1.,2.,3.]))
    out=eligible(rows,['x'],pd.Timestamp('2019-01-10'))
    assert out.index.tolist()==[1]

def test_calibration_maturity_embargo():
    cal=pd.bdate_range('2010-01-01',periods=1000)
    rows=pd.DataFrame({'date':cal[:-20],'label_matured':cal[20:]})
    fit,tail,cutoff,first=calibration_split(rows,cal)
    assert fit.label_matured.max()<=cutoff
    assert cal.get_loc(first)-cal.get_loc(cutoff)-1==10
    assert fit.date.max()<tail.date.min()

def test_selection_rejects_validation():
    with pytest.raises(ValueError,match='development'):rank_candidates(pd.DataFrame({'partition':['validation']}))

def test_confidence_filter_cannot_admit_negative_lower():
    r=dict(prediction=.01,prediction_low=-.01,admitted=True)
    out=confidence_records([r])[0]
    assert out['prediction'] is None and not out['admitted']

def test_context_terminal_missing_not_carried_forward():
    features,cal=load_inputs();f=features['SPY']
    assert np.isfinite(f.loc['2026-09-23',CONTEXT].to_numpy(dtype=float)).all()
    assert f.loc['2026-09-24':,CONTEXT].isna().any(axis=1).all()
    assert len(f.loc['2026-10-19'])>0

def test_features_and_labels_prefix_invariant():
    features,cal=load_inputs('2021-12-31');full,_=load_inputs('2026-10-19')
    for s in features:
        for c in CONTEXT+['return_20','atr14','sma50']:
            pd.testing.assert_series_equal(features[s][c],full[s].loc[:'2021-12-31',c])
        labels=bracket_labels(features[s]);fl=bracket_labels(full[s]);mature=labels.label_matured.notna()
        pd.testing.assert_frame_equal(labels.loc[mature],fl.loc[labels.index[mature]])


def test_comparison_curve_drops_risk_week_label(monkeypatch):
    frame=pd.DataFrame({'date':pd.to_datetime(['2024-01-02','2024-01-03']),
                        'equity':[5000.,5001.], 'week':['2024-01-01','2024-01-01']})
    monkeypatch.setattr('evaluate.curve',lambda *args:frame.copy())
    normalized=comparison_curve('final','scenario','candidate')
    assert list(normalized.columns)==['date','equity']
