"""Passive market references and actual trade spans; no strategy tuning."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.data import load_panel
OUT=ROOT/'analysis/market_benchmark'


def buy_hold(panel,initial=5000.,fee=1.09,slip=.0005):
    """Equal initial cash sleeves, whole shares, no rebalance/dividend reinvestment.

    Dividend receivables count in equity on ex-date. Settlement timing cannot
    affect quantities because there are no further purchases. Sell at final close.
    """
    index=next(iter(panel.values())).index
    if any(not f.index.equals(index) for f in panel.values()):raise ValueError('Calendars must match')
    if any(not f.splits.isin([0,1]).all() for f in panel.values()):raise ValueError('Split adjustment required')
    cash=initial;marked=pd.Series(0.,index=index);exit_cost=0.;holdings={}
    for symbol,f in panel.items():
        sleeve=initial/len(panel);fill=float(f.open.iloc[0])*(1+slip)
        qty=np.floor(max(0,sleeve-fee)/fill)
        if qty==0:continue
        cash-=qty*fill+fee
        div=f.dividends.copy();div.iloc[0]=0.
        marked+=qty*f.close+qty*div.cumsum()
        exit_cost+=qty*float(f.close.iloc[-1])*slip+fee
        holdings[symbol]=float(qty)
    equity=marked+cash;equity.iloc[-1]-=exit_cost
    return pd.DataFrame({'date':index,'equity':equity.to_numpy()}),holdings


def stats(frame):
    years=(pd.Timestamp(frame.date.iloc[-1])-pd.Timestamp(frame.date.iloc[0])).days/365.25
    vals=np.r_[5000.,frame.equity.to_numpy()]
    return dict(net_pnl=float(vals[-1]-5000),total_return=float(vals[-1]/5000-1),
        cagr=float((vals[-1]/5000)**(1/years)-1),max_drawdown=float(max(1-vals/np.maximum.accumulate(vals))))


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    panel={s:f.loc['2024-01-02':'2026-10-19'].copy() for s,f in load_panel(ROOT/'data').items()}
    inputs=[ROOT/'frozen_config.json',ROOT/'data/manifest.json']+list((ROOT/'data/processed').glob('*.csv'))
    source=ROOT/'analysis/eval_loop_v3/portfolios/final/risk05_base_whole/ridge_fixed_h20_a100'
    inputs += [source/'equity.csv',source/'trades.csv']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    model=pd.read_csv(source/'equity.csv',parse_dates=['date'])[['date','equity']]
    curves={'Ridge20':model};holdings={}
    for name,symbols in [('SPY',['SPY']),('QQQ',['QQQ']),('GLD',['GLD']),('equal_initial_basket',list(panel))]:
        curves[name],holdings[name]=buy_hold({s:panel[s] for s in symbols})
        curves[name].to_csv(OUT/f'{name}_equity.csv',index=False)
    summary=[];yearly=[]
    for name,e in curves.items():
        assert pd.DatetimeIndex(e.date).equals(pd.DatetimeIndex(model.date))
        summary.append(dict(strategy=name,**stats(e)))
        prior=5000.
        for year,g in e.groupby(e.date.dt.year):
            end=float(g.equity.iloc[-1])
            yearly.append(dict(strategy=name,year=int(year),period='YTD through2026-10-19' if year==2026 else 'full calendar year',
                return_fraction=end/prior-1,pnl=end-prior))
            prior=end
    summary=pd.DataFrame(summary);annual=pd.DataFrame(yearly)
    summary.to_csv(OUT/'summary.csv',index=False);annual.to_csv(OUT/'calendar_year_returns.csv',index=False)
    trades=pd.read_csv(source/'trades.csv',parse_dates=['entry_date','exit_date'])
    span=dict(scenario='risk05_base_whole',model='ridge_fixed_h20_a100',completed_trades=len(trades),
        mean_trading_sessions=float(trades.holding_sessions.mean()),median_trading_sessions=float(trades.holding_sessions.median()),
        minimum_trading_sessions=int(trades.holding_sessions.min()),maximum_trading_sessions=int(trades.holding_sessions.max()),
        mean_elapsed_calendar_days=float((trades.exit_date-trades.entry_date).dt.days.mean()),
        first_entry=str(trades.entry_date.min().date()),last_exit=str(trades.exit_date.max().date()),
        reasons=trades.reason.value_counts().to_dict())
    (OUT/'trade_span.json').write_text(json.dumps(span,indent=2)+'\n')
    annual_pivot=annual.pivot(index='year',columns='strategy',values='return_fraction')
    for benchmark in ['SPY','QQQ','GLD','equal_initial_basket']:
        annual_pivot[f'excess_pp_vs_{benchmark}']=100*(annual_pivot.Ridge20-annual_pivot[benchmark])
        #5x applies only to positive benchmark returns, not flat/down markets.
        annual_pivot[f'five_x_positive_target_met_vs_{benchmark}']=np.where(annual_pivot[benchmark]>0,
            annual_pivot.Ridge20>=5*annual_pivot[benchmark],None)
    annual_pivot.to_csv(OUT/'relative_targets.csv')
    lines=['# Market-relative objective and trade duration','',
        'User target: approximately5× a positive annual market return (e.g.50% if the benchmark gains10%). This is a desired research target, not an achieved result or guaranteed return. No strategy or risk limit changed in this diagnostic.','',
        'The strategy trades SPY, QQQ and GLD, so passive references are reported individually and as an equal-initial-cash basket. The basket is a transparent reference, not a user-selected or fitted benchmark. Model performance is the existing5% risk/base-cost/whole-share portfolio.','',
        'Same dates:2024-01-02 through2026-10-19, starting capital$5,000. Passive references buy at the first opening price plus5bps and$1.09 per order, and sell at the last close minus5bps and$1.09. Whole shares, unused cash retained, dividends included as cash/receivables without reinvestment, no rebalancing. The model waits when its rules require; passive purchases are immediate. Passive portfolios do not impose the model’s stops or risk caps, so drawdown is reported for context.','',
        '| Portfolio | Net profit$ | Total return% | Annualized return% | Maximum drawdown% |','|---|---:|---:|---:|---:|']
    for r in summary.itertuples():lines.append(f'| {r.strategy} | {r.net_pnl:.2f} | {100*r.total_return:.2f} | {100*r.cagr:.2f} | {100*r.max_drawdown:.2f} |')
    lines += ['', '| Calendar period | Ridge% | SPY% | QQQ% | GLD% | Equal initial basket% |','|---|---:|---:|---:|---:|---:|']
    for year,r in annual_pivot.iterrows():
        lines.append(f"| {year}{' YTD to Oct19' if year==2026 else ''} | {100*r.Ridge20:.2f} | {100*r.SPY:.2f} | {100*r.QQQ:.2f} | {100*r.GLD:.2f} | {100*r.equal_initial_basket:.2f} |")
    lines += ['', 'Calendar returns are from the carried portfolio, not separate yearly resets.2026 is incomplete and must not be presented as a full-year return. Overall CAGR is a separate multi-year annualization. Ratios to near-zero or negative market returns are not useful targets; use excess percentage points in those cases. The relative_targets.csv file preserves each positive-benchmark5× check.','',
        f"Trade span: {span['completed_trades']} completed trades; mean{span['mean_trading_sessions']:.2f} trading sessions, median{span['median_trading_sessions']:.0f}, range{span['minimum_trading_sessions']}–{span['maximum_trading_sessions']}. Mean elapsed calendar duration{span['mean_elapsed_calendar_days']:.2f} days. First entry{span['first_entry']}, last exit{span['last_exit']}.",
        '', 'The current candidate forecasts20 trading sessions and exits no later than20 sessions, or earlier at a stop, target or risk exit. Signals use completed daily bars and orders may enter the next trading session. This is a swing-trading experiment, not intraday or high-frequency trading. The original strategy used a maximum5-session hold.','',
        'No new tuning or live orders. Underperformance versus passive references must not be hidden by comparing only with a weaker active strategy. The existing10% drawdown target remains unchanged.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (OUT/'provenance.json').write_text(json.dumps({'inputs_sha256':hashes,'inputs_unchanged':True,'holdings':holdings},indent=2)+'\n')
    print(summary.to_string(index=False));print(annual_pivot.to_string())

if __name__=='__main__':run()
