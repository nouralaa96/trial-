"""Independent artifact/ledger/benchmark audit; does not call project metrics."""
import hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xc
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'review'; MODEL=ROOT/'analysis/model'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
 try:return pd.read_csv(p)
 except pd.errors.EmptyDataError:return pd.DataFrame()
def close(a,b):return bool(np.isclose(a,b,atol=1e-6,rtol=1e-10))
errors=[]; allstats=[]; hashes={}
for partition in ['development','validation','final']:
 results=read(MODEL/f'{partition}_results.csv')
 annual=read(MODEL/f'{partition}_yearly.csv')
 for r in results.to_dict('records'):
  folder=MODEL/'portfolios'/partition/r['scenario']/r['candidate']
  e,t,d=[read(folder/f'{n}.csv') for n in ['equity','trades','decisions']]
  for p in folder.glob('*.csv'):hashes[str(p.relative_to(ROOT))]=digest(p)
  key=f"{partition}/{r['scenario']}/{r['candidate']}"; fail=[]
  v=np.r_[5000.,e.equity];peak=np.maximum.accumulate(v)
  years=(pd.Timestamp(e.date.iloc[-1])-pd.Timestamp(e.date.iloc[0])).days/365.25
  calc=dict(final_equity=v[-1],net_pnl=v[-1]-5000.,cagr=(v[-1]/5000.)**(1/years)-1,max_drawdown=float(max(1-v/peak)),completed_trades=len(t),fees=float(e.fees.iloc[-1]),friction=float(e.friction.iloc[-1]))
  for k,val in calc.items():
   if not close(val,r[k]):fail.append(f'metric:{k}')
  if not np.isfinite(e.equity).all() or not e.date.is_unique or not e.date.is_monotonic_increasing:fail.append('dates_or_finite')
  if not np.allclose(e.equity,e.cash+e.exposure,rtol=0,atol=1e-6):fail.append('equity_cash_exposure')
  if not np.allclose(e.cash,e.settled_cash+e.unsettled_cash,rtol=0,atol=1e-6):fail.append('cash_parts')
  if e.settled_cash.min() < -1e-6:fail.append('negative_settled')
  if 'reserved_cash' in e and (e.reserved_cash-e.settled_cash).max()>1e-6:fail.append('overspent_reservations')
  if (e.open_positions+e.pending_positions).max()>3:fail.append('position_limit')
  if e.open_positions.iloc[-1]!=0 or e.pending_positions.iloc[-1]!=0:fail.append('terminal_positions')
  tp=float(t.net_pnl.sum()) if len(t) else 0.
  if not close(tp,calc['net_pnl']):fail.append('closed_pnl_reconcile')
  if len(t):
   if not close(t.fees.sum(),calc['fees']):fail.append('fee_reconcile')
   if not close(t.friction.sum(),calc['friction']):fail.append('friction_reconcile')
   if not (pd.to_datetime(t.exit_date)>=pd.to_datetime(t.entry_date)).all():fail.append('exit_before_entry')
   if not r['candidate'].startswith('SPY_'):
    valid_hold=t.holding_sessions.between(1,20) | ((t.holding_sessions==0)&(t.entry_date==t.exit_date)&(t.reason=='actual_fill_revalidation_exit'))
    if not valid_hold.all():fail.append('hold_bounds')
    independent_pnl=t.exit_notional-t.entry_notional-t.fees+t.dividends
    if not np.allclose(independent_pnl,t.net_pnl,rtol=0,atol=1e-6):fail.append('trade_pnl_formula')
    if r['scenario'].endswith('_whole') and not np.allclose(t.qty,np.round(t.qty),atol=1e-9):fail.append('whole_shares')
  if len(d) and not r['candidate'].startswith('SPY_'):
   admit=d[d.status=='admitted']
   if len(admit):
    if admit.groupby('date').size().max()>1:fail.append('one_admission')
    if (admit.considered_today>2).any():fail.append('candidate_limit')
    for a,b,label in [('planned_risk','per_trade_budget_at_admission','trade_risk'),('session_risk_after','session_budget_at_admission','session_risk'),('projected_weekly_required','weekly_budget_at_admission','weekly_risk'),('cash','settled_available','cash_admission')]:
     if (admit[a]-admit[b]).max()>1e-6:fail.append(label)
    if not (pd.to_datetime(admit.execute)>pd.to_datetime(admit.date)).all():fail.append('next_session_order')
  yearly={};prev=5000.
  for y,g in e.groupby(e.date.str[:4]):
   ret=float(g.equity.iloc[-1]/prev-1);yearly[y]=ret;prev=float(g.equity.iloc[-1])
   saved=annual[(annual.scenario==r['scenario'])&(annual.candidate==r['candidate'])&(annual.year==int(y))]
   if len(saved)!=1 or not close(ret,float(saved.return_fraction.iloc[0])):fail.append(f'annual:{y}')
  calc.update(key=key,calendar_returns=yearly,errors=fail)
  allstats.append(calc)
  if fail:errors.append(dict(key=key,errors=fail))
