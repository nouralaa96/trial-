"""Independent stdlib recomputation; never imports implementation metrics."""
import csv, hashlib, json
from pathlib import Path
from datetime import date
BASE=Path('/workspace/trading-research-v2')
OUT=Path('/workspace/trading-research-v4/review')
paths={
 'ridge20':BASE/'analysis/eval_loop_v3/portfolios/final/risk05_base_whole/ridge_fixed_h20_a100/equity.csv',
 'simple20':BASE/'analysis/eval_loop_v3/portfolios/final/risk05_base_whole/trend_h20/equity.csv',
 **{s:BASE/f'analysis/market_benchmark/{s}_equity.csv' for s in ['SPY','QQQ','GLD','equal_initial_basket']}}
results={}
for name,p in paths.items():
 rows=list(csv.DictReader(p.open())); vals=[5000.]+[float(r['equity']) for r in rows]
 years=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(rows[0]['date'])).days/365.2425
 peak=5000.; dd=0.
 for v in vals:
  peak=max(peak,v);dd=max(dd,1-v/peak)
 annual={};prev=5000.
 for year in sorted({r['date'][:4] for r in rows}):
  end=float([r for r in rows if r['date'].startswith(year)][-1]['equity']);annual[year]=end/prev-1;prev=end
 results[name]={'end':vals[-1],'profit':vals[-1]-5000.,'cagr':(vals[-1]/5000.)**(1/years)-1,'max_drawdown':dd,'calendar_returns':annual,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
manifest=json.loads((BASE/'data/manifest.json').read_text()); checks={}
for group in ['processed','retrievals']:
 for name,item in manifest[group].items():
  actual=hashlib.sha256((BASE/item['path']).read_bytes()).hexdigest();checks[item['path']]={'expected':item['sha256'],'actual':actual,'pass':actual==item['sha256']}
sm=json.loads((BASE/'artifacts/source-manifest.json').read_text())
for path,expected in sm['sha256'].items():
 actual=hashlib.sha256((BASE/path).read_bytes()).hexdigest();checks[path]={'expected':expected,'actual':actual,'pass':actual==expected}
output={'metrics':results,'frozen_hash_checks':checks,'all_hashes_pass':all(x['pass'] for x in checks.values()),'method':'Initial capital included in drawdown; elapsed calendar days/365.2425; full first year starts at $5000; later years carry previous year-end equity; 2026 is YTD.'}
(OUT/'prior_independent_metrics.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'metrics':results,'all_hashes_pass':output['all_hashes_pass'],'hash_count':len(checks)},indent=2))
