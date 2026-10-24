"""Read-only, retrospective trade-quality diagnostics for both frozen strategies."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.data import load_panel
from research.metrics import portfolio_metrics
OUT = ROOT / 'analysis/trade_quality'
ENDS = {'development':'2021-12-31','validation':'2023-12-31','final':'2026-10-19'}


def drawdowns(equity, initial=5000.):
    """Close-marked drawdowns including initial capital; open episodes are censored."""
    peak, peak_date, start, trough, trough_date = initial, 'initial', None, initial, None
    episodes, underwater, longest = [], 0, 0
    for row in equity.itertuples():
        date, value = str(pd.Timestamp(row.date).date()), float(row.equity)
        if value < peak-1e-8:
            if start is None:
                start, trough, trough_date = date, value, date
            if value < trough:
                trough, trough_date = value, date
            underwater += 1
            longest = max(longest, underwater)
        else:
            if start is not None:
                episodes.append(dict(peak_date=peak_date, first_underwater=start, trough_date=trough_date,
                    recovery_date=date, recovered=True, underwater_sessions=underwater,
                    peak_equity=peak, trough_equity=trough, drawdown_dollars=peak-trough,
                    drawdown_pct=100*(1-trough/peak)))
            peak, peak_date, start, underwater = value, date, None, 0
    if start is not None:
        episodes.append(dict(peak_date=peak_date, first_underwater=start, trough_date=trough_date,
            recovery_date=None, recovered=False, underwater_sessions=underwater,
            peak_equity=peak, trough_equity=trough, drawdown_dollars=peak-trough,
            drawdown_pct=100*(1-trough/peak)))
    return episodes, longest


def loss_streak(trades):
    """Recorded chronological exit order; same-session exits keep engine order."""
    current, worst, amount, start = 0, dict(count=0, net_pnl=0., start=None, end=None), 0., None
    for row in trades.itertuples():
        if row.net_pnl < -1e-8:
            if not current:
                start = str(pd.Timestamp(row.exit_date).date())
            current += 1
            amount += row.net_pnl
            if current > worst['count'] or (current == worst['count'] and amount < worst['net_pnl']):
                worst = dict(count=current, net_pnl=float(amount), start=start,
                             end=str(pd.Timestamp(row.exit_date).date()))
        else:
            current, amount, start = 0, 0., None
    return worst


def trade_path(trade, frame, fee, slip, end):
    """Close observations only; never use a stop/target exit bar's later high/close.

    Post-exit continuation ignores stops/capital constraints and is descriptive,
    not a realizable strategy. Splits explicitly rejected in the diagnostic window.
    """
    i, j = frame.index.get_loc(trade.entry_date), frame.index.get_loc(trade.exit_date)
    if not frame.loc[trade.entry_date:pd.Timestamp(end), 'splits'].isin([0,1]).all():
        raise ValueError('Split-aware path attribution required')
    before = frame.iloc[i:j]
    divs = frame.dividends.iloc[i+1:j].cumsum().reindex(before.index, fill_value=0.)
    path = trade.qty * before.close * (1-slip) - trade.entry_notional + trade.qty*divs - 2*fee
    # Entry and exit bars can have intraday ordering ambiguity; use completed
    # pre-exit closes, then append the actual recorded net exit outcome.
    marked = np.r_[0., path.to_numpy(), trade.net_pnl]
    rec = dict(close_observation_count=len(path), close_mae_dollars=float(-min(marked)),
        close_mfe_dollars=float(max(marked)), prior_positive_close=bool((path>0).any()),
        loss_after_positive_close=bool(trade.net_pnl<0 and (path>0).any()),
        gross_same_trades=float(trade.net_pnl+trade.fees+trade.friction))
    rec['cost_flipped_loss'] = bool(rec['gross_same_trades']>1e-8 and trade.net_pnl < -1e-8)
    rec['gross_flat_net_loss'] = bool(abs(rec['gross_same_trades'])<=1e-8 and trade.net_pnl < -1e-8)
    rec['gross_losing_trade'] = bool(rec['gross_same_trades'] < -1e-8)
    # Five-session outcome measured from ACTUAL entry fill, no stop or target.
    k = i+4
    if k < len(frame) and frame.index[k] <= pd.Timestamp(end):
        div = frame.dividends.iloc[i+1:k+1].sum()*trade.qty
        fixed_net = trade.qty*frame.close.iloc[k]*(1-slip)-trade.entry_notional+div-2*fee
        rec.update(fixed5_net=float(fixed_net), fixed5_negative=bool(fixed_net<0))
    else:
        rec.update(fixed5_net=np.nan, fixed5_negative=None)
    k = j+5
    if k < len(frame) and frame.index[k] <= pd.Timestamp(end):
        div = frame.dividends.iloc[i+1:k+1].sum()*trade.qty
        held_net = trade.qty*frame.close.iloc[k]*(1-slip)-trade.entry_notional+div-2*fee
        rec.update(post5_net_if_held=float(held_net), post5_delta=float(held_net-trade.net_pnl),
            post5_better=bool(held_net>trade.net_pnl), post5_date=str(frame.index[k].date()))
    else:
        rec.update(post5_net_if_held=np.nan, post5_delta=np.nan, post5_better=None, post5_date=None)
    return rec


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cfg = json.loads((ROOT/'frozen_config.json').read_text())
    panel = load_panel(ROOT/'data')
    sources = [ROOT/'frozen_config.json', ROOT/'artifacts/source-manifest.json']
    sources += list((ROOT/'data').rglob('*.csv')) + [ROOT/'data/manifest.json']
    sources += list((ROOT/'artifacts/historical').glob('*/*/*/*.csv'))
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    saved = json.loads((ROOT/'artifacts/historical/metrics.json').read_text())['partitions']
    summaries, all_trades, all_episodes, all_reasons, all_assets, all_decisions = [], [], [], [], [], []
    for partition, end in ENDS.items():
        for scenario, sc in cfg['scenarios'].items():
            for strategy in ('ridge','trend'):
                folder=ROOT/'artifacts/historical'/partition/scenario/strategy
                t=pd.read_csv(folder/'trades.csv',parse_dates=['entry_date','exit_date'])
                e=pd.read_csv(folder/'equity.csv',parse_dates=['date'])
                d=pd.read_csv(folder/'decisions.csv')
                assert t.exit_date.is_monotonic_increasing
                assert e.open_positions.iloc[-1]==0 and e.pending_positions.iloc[-1]==0
                assert abs(t.net_pnl.sum()-(e.equity.iloc[-1]-5000))<1e-6
                key=dict(partition=partition,scenario=scenario,strategy=strategy)
                metrics=portfolio_metrics(e,t,d,initial_equity=5000.)
                for field in ('net_pnl','max_drawdown','win_rate','profit_factor'):
                    assert np.isclose(metrics[field],saved[partition][scenario][strategy][field])
                episodes,longest=drawdowns(e)
                assert longest==metrics['max_drawdown_duration_sessions']
                assert np.isclose(max((x['drawdown_pct'] for x in episodes),default=0),100*metrics['max_drawdown'])
                all_episodes.extend([{**key,**ep} for ep in episodes])
                records=[]
                for idx, trade in enumerate(t.itertuples(index=False)):
                    rec={**key,'trade_number':idx+1,**trade._asdict(),
                         **trade_path(trade,panel[trade.symbol],sc['fee_per_side'],sc['slippage_bps']/10000,end)}
                    records.append(rec)
                paths=pd.DataFrame(records)
                all_trades.extend(records)
                streak=loss_streak(t)
                losses=t.net_pnl[t.net_pnl<0]
                summary={**key,**{f:metrics[f] for f in ('net_pnl','completed_trades','win_rate','profit_factor',
                    'average_win','average_loss','net_expectancy_per_trade','max_drawdown','max_drawdown_dollars',
                    'max_drawdown_duration_sessions','worst_marked_weekly_loss','mean_exposure_fraction_equity')},
                    'losses':len(losses),'worst_trade':float(t.net_pnl.min()),
                    'longest_loss_streak':streak['count'],'streak_net_pnl':streak['net_pnl'],
                    'streak_start':streak['start'],'streak_end':streak['end'],
                    'net_without_best5_same_trades':float(t.net_pnl.sum()-t.net_pnl.nlargest(5).sum()),
                    'gross_losing_trades':int(paths.gross_losing_trade.sum()),
                    'cost_flipped_losses':int(paths.cost_flipped_loss.sum()),
                    'gross_flat_net_losses':int(paths.gross_flat_net_loss.sum()),
                    'losses_after_positive_close':int(paths.loss_after_positive_close.sum()),
                    'fixed5_negative_count':int(paths.fixed5_negative.eq(True).sum()),
                    'fixed5_available':int(paths.fixed5_net.notna().sum()),
                    'post5_better_count':int(paths.post5_better.eq(True).sum()),
                    'post5_available':int(paths.post5_delta.notna().sum()),
                    'post5_median_delta':float(paths.post5_delta.median()),
                    'close_mae_median':float(paths.close_mae_dollars.median()),
                    'close_mfe_median':float(paths.close_mfe_dollars.median())}
                summaries.append(summary)
                for column,dest in [('reason',all_reasons),('symbol',all_assets)]:
                    for name, group in paths.groupby(column):
                        dest.append({**key,column:name,'trades':len(group),'net_pnl':float(group.net_pnl.sum()),
                            'win_rate':float((group.net_pnl>0).mean()),
                            'gross_pnl':float(group.gross_same_trades.sum()),
                            'post5_n':int(group.post5_delta.notna().sum()),
                            'post5_mean_delta':float(group.post5_delta.mean()),
                            'post5_median_delta':float(group.post5_delta.median()),
                            'loss_after_positive_close':int(group.loss_after_positive_close.sum())})
                for (status,reason),g in d.groupby(['status','reason']):
                    all_decisions.append({**key,'status':status,'reason':reason,'count':len(g)})
    for name,rows in [('summary',summaries),('trade_paths',all_trades),('drawdown_episodes',all_episodes),
                      ('by_exit_reason',all_reasons),('by_asset',all_assets),('decisions',all_decisions)]:
        pd.DataFrame(rows).to_csv(OUT/f'{name}.csv',index=False)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in hashes.items())
    (OUT/'provenance.json').write_text(json.dumps({'input_sha256':hashes,'unchanged':True,
        'portfolios':len(summaries),'trades':len(all_trades),'interpretation':'retrospective descriptive only'},indent=2)+'\n')
    print(pd.DataFrame(summaries).query("partition=='final' and scenario.str.endswith('base_whole')",engine='python').to_string(index=False))

if __name__=='__main__':
    run()
