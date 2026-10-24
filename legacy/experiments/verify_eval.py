"""Reconcile every saved portfolio and verify chronology, locks and frozen inputs."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from research.run import audit_result
from research.data import load_panel


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    out=ROOT/'analysis/eval_loop_v3'
    cfg=json.loads((ROOT/'frozen_config.json').read_text())
    tables=[pd.read_csv(out/f'{p}_results.csv') for p in ['development','validation','final','matched_horizon']]
    all_rows=pd.concat(tables,ignore_index=True)
    assert not all_rows.duplicated(['partition','scenario','candidate']).any()
    plan=json.loads((out/'plan.json').read_text())
    for r in all_rows.itertuples():
        folder=out/'portfolios'/r.partition/r.scenario/r.candidate
        frames={name:pd.read_csv(folder/f'{name}.csv') for name in ['equity','trades','decisions']}
        e,t=frames['equity'],frames['trades']
        assert e.open_positions.iloc[-1]==0 and e.pending_positions.iloc[-1]==0
        assert np.isclose(t.net_pnl.sum(),r.net_pnl,rtol=0,atol=1e-6)
        assert np.isclose(e.equity.iloc[-1]-5000,r.net_pnl,rtol=0,atol=1e-6)
        assert np.isclose(t.fees.sum(),r.fees,rtol=0,atol=1e-6)
        assert np.isclose(t.friction.sum(),r.friction,rtol=0,atol=1e-6)
        assert len(t)==r.completed_trades
        values=np.r_[5000,e.equity.to_numpy()]
        assert np.isclose(max(1-values/np.maximum.accumulate(values)),r.max_drawdown,rtol=0,atol=1e-12)
        years=(pd.Timestamp(e.date.iloc[-1])-pd.Timestamp(e.date.iloc[0])).days/365.25
        assert np.isclose((e.equity.iloc[-1]/5000)**(1/years)-1,r.cagr,rtol=0,atol=1e-12)
        assert not audit_result(frames,{**cfg,**cfg['scenarios'][r.scenario]})['violations']
    calendar=next(iter(load_panel(ROOT/'data').values())).index
    fits_count=0
    for file in (out/'predictions').glob('*/*/fits.json'):
        for fit in json.loads(file.read_text()):
            first=pd.Timestamp(fit['first_decision']);cutoff=pd.Timestamp(fit['cutoff'])
            assert pd.Timestamp(fit['max_training_maturity'])<=cutoff
            assert calendar.get_loc(first)-calendar.get_loc(cutoff)==11
            fits_count+=1
    events=[json.loads(x) for x in (out/'events.jsonl').read_text().splitlines()]
    assert events[0]['plan_sha256']==sha(out/'plan.json')
    lock=next(x for x in events if x['event']=='final_candidates_locked')
    assert lock['sha256']==sha(out/'locked.json')
    assert all(x['utc']>lock['utc'] for x in events if x.get('partition')=='final')
    original=json.loads((ROOT/'artifacts/source-manifest.json').read_text())['sha256']
    previous=json.loads((ROOT/'analysis/trade_quality/provenance.json').read_text())['input_sha256']
    for name,digest in {**original,**previous}.items():assert sha(ROOT/name)==digest,name
    sources={str(p.relative_to(ROOT)):sha(p) for folder in ['experiments','diagnostics'] for p in (ROOT/folder).glob('*.py')}
    model_manifest=json.loads((out/'research_models/manifest.json').read_text())
    for m in model_manifest:assert sha(out/m['path'])==m['sha256']
    report=dict(portfolios_reconciled=len(all_rows),quarterly_fits_checked=fits_count,
        original_frozen_sources_unchanged=len(original),previous_diagnostic_inputs_unchanged=len(previous),
        final_selection_lock_unchanged=True,exported_model_hashes_verified=len(model_manifest),
        source_sha256=sources,plan_sha256=sha(out/'plan.json'))
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}))

if __name__=='__main__':run()
