"""Reconcile V4's final C03/T05/SPY ledgers and classify the C03/T05 gap.

Read-only with respect to V4 inputs. Writes one JSON report to the path supplied.
Entry classifications are an accounting diagnostic, not counterfactual causal P/L.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "analysis/model/portfolios/final/risk05_base_whole"
METRICS = ROOT / "analysis/model/final_metrics.json"
NAMES = ("C03", "T05", "SPY_cash_dividend")


def rounded(value):
    return round(float(value), 6)


def trade_summary(trades):
    fees = trades.fees.sum()
    friction = trades.friction.sum()
    net = trades.net_pnl.sum()
    out = {
        "trades": len(trades),
        "net_pnl": rounded(net),
        "fees": rounded(fees),
        "friction": rounded(friction),
        "gross_before_modeled_costs": rounded(net + fees + friction),
        "winning_trades": int((trades.net_pnl > 0).sum()),
        "losing_trades": int((trades.net_pnl < 0).sum()),
        "longest_loss_streak": 0,
        "by_symbol": {},
        "by_exit_reason": {},
        "by_exit_year": {},
    }
    streak = 0
    for value in trades.sort_values("exit_date").net_pnl:
        streak = streak + 1 if value < 0 else 0
        out["longest_loss_streak"] = max(streak, out["longest_loss_streak"])
    for column, target in (("symbol", "by_symbol"), ("reason", "by_exit_reason")):
        out[target] = {str(key): {"trades": len(group), "net_pnl": rounded(group.net_pnl.sum())}
                       for key, group in trades.groupby(column)}
    out["by_exit_year"] = {str(key): {"trades": len(group), "net_pnl": rounded(group.net_pnl.sum())}
                           for key, group in trades.groupby(trades.exit_date.str[:4])}
    return out


def entry_classification(c, t):
    key = ["symbol", "entry_date"]
    if c.duplicated(key).any() or t.duplicated(key).any():
        raise ValueError("Duplicate symbol/entry date; matching needs a lot identifier")
    pair = c.merge(t, on=key, how="outer", suffixes=("_c03", "_t05"), indicator=True)
    same_entry = pair[pair._merge == "both"]
    c_only = pair[pair._merge == "left_only"]
    t_only = pair[pair._merge == "right_only"]
    matched_gap = (same_entry.net_pnl_t05 - same_entry.net_pnl_c03).sum()
    t_only_gain = t_only.net_pnl_t05.sum()
    c_only_subtraction = -c_only.net_pnl_c03.sum()
    result = {
        "shared_entry_count": len(same_entry),
        "shared_entry_same_exit_count": int((same_entry.exit_date_c03 == same_entry.exit_date_t05).sum()),
        "shared_entry_different_exit_count": int((same_entry.exit_date_c03 != same_entry.exit_date_t05).sum()),
        "shared_entry_net_gap_t05_minus_c03": rounded(matched_gap),
        "t05_only_entry_count": len(t_only),
        "t05_only_net_contribution": rounded(t_only_gain),
        "c03_only_entry_count": len(c_only),
        "negative_c03_only_net_contribution": rounded(c_only_subtraction),
        "t05_only_by_symbol": {str(k): {"trades": len(g), "net_pnl": rounded(g.net_pnl_t05.sum())}
                               for k, g in t_only.groupby("symbol")},
        "c03_only_by_symbol": {str(k): {"trades": len(g), "net_pnl": rounded(g.net_pnl_c03.sum())}
                               for k, g in c_only.groupby("symbol")},
        "largest_t05_only_wins": [
            {"symbol": row.symbol, "entry_date": row.entry_date,
             "exit_date": row.exit_date_t05, "net_pnl": rounded(row.net_pnl_t05)}
            for row in t_only.nlargest(5, "net_pnl_t05").itertuples()
        ],
        "total_gap_reconciled": rounded(matched_gap + t_only_gain + c_only_subtraction),
        "meaning": "Accounting partition by same-symbol same-entry-date. Different equity paths, sizing and exits prevent a causal entry/exit attribution.",
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    metrics = {(m["scenario"], m["candidate"]): m for m in json.loads(METRICS.read_text())}
    trades = {name: pd.read_csv(BASE / name / "trades.csv") for name in NAMES}
    equity = {name: pd.read_csv(BASE / name / "equity.csv") for name in NAMES}
    summaries = {}
    for name in NAMES:
        m = metrics["risk05_base_whole", name]
        e = equity[name]
        s = trade_summary(trades[name])
        if abs(s["net_pnl"] - m["net_pnl"]) > 1e-4:
            raise AssertionError(f"Trade P/L does not reconcile for {name}")
        if abs(e.equity.iloc[-1] - m["initial_equity"] - m["net_pnl"]) > 1e-4:
            raise AssertionError(f"Equity does not reconcile for {name}")
        if abs(s["fees"] - m["fees"]) > 1e-4 or abs(s["friction"] - m["friction"]) > 1e-4:
            raise AssertionError(f"Trade costs do not reconcile for {name}")
        s.update({"start": str(e.date.iloc[0]), "end": str(e.date.iloc[-1]),
                  "ending_equity": rounded(e.equity.iloc[-1]),
                  "cagr_pct": rounded(100 * m["cagr"]),
                  "max_drawdown_pct": rounded(100 * m["max_drawdown"]),
                  "mean_marked_exposure_pct": rounded(100 * m["mean_exposure_fraction_equity"]),
                  "underwater_sessions_max": int(m["max_drawdown_duration_sessions"])})
        summaries[name] = s
    dates = [equity[name].date.tolist() for name in NAMES]
    if not dates[0] == dates[1] == dates[2]:
        raise AssertionError("Comparisons require the same valuation dates")
    c, t, spy = [summaries[name] for name in NAMES]
    gap = rounded(t["net_pnl"] - c["net_pnl"])
    cost_gap = rounded((t["fees"] + t["friction"]) - (c["fees"] + c["friction"]))
    gross_gap = rounded(t["gross_before_modeled_costs"] - c["gross_before_modeled_costs"])
    if abs(gross_gap - cost_gap - gap) > 2e-6:
        raise AssertionError("Gross/cost/net bridge does not reconcile")
    classification = entry_classification(trades["C03"], trades["T05"])
    if abs(classification["total_gap_reconciled"] - gap) > 2e-6:
        raise AssertionError("Entry partition does not reconcile")
    result = {
        "scope": "Frozen final V4, risk05_base_whole, $5,000, 2024-01-02 to 2026-10-19",
        "source": "V4 final trade/equity ledgers and final_metrics.json; no model refit or new market data",
        "strategies": summaries,
        "t05_minus_c03": {"net_pnl_gap": gap, "gross_before_cost_gap": gross_gap,
                          "extra_t05_modeled_costs": cost_gap,
                          "entry_classification": classification},
        "spy_minus_c03_net_pnl": rounded(spy["net_pnl"] - c["net_pnl"]),
        "limitations": ["Gross is reconstructed by adding recorded fees and fill friction to net P/L; it is not a zero-cost rerun.",
                        "Shared-entry partition is descriptive. Different sizing, exits and prior equity paths confound causal attribution.",
                        "Historical periods have been repeatedly inspected; this diagnostic cannot validate a new selected strategy."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "output": str(args.output), "net_gap": gap,
                      "gross_gap": gross_gap, "cost_gap": cost_gap,
                      "shared_entries": classification["shared_entry_count"]}))


if __name__ == "__main__":
    main()
