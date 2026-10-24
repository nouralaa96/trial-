"""Local research replay and guarded paper inspection. No order or broker API.

A bundle binds forecasts, model, gates, config and input files by SHA256. Historical
replay reconstructs the selected portfolio from its frozen period start; it does
not fabricate an empty account or use a final model to back-predict past dates.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime, timezone, date
import numpy as np
import pandas as pd
from execution_adapter import ROOT, run_engine
from legacy.research.features import build_features
from legacy.research.execution import ExchangeCalendar

class Refusal(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, default=str, allow_nan=False)+'\n')


def local_file(root, name):
    p = (root/name).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise Refusal('missing_or_outside_bundle_file: '+str(name))
    return p


def freeze_bundle(root, metadata, predictions, config, gates, model, data_paths,
                  start='2024-01-02', end='2026-10-19', context=None, output='artifacts/paper_bundle.json'):
    root = Path(root).resolve()
    files = dict(metadata=metadata, predictions=predictions, config=config, gates=gates, model=model)
    files.update({'data_'+s: p for s, p in data_paths.items()})
    if context:
        files['context'] = context
    # Bind executable semantics and the frozen candidate declaration as well.
    for key, name in [('paper_source','paper.py'),('execution_source','execution_adapter.py'),
                      ('registry','analysis/model/registry.json')]:
        if (root/name).is_file():
            files[key] = name
    hashes = {name: dict(path=str(local_file(root, p).relative_to(root)), sha256=sha(root/p)) for name, p in files.items()}
    meta = json.loads((root/metadata).read_text())
    bundle = dict(schema_version=1, purpose='RESEARCH_PAPER_ONLY', created_at=datetime.now(timezone.utc).isoformat(),
        candidate=meta.get('candidate', meta.get('candidate_id', 'unknown')),
        status=meta.get('status', 'REJECTED_RESEARCH'), evaluation_start=start, evaluation_end=end,
        max_model_age_days=110, context_max_age_days=5, files=hashes)
    write_json(root/output, bundle)
    return bundle


def load_bundle(path, root=ROOT):
    path, root = Path(path), Path(root).resolve()
    if not path.is_file():
        raise Refusal('missing_frozen_bundle')
    b = json.loads(path.read_text())
    if b.get('schema_version') != 1 or b.get('purpose') != 'RESEARCH_PAPER_ONLY':
        raise Refusal('invalid_bundle_schema_or_purpose')
    required = {'metadata','predictions','config','gates','model','data_SPY','data_QQQ','data_GLD'}
    if not required.issubset(b.get('files', {})):
        raise Refusal('missing_bundle_inputs')
    for name, entry in b['files'].items():
        p = local_file(root, entry['path'])
        if sha(p) != entry['sha256']:
            raise Refusal('provenance_hash_mismatch: '+name)
    meta = json.loads(local_file(root,b['files']['metadata']['path']).read_text())
    for name, digest in meta.get('data_hashes', {}).items():
        if sha(local_file(root,name)) != digest:
            raise Refusal('model_data_provenance_mismatch: '+name)
    for name, digest in meta.get('source_hashes', {}).items():
        if sha(local_file(root,name)) != digest:
            raise Refusal('model_source_provenance_mismatch: '+name)
    if meta.get('candidate',meta.get('candidate_id')) != b.get('candidate'):
        raise Refusal('model_candidate_provenance_mismatch')
    return b


def validate_bars(panel, date, calendar=None):
    cal = calendar or ExchangeCalendar()
    date = pd.Timestamp(date).normalize()
    for symbol in ('SPY','QQQ','GLD'):
        if symbol not in panel:
            raise Refusal('missing_required_asset: '+symbol)
        f = panel[symbol]
        if not f.index.is_unique or not f.index.is_monotonic_increasing:
            raise Refusal('duplicate_or_unordered_bars: '+symbol)
        if date not in f.index:
            raise Refusal('missing_or_stale_completed_bar: '+symbol)
        history = f.loc[:date]
        expected = cal.sessions[(cal.sessions >= history.index[0]) & (cal.sessions <= date)]
        if not history.index.equals(expected) or len(history) < 60:
            raise Refusal('incomplete_required_bar_history: '+symbol)
        required = ['open','high','low','close','volume','dividends','splits']
        if any(k not in history for k in required) or not np.isfinite(history[required].to_numpy()).all():
            raise Refusal('missing_or_nonfinite_bar_values: '+symbol)
        if ((history[['open','high','low','close','volume']] <= 0).any().any()
            or (history.high < history[['open','close','low']].max(axis=1)).any()
            or (history.low > history[['open','close','high']].min(axis=1)).any()
            or (history.dividends < 0).any() or (history.splits < 0).any()):
            raise Refusal('invalid_ohlcv_or_corporate_action: '+symbol)


def asof_session(as_of, now=None, calendar=None):
    """Require explicit known timezone and a fully completed latest XNYS session."""
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is None:
        raise Refusal('as_of_requires_explicit_timezone')
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if stamp > now:
        raise Refusal('future_as_of_timestamp')
    cal = (calendar or ExchangeCalendar()).calendar
    completed = [d for d in cal.sessions if cal.session_close(d) <= stamp]
    if not completed:
        raise Refusal('no_completed_session')
    return pd.Timestamp(completed[-1]).tz_localize(None).normalize()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp,datetime,date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def portfolio_snapshot(engine, bundle_digest):
    engine.assert_accounting()
    return clean(dict(schema_version=1, bundle_sha256=bundle_digest, as_of=str(engine.date.date()),
        initial_cash=engine.initial_cash, settled_cash=engine.settled,
        unsettled_cash=[dict(available_date=d,amount=a,kind=k) for d,a,k in engine.unsettled],
        positions={s: asdict(p) for s,p in engine.positions.items()},
        pending={s: asdict(p) for s,p in engine.pending.items()}, marks=engine.marks,
        risk=asdict(engine.risk), equity=engine.equity, fees=engine.total_fees,
        friction=engine.total_friction))


def check_snapshot(snapshot, expected):
    """A paper ledger is accepted only if it exactly matches frozen replay state."""
    if snapshot.get('schema_version') != 1 or snapshot.get('as_of') != expected['as_of']:
        raise Refusal('snapshot_missing_stale_or_future_timestamp')
    if snapshot.get('bundle_sha256') != expected['bundle_sha256']:
        raise Refusal('snapshot_provenance_mismatch')
    if snapshot != expected:
        raise Refusal('snapshot_ledger_or_risk_mismatch')


def decide(bundle_path, date=None, as_of=None, mode='replay', scenario='risk05_base_whole',
           root=ROOT, snapshot=None, now=None):
    if mode not in ('replay','paper'):
        raise Refusal('live_and_order_actions_unsupported')
    root = Path(root).resolve()
    b = load_bundle(bundle_path, root)
    files = {k: local_file(root,v['path']) for k,v in b['files'].items()}
    cal = ExchangeCalendar()
    if mode == 'paper':
        if not as_of:
            raise Refusal('paper_requires_as_of_timestamp')
        date = asof_session(as_of, now=now, calendar=cal)
        wall = pd.Timestamp(now or datetime.now(timezone.utc))
        if (wall-pd.Timestamp(as_of) > pd.Timedelta(days=3)
                or date != asof_session(wall.isoformat(), now=wall, calendar=cal)):
            raise Refusal('stale_paper_as_of_use_historical_replay')
    elif date:
        date = pd.Timestamp(date)
        if date.tzinfo is not None or date != date.normalize():
            raise Refusal('replay_date_must_be_plain_session_date')
        if date > pd.Timestamp.now(tz='UTC').tz_localize(None).normalize():
            raise Refusal('future_replay_date')
    else:
        raise Refusal('replay_requires_date')
    if date not in cal.sessions:
        raise Refusal('not_an_exchange_session')
    panel = {s: pd.read_csv(files['data_'+s], index_col='date', parse_dates=True) for s in ('SPY','QQQ','GLD')}
    validate_bars(panel, date, cal)
    if not pd.Timestamp(b['evaluation_start']) <= date <= pd.Timestamp(b['evaluation_end']):
        raise Refusal('outside_frozen_forecast_period')
    forecasts = pd.read_csv(files['predictions'], parse_dates=['date'])
    required = {'date','symbol','prediction','prediction_low','confidence','training_cutoff','first_decision'}
    if not required.issubset(forecasts):
        raise Refusal('missing_forecast_columns')
    if forecasts.duplicated(['date','symbol']).any():
        raise Refusal('duplicate_forecasts')
    rows = forecasts[forecasts.date == date].copy()
    if set(rows.symbol) != set(panel):
        raise Refusal('missing_dated_model_forecasts')
    confidence_required = b['candidate'] in {'C03','C04'}
    for _, row in rows.iterrows():
        cutoff, available = pd.Timestamp(row.training_cutoff), pd.Timestamp(row.first_decision)
        if pd.isna(cutoff) or pd.isna(available) or cutoff >= date or available > date:
            raise Refusal('future_or_missing_model_timestamp')
        if (date-available).days > b['max_model_age_days']:
            raise Refusal('stale_model_refit')
        # P01/P02 have no calibration layer and therefore declare confidence
        # unavailable.  C03/C04 do use the frozen residual diagnostic and must
        # provide a finite value. Missing predictions require an explicit
        # rejected-admission flag; absence alone is never a forecast.
        confidence = pd.to_numeric(pd.Series([row.confidence]),errors='coerce').iloc[0]
        if confidence_required and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise Refusal('missing_or_invalid_required_confidence_diagnostic')
        if not confidence_required and math.isfinite(confidence) and not 0 <= confidence <= 1:
            raise Refusal('invalid_optional_confidence_diagnostic')
        if pd.isna(row.prediction) and row.get('admitted',True) not in (False,0,'False'):
            raise Refusal('missing_required_model_prediction')
        if not pd.isna(row.prediction) and not math.isfinite(float(row.prediction)):
            raise Refusal('nonfinite_model_prediction')
    context_snapshot = None
    if 'context' in files:
        ctx = pd.read_csv(files['context'])
        if not {'date','available_date','vix_close_pct'}.issubset(ctx):
            raise Refusal('missing_context_timestamp_or_required_values')
        ctx['date'] = pd.to_datetime(ctx.date)
        ctx['available_date'] = pd.to_datetime(ctx.available_date)
        if ctx.available_date.duplicated().any() or not (ctx.available_date > ctx.date).all():
            raise Refusal('invalid_context_availability')
        # Exact next-session availability contract: never carry stale September
        # observations into later padded October rows or accept future release.
        ctx = ctx.sort_values('date')
        ctx['vix_change20'] = ctx.vix_close_pct.diff(20)
        current = ctx[(ctx.available_date == date) & (ctx.date < date)]
        if len(current) != 1 or not np.isfinite(current[['vix_close_pct','vix_change20']].to_numpy()).all():
            raise Refusal('missing_or_stale_context_data')
        context_snapshot = current[['date','available_date','vix_close_pct','vix_change20']].to_dict('records')[0]
    config = json.loads(files['config'].read_text())
    if scenario not in config.get('scenarios', {}):
        raise Refusal('unknown_frozen_risk_cost_scenario')
    config = {**config, **config['scenarios'][scenario], 'max_holding_sessions':20}
    metadata = json.loads(files['metadata'].read_text())
    gates = json.loads(files['gates'].read_text())
    # Historical rows were emitted by causally separated fits, never recomputed
    # here with the final saved pipeline. All future bars are ignored by driver.
    features = build_features(panel)
    predictions = forecasts.pivot(index='date',columns='symbol',values='prediction')
    result = run_engine(features,predictions,config,start=b['evaluation_start'],end=b['evaluation_end'],
                        replay_through=date,return_engine=True)
    engine = result['engine']
    current = portfolio_snapshot(engine,sha(bundle_path))
    if snapshot is not None:
        check_snapshot(snapshot,current)
    day = [r for r in engine.decisions if r['date'] == date]
    approved = b['status'] == 'APPROVED_PAPER' and metadata.get('status') == 'APPROVED_PAPER' and (gates.get('status') == 'PASS' or gates.get('all_gates_pass') is True)
    if mode == 'paper' and not approved:
        raise Refusal('strategy_not_approved: '+str(b['status']))
    public_forecast_fields=['date','symbol','prediction','prediction_low','confidence',
                            'training_cutoff','first_decision','group','quarter','admitted']
    public_forecasts=rows[[c for c in public_forecast_fields if c in rows]].to_dict('records')
    return clean(dict(mode=mode,status='APPROVED_PAPER' if approved else 'REJECTED_RESEARCH_COUNTERFACTUAL',
        actionable=False, broker_connected=False, candidate=b['candidate'], as_of_session=str(date.date()),
        scenario=scenario, bundle_sha256=sha(bundle_path), gates=gates,
        completed_bars={symbol:frame.loc[date].to_dict() for symbol,frame in panel.items()}, context=context_snapshot,
        rationale='Frozen historical research replay; failed gates prohibit actionable strategy.' if not approved else 'Local paper inspection only; no executable orders.',
        account=current, forecasts=public_forecasts, decisions=day,
        entry_plans={s: asdict(p) for s,p in engine.pending.items()},
        exits_today=[r for r in day if r['status']=='exited'],
        assumptions=dict(cash_only=True,leverage=False,max_positions=3,max_candidates_per_session=2,
            max_entries_per_session=1,capital_floor=config.get('capital_floor',160.),
            trade_risk_fraction=config['per_trade_risk_fraction'],session_risk_fraction=config.get('session_risk_fraction'),
            weekly_risk_fraction=config.get('weekly_risk_fraction'),max_drawdown_target=.10,
            max_drawdown_guaranteed=False,settlement='T+1 from2024-05-28; historical T+2/T+3',
            slippage_bps=config['slippage_bps'],fee_per_side=config['fee_per_side'],
            stop_atr=config['stop_atr'],target_atr=config['target_atr'],holding_limit_sessions=20,
            limit_fills='Full fills or cancellation; daily OHLC small-order liquidity assumption; stop-first ambiguity.',
            gap_risk='Stop and weekly budgets can be exceeded by opening gaps.',
            confidence='Residual-scale diagnostic, not calibrated probability of profit.')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['replay','paper','live','order','status'])
    parser.add_argument('--bundle',default=str(ROOT/'artifacts/paper_bundle.json'))
    parser.add_argument('--date')
    parser.add_argument('--as-of')
    parser.add_argument('--scenario',default='risk05_base_whole')
    parser.add_argument('--snapshot')
    parser.add_argument('--snapshot-out')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        if args.mode in ('live','order'):
            raise Refusal('live_and_order_actions_unsupported')
        if args.mode == 'status':
            b=load_bundle(args.bundle)
            out=dict(mode='status',status=b['status'],candidate=b['candidate'],actionable=False,
                broker_connected=False,period=[b['evaluation_start'],b['evaluation_end']],
                gates=json.loads(local_file(ROOT,b['files']['gates']['path']).read_text()))
        else:
            snapshot=json.loads(Path(args.snapshot).read_text()) if args.snapshot else None
            out=decide(args.bundle,date=args.date,as_of=args.as_of,mode=args.mode,scenario=args.scenario,snapshot=snapshot)
        if args.snapshot_out and 'account' in out:
            write_json(args.snapshot_out,out['account'])
        code=0
    except (Refusal,ValueError,KeyError,FileNotFoundError,TypeError) as exc:
        out=dict(mode=args.mode,status='REFUSED',reason=str(exc),actionable=False,broker_connected=False)
        code=2
    if args.output:
        write_json(args.output,out)
    print(json.dumps(out,indent=2,default=str,allow_nan=False))
    return code

if __name__=='__main__':
    raise SystemExit(main())
