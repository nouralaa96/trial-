"""Independent fit chronology, closed-form Ridge and source availability audit."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from legacy.research.features import build_features
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from model_pipeline import bracket_labels
raw={p.stem:pd.read_csv(p,index_col=0,parse_dates=True) for p in (ROOT/'data/processed').glob('*.csv')}
cal=raw['SPY'].index;features=build_features(raw)
ctx=pd.read_csv(ROOT/'data/context.csv',parse_dates=['date','available_date'])
assert not ctx.date.duplicated().any();assert not ctx.available_date.duplicated().any()
assert np.array_equal(cal[cal.get_indexer(ctx.date.iloc[:-1])+1].values,ctx.available_date.iloc[:-1].values)
vix=ctx.set_index('available_date').vix_close_pct.reindex(cal);context=pd.DataFrame({'vix_close_pct':vix,'vix_change20':vix.diff(20)})
for s in features:features[s]=features[s].join(context)
# Independent economic labels; no implementation training/eligibility code used.
def labels(f,kind):
 records=[]
 for i in range(len(f)):
  answer=np.nan;maturity=pd.NaT
  if i+20<len(f):
   nxt=f.iloc[i+1];last=f.iloc[i+20]
   if kind=='fixed':answer=(last.close+f.dividends.iloc[i+2:i+21].sum())/nxt.open-1;maturity=f.index[i+20]
   elif np.isfinite(f.atr14.iloc[i]):
    cap=f.close.iloc[i]*1.005;stop=cap-2*f.atr14.iloc[i];target=cap+6*f.atr14.iloc[i]
    if 0<stop<cap<target and nxt.low<=cap:
     entry=min(nxt.open,cap);income=0.
     for j in range(i+1,i+21):
      b=f.iloc[j];intraday=j==i+1 and b.open>cap
      if j>i+1:income+=b.dividends
      price=None
      if entry<=stop or entry>=target:price=entry
      elif b.open<=stop and not intraday:price=b.open
      elif b.low<=stop:price=stop
      elif b.open>=target and not intraday:price=b.open
      elif b.high>=target and not intraday:price=target
      elif j==i+20:price=b.close
      if price is not None:answer=(price+income)/entry-1;maturity=f.index[j];break
  records.append((answer,maturity))
 return pd.DataFrame(records,index=f.index,columns=['label','label_matured'])
cache={};labelcheck={}
for kind in ['fixed','bracket']:
 for s,f in features.items():
  lab=labels(f,kind);cache[kind,s]=f.drop(columns=['label','label_matured']).join(lab)
  if kind=='bracket':
   impl=bracket_labels(f);assert np.allclose(lab.label,impl.label,atol=1e-12,equal_nan=True);assert lab.label_matured.equals(impl.label_matured);labelcheck[s]=int(lab.label.notna().sum())
# Close-form independent Ridge using independently reconstructed training rows.
def fit(frame,columns):
 x=frame[columns].to_numpy();y=frame.label.to_numpy();mu=x.mean(0);scale=x.std(0);scale[scale==0]=1.;z=(x-mu)/scale
 intercept=y.mean();coef=np.linalg.solve(z.T@z+100*np.eye(len(columns)),z.T@(y-intercept))
 return mu,scale,coef,intercept
checks=[];fitcount=0;predcount=0;largest=0.
for path in sorted((ROOT/'analysis/model/predictions').glob('*/*/fits.json')):
 logs=json.loads(path.read_text())
 if not logs:continue
 saved=pd.read_csv(path.parent/'predictions.csv',parse_dates=['date'])
 for log in logs:
  cid=log['candidate'];kind='fixed' if cid=='P01' else 'bracket';symbols=['SPY','QQQ'] if log['group']=='equity' else ['GLD'];columns=log['feature_columns']
  rows=pd.concat([cache[kind,s].assign(date=cache[kind,s].index,symbol=s).reset_index(drop=True) for s in symbols]).sort_values(['date','symbol'])
  cutoff=pd.Timestamp(log['training_cutoff']);first=pd.Timestamp(log['first_decision'])
  assert cal.get_loc(first)-cal.get_loc(cutoff)-1==10
  valid=(rows.date>='2010-01-01')&(rows.label_matured<=cutoff)&np.isfinite(rows[columns]).all(axis=1)&np.isfinite(rows.label)
  for boundary in pd.to_datetime(['2019-01-01','2022-01-01','2024-01-01']):valid &= ~((rows.date<boundary)&(rows.label_matured>=boundary))
  train=rows.loc[valid]
  assert len(train)==log['training_rows'];assert train.label_matured.max()==pd.Timestamp(log['max_training_maturity']);assert train.date.max()<first
  mu,scale,coef,intercept=fit(train,columns);fitcount+=1
  for a,b in [(mu,log['scaler_mean']),(scale,log['scaler_scale']),(coef,log['coefficients']),(intercept,log['intercept'])]:assert np.allclose(a,b,rtol=1e-9,atol=1e-11)
  s=saved[(saved.group==log['group'])&(saved.quarter==log['quarter'])].dropna(subset=['prediction'])
  actual=rows[['date','symbol']+columns].merge(s,on=['date','symbol'],validate='one_to_one')
  estimate=((actual[columns].to_numpy()-mu)/scale)@coef+intercept
  error=float(np.max(abs(estimate-actual.prediction))) if len(actual) else 0.;largest=max(largest,error);assert error<1e-10;predcount+=len(actual)
  calibration=log['calibration']
  if calibration:
   start=pd.Timestamp(calibration['first_decision']);cc=pd.Timestamp(calibration['fit_cutoff']);assert cal.get_loc(start)-cal.get_loc(cc)-1==10
   sub=train[train.label_matured<=cc];tail=train[train.date>=start]
   assert len(sub)==calibration['fit_rows'] and len(tail)==calibration['rows']
   assert sub.label_matured.max()==pd.Timestamp(calibration['max_fit_maturity'])
   cm,cs,cb,ci=fit(sub,columns);fitcount+=1
   residual=np.abs(tail.label-(((tail[columns].to_numpy()-cm)/cs)@cb+ci));q=float(np.quantile(residual,.5))
   assert abs(q-calibration['median_abs_residual'])<1e-10
   if len(actual):assert np.allclose(actual.prediction_low,actual.prediction-q,atol=1e-10)
  checks.append(dict(candidate=cid,partition=log['partition'],group=log['group'],quarter=log['quarter'],training_rows=len(train),prediction_rows=len(actual),max_prediction_error=error))
# Final price-only sensitivity computes24 additional fits; source does not retain
# those fit logs, so verify by rerunning predict_stage and exact final equity later.
counts=json.loads((ROOT/'analysis/model/run_counts.json').read_text())
assert fitcount==172 and counts['fits']==196
report={'status':'PASS','independently_verified_logged_fits':fitcount,'additional_P01_fullhistory_fits_reported':24,'total_reported_fits':196,'logged_model_records':len(checks),'verified_forecasts':predcount,'max_prediction_abs_error':largest,'independent_bracket_label_counts':labelcheck,'calibration_and_production_embargo_sessions':10,'context_last_available_nonmissing':str(ctx.loc[ctx.vix_close_pct.notna(),'available_date'].max().date()),'checks':checks,'scope_limitation':'172 logged production/calibration fits checked by independent closed-form solution.24 final P01_fullhistory fits are additionally covered by full deterministic run reproduction; individual sensitivity fit logs are not saved.'}
(ROOT/'review/model_chronology_recomputation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
