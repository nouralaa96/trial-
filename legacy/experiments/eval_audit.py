"""Supplement locked-candidate evaluation with identical-horizon benchmarks and model exports."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import joblib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.eval_loop import (OUT,write_json,digest,run_stage,candidates,training_rows,fit_predict,
                                  bracket_labels,load_equity,ledger)
from research.data import load_panel
from research.features import build_features,executable_labels,FEATURE_COLUMNS
from research.modeling import _pooled,GROUPS
from research.metrics import paired_weekly_bootstrap


def run():
    plan=json.loads((OUT/'plan.json').read_text());locked=json.loads((OUT/'locked.json').read_text())
    catalog=candidates(plan);lock_hash=digest(OUT/'locked.json')
    ids={r:[f"trend_h{catalog[e['ridge']]['horizon']}"] for r,e in locked.items()}
    ledger('supplemental_benchmark_started',plan_sha256=digest(OUT/'supplemental_plan.json'),locked_sha256=lock_hash)
    original_hashes={str(p):digest(p) for p in OUT.glob('*_results.csv')}
    results=[]
    # run_stage writes progress CSV; retain the original selection tables exactly.
    for partition in ('validation','final'):
        original=(OUT/f'{partition}_results.csv').read_bytes()
        try:
            f=run_stage(partition,plan,catalog,ids)
            results.extend(f.to_dict('records'))
        finally:
            (OUT/f'{partition}_results.csv').write_bytes(original)
    pd.DataFrame(results).to_csv(OUT/'matched_horizon_results.csv',index=False)
    final=pd.read_csv(OUT/'final_results.csv');extra=pd.DataFrame(results);comparisons=[]
    for risk,entry in locked.items():
        cid=entry['ridge'];benchmark=ids[risk][0]
        for scenario in final[(final.risk==risk)&(final.candidate==cid)].scenario:
            row=final[(final.scenario==scenario)&(final.candidate==cid)].iloc[0]
            base=extra[(extra.partition=='final')&(extra.scenario==scenario)].iloc[0]
            boot=paired_weekly_bootstrap(load_equity('final',scenario,cid),load_equity('final',scenario,benchmark),
                initial_equity=5000.,resamples=10000,seed=20261020,block_lengths=(2,4,8))
            comparisons.append(dict(risk=risk,scenario=scenario,model=cid,benchmark=benchmark,
                model_cagr=row.cagr,benchmark_cagr=base.cagr,model_drawdown=row.max_drawdown,
                benchmark_drawdown=base.max_drawdown,annual_increment_dollars=(row.net_pnl-base.net_pnl)/row.years,
                bootstrap=boot))
    write_json(OUT/'matched_horizon_comparisons.json',comparisons)
    # Reconstruct/export the latest already-evaluated quarterly fit, and verify
    # predictions against the recorded final series. This is not a new refit date.
    raw=load_panel(ROOT/'data');features=build_features(raw);exports=[]
    for cid in sorted(set(e['ridge'] for e in locked.values())):
        cand=catalog[cid];labeled={}
        for symbol,f in features.items():
            y=executable_labels(f,cand['horizon']) if cand['label']=='fixed' else bracket_labels(f,cand['horizon'])
            labeled[symbol]=f.drop(columns=['label','label_matured']).join(y)
        folder=OUT/'predictions/final'/cid
        fits=json.loads((folder/'fits.json').read_text())
        saved=pd.read_csv(folder/'predictions.csv',parse_dates=['date'])
        for group,symbols in GROUPS.items():
            fit=max((x for x in fits if x['group']==group),key=lambda x:x['first_decision'])
            rows=_pooled(labeled,symbols);cutoff=pd.Timestamp(fit['cutoff'])
            train=training_rows(rows,cutoff)
            test=rows[(rows.date>=fit['first_decision'])&np.isfinite(rows[FEATURE_COLUMNS]).all(axis=1)]
            p,model=fit_predict(train,test,cand['alpha'])
            expected=test[['date','symbol']].merge(saved[['date','symbol','prediction']],on=['date','symbol'],validate='one_to_one')
            assert len(expected)==len(test) and np.allclose(p,expected.prediction,rtol=0,atol=1e-12)
            dest=OUT/'research_models'/cid/f'{group}.joblib';dest.parent.mkdir(parents=True,exist_ok=True)
            joblib.dump(model,dest)
            restored=joblib.load(dest)
            assert np.allclose(restored.predict(test[FEATURE_COLUMNS]),p,rtol=0,atol=1e-12)
            exports.append(dict(candidate=cid,group=group,path=str(dest.relative_to(OUT)),sha256=digest(dest),
                training_cutoff=fit['cutoff'],first_evaluated_decision=fit['first_decision'],
                feature_columns=FEATURE_COLUMNS,predictions_verified=len(test),status='research_only_not_live_approved'))
    write_json(OUT/'research_models/manifest.json',exports)
    assert digest(OUT/'locked.json')==lock_hash
    assert all(digest(Path(p))==h for p,h in original_hashes.items())
    ledger('supplemental_audit_completed',additional_portfolios=len(results),exported_models=len(exports))
    print(json.dumps({'additional_portfolios':len(results),'models':len(exports),'locked_selection_unchanged':True}))

if __name__=='__main__':run()