# Independently reconstruct every passive curve directly from raw executable prices.
calendar=xc.get_calendar('XNYS',start='2009-01-01',end='2028-12-31').sessions.tz_localize(None)
spy=pd.read_csv(ROOT/'data/processed/SPY.csv',index_col=0,parse_dates=True)
config=json.loads((ROOT/'legacy/frozen_config.json').read_text()); benchmarks=[]
for item in allstats:
 partition,scenario,cid=item['key'].split('/')
 if not cid.startswith('SPY_'):continue
 target=read(MODEL/'portfolios'/partition/scenario/cid/'equity.csv')
 f=spy.loc[target.date.iloc[0]:target.date.iloc[-1]]; cfg=config['scenarios'][scenario]
 fee=cfg['fee_per_side'];slip=cfg['slippage_bps']/10000;precision=1 if cfg['whole_shares'] else 1e6
 cash=5000.;q=0.;receipts=[];values=[]
 for i,(dt,b) in enumerate(f.iterrows()):
  if b.splits>0:q*=b.splits
  if b.dividends>0 and q>0:
   pay=calendar[calendar.searchsorted(dt+pd.Timedelta(days=30))];receipts.append((pay,q*b.dividends))
  paid=sum(v for pay,v in receipts if pay<=dt);cash+=paid;receipts=[(pay,v) for pay,v in receipts if pay>dt]
  if i==0 or (cid=='SPY_reinvested_total_return' and paid>0):
   price=b.open*(1+slip);buy=math.floor(max(0,cash-fee)/price*precision)/precision
   if buy>0:cash-=buy*price+fee;q+=buy
  if i==len(f)-1 and q>0:cash+=q*b.close*(1-slip)-fee;q=0.
  values.append(cash+q*b.close+sum(v for _,v in receipts))
 maxerr=float(np.max(np.abs(np.array(values)-target.equity.to_numpy())))
 benchmarks.append(dict(key=item['key'],max_equity_abs_error=maxerr))
 if maxerr>1e-6:errors.append(dict(key=item['key'],errors=['independent_benchmark']))
# Frozen ranking, sources, previous attempt lock, original projects.
rank=[];dev=read(MODEL/'development_results.csv')
for cid in ['P01','P02','C03','C04']:
 g=dev[dev.candidate==cid];passed=0;margins=[]
 for r in g.itertuples():
  refs=dev[(dev.scenario==r.scenario)&dev.candidate.isin(['SPY_cash_dividend','SPY_reinvested_total_return','T05'])]
  margin=r.cagr-refs.cagr.max();passed+=int(margin>0 and r.max_drawdown<=.1);margins.append(margin-2*max(0,r.max_drawdown-.1))
 rank.append(dict(candidate=cid,passing_scenarios=passed,worst_penalized_increment=min(margins),mean_turnover=float(g.turnover.mean())))
rank.sort(key=lambda r:(-r['passing_scenarios'],-r['worst_penalized_increment'],r['mean_turnover'],r['candidate']))
lock=json.loads((MODEL/'locked.json').read_text());assert rank[0]['candidate']==lock['candidate']=='C03'
for a,b in zip(rank,lock['ranking']):
 for k in ['passing_scenarios','worst_penalized_increment','mean_turnover']:assert close(a[k],b[k]),k
inputs=json.loads((MODEL/'inputs.json').read_text());input_matches={p:digest(ROOT/p)==h for p,h in inputs.items()};assert all(input_matches.values())
original=json.loads((ROOT/'oversight/original_projects.json').read_text())['sha256'];origfail=[p for p,h in original.items() if digest(p)!=h]
priorlock=json.loads((ROOT/'analysis/failed_runs/20261024_week_key_mismatch/locked.json').read_text());assert priorlock['candidate']==lock['candidate'];assert priorlock['ranking']==lock['ranking']
retry_files=list((ROOT/'analysis/failed_runs').glob('*/portfolios/*/*/*/equity.csv'))
allfiles=[p for p in MODEL.rglob('*') if p.is_file()]+[ROOT/n for n in ['model_pipeline.py','evaluate.py','execution_adapter.py','paper.py','data_pipeline.py','CHARTER.md','requirements.lock.txt']]
for p in allfiles:hashes[str(p.relative_to(ROOT))]=digest(p)
out=dict(status='PASS' if not errors and not origfail else 'FAIL',portfolio_count=len(allstats),ledger_errors=errors,portfolios=allstats,independent_benchmarks=benchmarks,ranking=rank,inputs_unchanged=input_matches,prior_attempt_same_rank_and_lock=True,retained_failed_portfolios=len(retry_files),original_file_count=len(original),original_hash_failures=origfail,reviewed_sha256=hashes)
(OUT/'independent_recomputation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['portfolios','reviewed_sha256','independent_benchmarks']},indent=2))
