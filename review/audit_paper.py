import hashlib,json,subprocess,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from paper import decide,load_bundle,Refusal
bundle=ROOT/'artifacts/paper_bundle.json';load_bundle(bundle)
checks=[]
for date in ['2024-03-06','2024-03-08','2026-09-21']:
 result=decide(bundle,date=date);e=pd.read_csv(ROOT/'analysis/model/portfolios/final/risk05_base_whole/C03/equity.csv');row=e[e.date==date].iloc[0]
 assert abs(result['account']['equity']-row.equity)<1e-8
 assert result['actionable'] is False and result['broker_connected'] is False
 assert all('label' not in f and 'label_matured' not in f for f in result['forecasts'])
 assert result['status']=='REJECTED_RESEARCH_COUNTERFACTUAL'
 checks.append({'mode':'replay','date':date,'equity':result['account']['equity'],'exact_frozen_equity_match':True,'future_outcomes_omitted':True})
 if date=='2024-03-08':
  check=decide(bundle,date=date,snapshot=result['account']);assert check['account']==result['account']
for args in [['live'],['order'],['paper','--as-of','2026-10-24T05:00:00Z'],['paper','--as-of','2026-10-19T22:00:00Z']]:
 p=subprocess.run([sys.executable,str(ROOT/'paper.py'),*args],capture_output=True,text=True);j=json.loads(p.stdout);assert p.returncode==2 and j['status']=='REFUSED' and j['actionable'] is False
 checks.append({'command':['paper.py',*args],'exit_code':p.returncode,'reason':j['reason']})
paths=[ROOT/n for n in ['paper.py','execution_adapter.py','tests/test_v4_paper.py','artifacts/paper_bundle.json']]
report={'status':'PASS','checks':checks,'reviewed_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(ROOT/'review/paper_recomputation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
