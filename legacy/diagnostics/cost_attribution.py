"""Read-only attribution of frozen executed portfolios; never refit or resimulate."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/cost_attribution'


def attribute(trades, equity, initial=5000.):
    """Cost add-back for the SAME fills/quantity/path, including cash dividends."""
    if equity.empty or equity.open_positions.iloc[-1] != 0 or equity.pending_positions.iloc[-1] != 0:
        raise ValueError('Attribution requires a terminal flat portfolio with no pending entries')
    if 'external_flows' in equity and not np.allclose(equity.external_flows,0):
        raise ValueError('External cash flows need separate attribution')
    net=float(equity.equity.iloc[-1]-initial)
    trades=trades.copy()
    fees=float(trades.fees.sum()) if len(trades) else 0.
    friction=float(trades.friction.sum()) if len(trades) else 0.
    trade_net=float(trades.net_pnl.sum()) if len(trades) else 0.
    if not np.isclose(net,trade_net,rtol=0,atol=1e-6):
        raise ValueError('Trade and marked-equity P/L mismatch')
    if not np.isclose(fees,equity.fees.iloc[-1],rtol=0,atol=1e-6):
        raise ValueError('Commission ledger mismatch')
    if not np.isclose(friction,equity.friction.iloc[-1],rtol=0,atol=1e-6):
        raise ValueError('Friction ledger mismatch')
    if len(trades):
        expected=trades.qty*(trades.exit_price-trades.entry_price)+trades.dividends-trades.fees
        if not np.allclose(expected,trades.net_pnl,rtol=0,atol=1e-6):
            raise ValueError('Fill-price/dividend P/L mismatch')
        if (trades[['fees','friction']] < -1e-8).any().any():
            raise ValueError('Negative modeled costs')
        trades['gross_same_trades']=trades.net_pnl+trades.fees+trades.friction
        trades['before_commissions_after_friction']=trades.net_pnl+trades.fees
    gross=net+fees+friction
    summary={'trades':len(trades),'initial_equity':initial,
        'gross_same_trades':gross,'commissions':fees,'friction':friction,
        'total_direct_cost':fees+friction,'before_commissions_after_friction':net+fees,
        'net_pnl':net,'gross_expectancy':gross/len(trades) if len(trades) else None,
        'net_expectancy':net/len(trades) if len(trades) else None,
        'costs_erased_positive_gross':gross>0 and net<0,
        'gross_was_already_negative':gross<0,
        'terminal_reconciliation_error':abs(net-trade_net)}
    return summary,trades


def difference(ridge,trend):
    gross=ridge['gross_same_trades']-trend['gross_same_trades']
    cost=ridge['total_direct_cost']-trend['total_direct_cost']
    net=ridge['net_pnl']-trend['net_pnl']
    if not np.isclose(gross-cost,net,rtol=0,atol=1e-7):
        raise ValueError('Strategy-difference decomposition mismatch')
    return {'ridge_minus_trend_gross':gross,'ridge_minus_trend_cost':cost,
            'ridge_minus_trend_net':net}


def json_write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def plot(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4),sharey=True)
    for ax,risk in zip(axes,['risk05','risk10']):
        rows=summary[(summary.partition=='final')&(summary.scenario==risk+'_base_whole')].set_index('strategy')
        x=np.arange(2)
        for off,key,label in [(-.18,'gross_same_trades','Before commissions and friction'),(.18,'net_pnl','After commissions and friction')]:
            bars=ax.bar(x+off,[rows.loc[s,key] for s in ['ridge','trend']],.36,label=label)
            ax.bar_label(bars,fmt='%.0f',padding=3)
        ax.set_xticks(x,['Ridge','Simple trend']);ax.axhline(0,color='black',linewidth=.6)
        ax.set_title(('5%' if risk=='risk05' else '10%')+' risk cap; base costs, whole shares')
        ax.set_ylabel('P/L on the same executed trades (USD)')
    axes[0].legend(fontsize=8)
    fig.suptitle('$5,000 portfolios: 2024–2026-10-19 (no strategy change)')
    fig.tight_layout();fig.savefig(OUT/'comparison.png',dpi=160);plt.close(fig)


def report(rows,gaps,forecasts):
    final=rows[rows.partition=='final']
    lines=['# تشخيص Ridge مقابل استراتيجية الاتجاه: الإشارة والتكاليف','',
        '**الخلاصة: التكاليف تمحو أرباح Ridge الخام الصغيرة في معظم السيناريوهات، وأداء صفقاته قبل التكاليف أضعف من الاستراتيجية البسيطة في السيناريوهات الثمانية.**','',
        'لم نغيّر النموذج أو قواعد الدخول أو المخاطرة، ولم نُعِد اختيار الصفقات. هذا تحليل محاسبي للصفقات المنفذة المحفوظة، وليس محاكاة جديدة تُلغى فيها الرسوم.','',
        'رأس المال 5,000 دولار؛ الفترة النهائية 2024–19 أكتوبر 2026. مقارنة الاستراتيجيتين بنفس القواعد والميزانية، لكن صفقاتهما وتعرّضهما للسوق مختلفان.','',
        'الصافي هنا بعد تكاليف التداول المفترضة وقبل تكلفة الاستضافة غير المقاسة. مقارنة الأساسي بالضغط ليست عزلًا للرسوم وحدها، لأن التكاليف أثّرت أيضًا في الصفقات المقبولة وأحجامها.','',
        '## طريقة الفصل','',
        '`الربح قبل العمولات والاحتكاك السعري = الصافي المسجل + العمولات الفعلية + الاحتكاك السعري المسجل`','',
        'يشمل الربح توزيعات الأرباح المستحقة. الاحتكاك السعري هو فرق سعر التنفيذ المفترض الناتج عن الانزلاق، مع احترام حد السعر؛ لا نضيف نسبة انزلاق اسمية مرة أخرى.','',
        'العمود الوسيط يزيل العمولة فقط ويبقي الانزلاق. جمع التكاليف هنا لا يغيّر أحجام الصفقات أو تواريخها أو مسار رأس المال الذي أنتجها. لذلك لا يعني أن استراتيجية أُعيد تشغيلها بلا تكاليف ستعطي الربح الخام نفسه.','',
        '## جميع السيناريوهات النهائية','',
        '| السيناريو | الاستراتيجية | الصفقات | قبل تكاليف التداول المباشرة $ | الانزلاق $ | قبل العمولة وبعد الانزلاق $ | العمولة $ | الصافي $ |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in final.itertuples():
        name=row.scenario.replace('risk05','5%').replace('risk10','10%').replace('base','أساسية').replace('stress','ضغط').replace('whole','كاملة').replace('fractional','كسرية').replace('_',' / ')
        strategy='Ridge' if row.strategy=='ridge' else 'الاتجاه البسيط'
        lines.append(f'| {name} | {strategy} | {row.trades} | {row.gross_same_trades:.2f} | {row.friction:.2f} | {row.before_commissions_after_friction:.2f} | {row.commissions:.2f} | {row.net_pnl:.2f} |')
    lines+=['','![المقارنة قبل التكاليف وبعدها](comparison.png)','',
        '## ما الذي تشير إليه الأرقام؟','',
        '- في السيناريوهات الأساسية الأربعة، أرباح Ridge الخام موجبة وصغيرة، ثم تصبح سالبة بعد التكاليف.','- في ضغط الرسوم مع مخاطرة 10%، صفقات Ridge خاسرة حتى قبل طرح تكاليف التداول؛ إذن لا يمكن تفسير كل الخسارة بالتكاليف وحدها.','- استراتيجية الاتجاه تتفوق على Ridge قبل التكاليف في السيناريوهات الثمانية. تكاليف Ridge الإجمالية أقل من تكاليف الاتجاه، ومع ذلك نتائجه أضعف.','- تتأثر النتائج أيضًا بالاختيار والترتيب والتعرّض وحجم الصفقة والخروج. فرق الربح الخام لا يعزل خطأ التوقع وحده.','',
        '## فحص التوقعات نفسها','',
        '| العينة | التوقعات المكتملة | تحسّن MSE مقابل توقع صفر | دقة اتجاه Ridge | نسبة الارتفاع الفعلية، كمرجع دائم الموجب |',
        '|---|---:|---:|---:|---:|']
    for name in ['development','validation','final']:
        f=forecasts['by_partition'][name]
        lines.append(f"| {name} | {f['n']} | {f['mse_improvement_vs_zero_pct']:.3f}% | {100*f['ridge_direction_accuracy']:.2f}% | {100*f['always_positive_direction_accuracy']:.2f}% |")
    lines+=['','في الفترة النهائية، تحسّن خطأ التنبؤ مقابل الصفر نحو 2.07% فقط؛ دقة الاتجاه 59.29% مقابل 60.50% لمرجع يتوقع اتجاهًا موجبًا دائمًا على العينة نفسها. هذه مقارنة وصفية وليست استراتيجية تداول بديلة مختبرة.','',
        'العوائد المستقبلية لخمس جلسات تتداخل زمنيًا والأصول مترابطة؛ لذلك لا نستنتج دلالة إحصائية مستقلة من هذه النسب. توقع النموذج يخص عائد أفق ثابت، بينما الصفقات قد تنتهي بوقف أو هدف أو إعادة تحقق مبكرة، فلا تتطابق العينتان.','',
        '## حدود الاستنتاج','',
        'الاستنتاج المدعوم هو أن أداء Ridge الحالي لا يتحمل التكاليف، وأن فروق النتائج لا تفسرها الرسوم وحدها. توجد أيضًا إشارات إلى ضعف القدرة التنبؤية، لكن لا نعزو كل الفارق إلى النموذج منفصلًا عن بناء المحفظة والخروج.','',
        'تفوق الاستراتيجية البسيطة في هذه المقارنة لا يكفي لاعتمادها؛ يبقى تقييم السحب الأقصى والمخاطرة وعدم اليقين، ولا توجد نتائج مستقبلية أو تداول حي. لا تعديل جديد مقترح أو مطبّق داخل هذا التحليل.','',
        '## الملفات وإعادة التشغيل','',
        '- `summary.csv`: جميع 48 محفظة Ridge/اتجاه عبر فترات التطوير والتحقق والنهائية، قبل التكاليف وبعدها.','- `gaps.csv`: تحليل الفرق بين الاستراتيجيتين إلى فرق الربح الخام وفرق التكاليف.','- `trade_attribution.csv`: مساهمة كل صفقة؛ `by_asset.csv` و`by_exit_year.csv` تجميع صفقات مقفلة، لا عوائد محفظة سنوية مرجّحة.','- `forecast_metrics.json` و`forecast_note.md`: تحليل مستقل للتوقعات ومطابقة المقاييس الأصلية.','- `REVIEW.md`: المراجعة المستقلة؛ `provenance.json`: بصمات المدخلات المحفوظة، و`test-results.xml`: اختبارات التحليل فقط.','',
        'من `/workspace/trading-research-v2`:', '```bash',
        '.venv/bin/python diagnostics/forecast_diagnosis.py',
        '.venv/bin/python -m pytest -q diagnostics/test_cost_attribution.py --junitxml=analysis/cost_attribution/test-results.xml',
        'MPLCONFIGDIR="$PWD/.cache/matplotlib" .venv/bin/python diagnostics/cost_attribution.py',
        '```']
    (OUT/'REPORT_AR.md').write_text('\n'.join(lines)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    paths=[ROOT/'frozen_config.json',ROOT/'artifacts/historical/metrics.json',
           ROOT/'inputs/ridge_explanations.csv',ROOT/'inputs/prediction_metrics.json']
    original={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source=json.loads((ROOT/'artifacts/historical/metrics.json').read_text())
    summaries=[];gaps=[];all_trades=[];asset=[];year=[]
    for partition,scenarios in source['partitions'].items():
        for scenario in scenarios:
            pair={}
            for strategy in ['ridge','trend']:
                directory=ROOT/'artifacts/historical'/partition/scenario/strategy
                trades=pd.read_csv(directory/'trades.csv'); equity=pd.read_csv(directory/'equity.csv')
                for p in [directory/'trades.csv',directory/'equity.csv']:
                    original[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
                summary,attributed=attribute(trades,equity)
                tags={'partition':partition,'scenario':scenario,'strategy':strategy}
                summaries.append({**tags,**summary});pair[strategy]=summary
                if len(attributed):
                    for key,val in tags.items():attributed[key]=val
                    attributed['exit_year']=pd.to_datetime(attributed.exit_date).dt.year
                    all_trades.append(attributed)
                    for key,dest in [('symbol',asset),('exit_year',year)]:
                        for group,frame in attributed.groupby(key):
                            dest.append({**tags,key:group,'trades':len(frame),
                                **{col:float(frame[col].sum()) for col in ['gross_same_trades','fees','friction','net_pnl']}})
            gaps.append({'partition':partition,'scenario':scenario,**difference(pair['ridge'],pair['trend'])})
    summary=pd.DataFrame(summaries);gap_frame=pd.DataFrame(gaps)
    summary.to_csv(OUT/'summary.csv',index=False);gap_frame.to_csv(OUT/'gaps.csv',index=False)
    pd.concat(all_trades,ignore_index=True).to_csv(OUT/'trade_attribution.csv',index=False)
    pd.DataFrame(asset).to_csv(OUT/'by_asset.csv',index=False);pd.DataFrame(year).to_csv(OUT/'by_exit_year.csv',index=False)
    forecast=json.loads((OUT/'forecast_metrics.json').read_text())
    plot(summary);report(summary,gap_frame,forecast)
    if not all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in original.items()):
        raise AssertionError('A frozen input changed during the diagnostic')
    json_write(OUT/'provenance.json',{'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'method':'same executed trades, direct cost addback; no zero-cost counterfactual or fitting',
        'source_files_unchanged':True,'sha256':original,'portfolios':len(summary),
        'max_terminal_reconciliation_error':float(summary.terminal_reconciliation_error.max())})
    print(json.dumps({'portfolios':len(summary),'report':str(OUT/'REPORT_AR.md'),
                      'max_reconciliation_error':float(summary.terminal_reconciliation_error.max())}))


if __name__=='__main__':main()
