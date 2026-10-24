import json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];M=ROOT/'analysis/model'
outputs=[]
def weekly(stage,scenario,cid):
 e=pd.read_csv(M/'portfolios'/stage/scenario/cid/'equity.csv',parse_dates=['date']);v=e.equity.to_numpy();daily=np.diff(np.r_[5000.,v]);return pd.Series(daily,index=e.date).resample('W-SUN').sum()
for stage in ['validation','final']:
 gates=json.loads((M/f'{stage}_gates.json').read_text());results=pd.read_csv(M/f'{stage}_results.csv');sel=results[results.candidate=='C03'];base=sel[sel.scenario.str.contains('_base_')];stress=sel[sel.scenario.str.contains('_stress_')]
 checks={'base_profitable':bool((base.net_pnl>0).all()),'stress_profitable':bool((stress.net_pnl>0).all()),'base_drawdown_at_most_10pct':bool((base.max_drawdown<=.1).all()),'stress_drawdown_at_most_10pct':bool((stress.max_drawdown<=.1).all()),'minimum_100_completed_trades':bool((sel.completed_trades>=100).all())}
 comparisons=[]
 for comparison in gates['comparisons']:
  a=weekly(stage,comparison['scenario'],'C03');b=weekly(stage,comparison['scenario'],comparison['reference']);assert a.index.equals(b.index);delta=(a-b).to_numpy();n=len(delta);boot=comparison['bootstrap'];assert n==boot['weeks'];assert np.isclose(delta.sum(),boot['incremental_net_pnl'])
  bounds={}
  for block in [2,4,8]:
   rng=np.random.default_rng(20261021+block);starts=rng.integers(n,size=(2000,int(np.ceil(n/block))));ix=((starts[:,:,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
   ci=np.quantile(delta[ix].mean(1)*52,[.025,.975]);assert np.allclose(ci,boot['block_sensitivity'][str(block)]['ci95'],atol=1e-8);bounds[str(block)]=ci.tolist()
  comparisons.append({'scenario':comparison['scenario'],'reference':comparison['reference'],'ci95_annual_incremental_dollars':bounds})
 annual=[];years=pd.read_csv(M/f'{stage}_yearly.csv')
 for row in gates['annual_market_targets']:
  s=years[(years.scenario==row['scenario'])&(years.year==row['year'])];r=float(s[s.candidate=='C03'].return_fraction.iloc[0]);b=float(s[s.candidate=='SPY_reinvested_total_return'].return_fraction.iloc[0]);assert np.isclose(row['strategy_return'],r) and np.isclose(row['spy_total_return'],b)
  test=None if row['partial'] or b<=0 else bool(r>=5*b);assert test==row['five_times_gate'];annual.append(test)
 checks['positive_increment_over_both_baselines_each_base_scenario']=all(c['cagr_increment']>0 for c in gates['comparisons'])
 checks['exploratory_paired_CI_lower_positive_all_block_lengths']=all(v[0]>0 for c in comparisons for v in c['ci95_annual_incremental_dollars'].values())
 tests=[a for a in annual if a is not None];checks['five_times_positive_SPY_full_calendar_years']=bool(tests) and all(tests)
 assert checks==gates['checks'];assert all(checks.values())==gates['all_gates_pass']
 outputs.append({'partition':stage,'all_gates_pass':all(checks.values()),'checks':checks,'comparisons':comparisons})
report={'status':'PASS','gates_independently_match':True,'bootstrap_comparison_count':sum(len(o['comparisons']) for o in outputs),'estimand':'Annual arithmetic incremental dollars; not CAGR confidence interval or selection-adjusted evidence','stages':outputs}
(ROOT/'review/gate_recomputation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'PASS','comparisons':report['bootstrap_comparison_count'],'checks':[o['checks'] for o in outputs]},indent=2))
