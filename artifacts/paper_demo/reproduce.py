"""Rebuild frozen research-only paper bundle and local demonstration outputs."""
import json
import sys
import subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from paper import freeze_bundle
freeze_bundle(ROOT,'artifacts/models/metadata.json','artifacts/predictions/C03.csv','legacy/frozen_config.json',
 'analysis/model/final_gates.json','artifacts/models/finalist.joblib',
 {s:f'data/processed/{s}.csv' for s in ('SPY','QQQ','GLD')},context='data/context.csv')
out=ROOT/'artifacts/paper_demo'
commands=[
 ('historical_replay',['replay','--date','2024-03-08','--snapshot-out',str(out/'snapshot.json')],0),
 ('historical_exit',['replay','--date','2024-03-06'],0),
 ('snapshot_check',['replay','--date','2024-03-08','--snapshot',str(out/'snapshot.json')],0),
 ('current_refusal',['paper','--as-of',datetime.now(timezone.utc).isoformat()],2),
 ('stale_refusal',['paper','--as-of','2026-10-19T22:00:00Z'],2),
 ('live_refusal',['live'],2),
 ('order_refusal',['order'],2),
 ('status',['status'],0)]
log=[]
for name,args,expected in commands:
 cmd=[sys.executable,str(ROOT/'paper.py'),*args,'--output',str(out/(name+'.json'))]
 r=subprocess.run(cmd,text=True,capture_output=True,cwd=ROOT)
 if r.returncode!=expected:raise RuntimeError((name,r.returncode,r.stdout,r.stderr))
 data=json.loads(r.stdout)
 log.append(dict(name=name,command=cmd,exit_code=r.returncode,status=data['status'],reason=data.get('reason')))
 print(name,r.returncode,data['status'],data.get('reason',''))
helptext=subprocess.run([sys.executable,str(ROOT/'paper.py'),'--help'],text=True,capture_output=True,check=True).stdout
(out/'help.txt').write_text(helptext)
(out/'commands.json').write_text(json.dumps(log,indent=2)+'\n')
import pandas as pd
f=pd.read_csv(ROOT/'analysis/model/portfolios/final/risk05_base_whole/C03/equity.csv')
r=json.loads((out/'historical_replay.json').read_text())
expected=float(f.loc[f.date=='2024-03-08','equity'].iloc[0])
actual=r['account']['equity']
assert abs(actual-expected)<1e-8,(actual,expected)
(out/'parity.json').write_text(json.dumps(dict(date='2024-03-08',scenario='risk05_base_whole',candidate='C03',replay_equity=actual,frozen_evaluation_equity=expected,absolute_difference=abs(actual-expected)),indent=2)+'\n')
print('replay evaluation parity',actual,expected)
