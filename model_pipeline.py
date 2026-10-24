"""Frozen V4 causal model production. No fitting uses evaluation outcomes early."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from legacy.research.features import FEATURE_COLUMNS, build_features, executable_labels

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'analysis/model'
GROUPS={'equity':('SPY','QQQ'),'gold':('GLD',)}
CONTEXT=['vix_close_pct','vix_change20']

def write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,default=str,allow_nan=False)+'\n')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_inputs(end='2026-10-19'):
    panel={p.stem:pd.read_csv(p,index_col=0,parse_dates=True).loc[:end] for p in sorted((ROOT/'data/processed').glob('*.csv'))}
    if set(panel)!={'SPY','QQQ','GLD'}:raise ValueError('Exactly SPY QQQ GLD required')
    features=build_features(panel)
    context=pd.read_csv(ROOT/'data/context.csv',parse_dates=['date','available_date'])
    if not (context.available_date>context.date).all():raise ValueError('Context must lag observation')
    context=context.sort_values('available_date').set_index('available_date')
    if context.index.duplicated().any():raise ValueError('Duplicate context availability')
    # Compute changes on the market-session clock so absent observations cannot
    # make a 20-observation change look like a 20-session change.
    cal=panel['SPY'].index
    context=context.reindex(cal)
    context['vix_change20']=context.vix_close_pct.diff(20)
    for symbol,f in features.items():features[symbol]=f.join(context[CONTEXT])
    return features,cal

def bracket_labels(f,horizon=20):
    """Conservative executable gross bracket target, mirroring engine OHLC order.

    Conditional on a next-session cap fill; stop wins same-bar ambiguity.
    Intraday cap entry cannot claim a prior high/target. End tails excluded.
    """
    if not f.splits.isin([0,1]).all():raise ValueError('Split-free label snapshot required')
    out=pd.DataFrame({'label':np.nan,'label_matured':pd.NaT},index=f.index)
    op,hi,lo,cl,div,atr=(f[c].to_numpy() for c in ['open','high','low','close','dividends','atr14'])
    for t in range(len(f)-horizon):
        if not np.isfinite(atr[t]) or atr[t]<=0:continue
        cap=cl[t]*1.005;stop=cap-2*atr[t];target=cap+6*atr[t]
        if not 0<stop<cap<target or lo[t+1]>cap:continue
        entry=min(op[t+1],cap);accrued=0.
        for j in range(t+1,t+horizon+1):
            if j>t+1:accrued+=div[j]
            intraday=j==t+1 and op[j]>cap
            if entry<=stop or entry>=target:exit_price=entry
            elif op[j]<=stop and not intraday:exit_price=op[j]
            elif lo[j]<=stop:exit_price=stop
            elif op[j]>=target and not intraday:exit_price=op[j]
            elif hi[j]>=target and not intraday:exit_price=target
            elif j==t+horizon:exit_price=cl[j]
            else:continue
            out.iloc[t,0]=(exit_price+accrued)/entry-1
            out.iloc[t,1]=f.index[j];break
    return out

def eligible(rows,columns,cutoff):
    valid=np.isfinite(rows[columns]).all(axis=1)&np.isfinite(rows.label)&(rows.date>='2010-01-01')&(rows.label_matured<=cutoff)
    for boundary in ('2019-01-01','2022-01-01','2024-01-01'):
        valid&=~((rows.date<boundary)&(rows.label_matured>=boundary))
    return rows.loc[valid].copy()

def new_model():return make_pipeline(StandardScaler(),Ridge(alpha=100))

def calibration_split(train,calendar):
    """Trailing252-session OOS calibration; 10 complete sessions before use."""
    last=calendar.searchsorted(train.date.max(),side='right')-1
    first=calendar[max(0,last-251)]
    pos=calendar.get_loc(first)
    if pos<11:raise ValueError('Insufficient calibration embargo history')
    fit_cut=calendar[pos-11]
    fit=train[train.label_matured<=fit_cut]
    cal=train[train.date>=first]
    return fit,cal,fit_cut,first

def predict_stage(candidate,partition,features,calendar,registry,common=True):
    begin,end=registry['periods'][partition]
    allowed=calendar[(calendar>=begin)&(calendar<=end)][10:]
    pred=pd.DataFrame(np.nan,index=calendar,columns=list(features));low=pred.copy()
    logs=[];records=[];models={};fits=0
    mask=np.isfinite(features['SPY'][CONTEXT]).all(axis=1)
    if candidate['strategy']=='trend':
        for s,f in features.items():
            v=f.return_20.copy()
            v[~v.index.isin(allowed)]=np.nan
            if common:v[~mask]=np.nan
            if candidate['id']=='T06':v[f.vix_close_pct>30]=np.nan
            pred[s]=v
        return pred,pred.copy(),logs,records,models,0
    columns=FEATURE_COLUMNS+(CONTEXT if candidate['context'] else [])
    labeled={s:f.drop(columns=['label','label_matured']).join(executable_labels(f,20) if candidate['label']=='fixed' else bracket_labels(f)) for s,f in features.items()}
    for group,symbols in GROUPS.items():
        # The processed frames intentionally keep an index named ``date``.  Put
        # decision dates in a normal column and discard that index before the
        # sort, otherwise pandas treats ``date`` as both an index level and a
        # column label and refuses the first production fit.
        pooled=[]
        for symbol,frame in labeled.items():
            if symbol not in symbols:
                continue
            item=frame.copy()
            item['date']=item.index
            item['symbol']=symbol
            pooled.append(item.reset_index(drop=True))
        rows=pd.concat(pooled,ignore_index=True).sort_values(['date','symbol'])
        for quarter in allowed.to_period('Q').unique():
            dates=allowed[allowed.to_period('Q')==quarter];first=dates[0]
            cutoff=calendar[calendar.get_loc(first)-11]
            train=eligible(rows,columns,cutoff)
            test=rows[rows.date.isin(dates)&np.isfinite(rows[columns]).all(axis=1)]
            if len(train)<100 or test.empty:continue
            model=new_model();model.fit(train[columns],train.label);fits+=1
            values=model.predict(test[columns]);q=0.;residual=np.array([])
            calibration={}
            # C03 supplies C04 predictions and calibrated residual distribution.
            if candidate['id']=='C03':
                sub,tail,calcut,calfirst=calibration_split(train,calendar)
                if len(sub)<100 or len(tail)<20:raise ValueError('Insufficient calibration rows')
                cm=new_model();cm.fit(sub[columns],sub.label);fits+=1
                residual=np.abs(tail.label.to_numpy()-cm.predict(tail[columns]));q=float(np.quantile(residual,.5))
                calibration=dict(rows=len(tail),fit_rows=len(sub),fit_cutoff=str(calcut.date()),first_decision=str(calfirst.date()),max_fit_maturity=str(sub.label_matured.max().date()),median_abs_residual=q,empirical_coverage=float(np.mean(residual<=q)))
            log=dict(candidate=candidate['id'],partition=partition,group=group,quarter=str(quarter),first_decision=str(first.date()),training_cutoff=str(cutoff.date()),max_training_maturity=str(train.label_matured.max().date()),training_rows=len(train),feature_columns=columns,scaler_mean=model.named_steps['standardscaler'].mean_.tolist(),scaler_scale=model.named_steps['standardscaler'].scale_.tolist(),coefficients=model.named_steps['ridge'].coef_.tolist(),intercept=float(model.named_steps['ridge'].intercept_),calibration=calibration)
            logs.append(log);models[group]={'pipeline':model,'features':columns,'training_cutoff':str(cutoff.date()),'calibration_residuals':residual,'quantile':q}
            for row,value in zip(test.itertuples(),values):
                admitted=(not common or bool(mask.loc[row.date]))
                if admitted:pred.loc[row.date,row.symbol]=value;low.loc[row.date,row.symbol]=value-q
                confidence=float(np.mean(residual<value)) if len(residual) else None
                records.append(dict(date=row.date,symbol=row.symbol,prediction=float(value) if admitted else None,prediction_low=float(value-q) if admitted else None,confidence=confidence,training_cutoff=str(cutoff.date()),first_decision=str(first.date()),group=group,quarter=str(quarter),label=float(row.label) if np.isfinite(row.label) else None,label_matured=row.label_matured,admitted=admitted))
    return pred,low,logs,records,models,fits

def confidence_records(records):
    out=[]
    for r in records:
        r=r.copy();r['candidate']='C04'
        if r['prediction_low'] is None or r['prediction_low']<=0:r['prediction']=None;r['admitted']=False
        out.append(r)
    return out

if __name__=='__main__':
    raise SystemExit('Use python evaluate.py --run; production fitting requires frozen stage order.')
