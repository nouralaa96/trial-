"""Run explicit synthetic integration or a strictly validated market experiment."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def ledger(event, **fields):
    with (ROOT / "experiment_ledger.jsonl").open("a") as f:
        f.write(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "event": event, **fields}, default=str) + "\n")


def save_frames(result, directory):
    directory.mkdir(parents=True, exist_ok=True)
    empty_columns = {
        "equity": ["date", "equity", "cash", "settled_cash", "open_positions", "pending_positions"],
        "trades": ["symbol", "entry_date", "exit_date", "qty", "entry_price", "exit_price",
                   "net_pnl", "fees", "friction", "holding_sessions", "reason"],
        "decisions": ["date", "symbol", "status", "reason"],
    }
    for key in ("equity", "trades", "decisions"):
        frame = result[key] if len(result[key].columns) else pd.DataFrame(columns=empty_columns[key])
        frame.to_csv(directory / f"{key}.csv", index=False)


def chart(results, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    for label, result in results.items():
        e = result["equity"]
        dates = pd.to_datetime(e["date"]) if "date" in e else e.index
        ax.plot(dates, e["equity"], label=label)
    ax.set(title=title, ylabel="Simulated equity (USD)", xlabel="Session")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def audit_result(result, config):
    """Independent checks on emitted accounting/admission records."""
    e, t, d = result["equity"], result["trades"], result["decisions"]
    findings = []
    if len(e):
        for check, message in [
            (np.allclose(e.equity, e.cash+e.exposure, atol=1e-7), "Equity ledger mismatch"),
            ((e.settled_cash >= -1e-7).all(), "Negative settled cash"),
            ((e.reserved_cash <= e.settled_cash+1e-7).all(), "Cash over-reserved"),
            ((e.open_positions+e.pending_positions <= config["max_positions"]).all(), "Position count exceeded"),
        ]:
            if not check:
                findings.append(message)
        if e.open_positions.iloc[-1] == 0:
            closed = t.net_pnl.sum() if len(t) else 0.
            if not np.isclose(e.equity.iloc[-1], config["initial_equity"]+closed, atol=1e-6):
                findings.append("Terminal equity does not reconcile to closed trade P/L")
    if len(d) and "status" in d:
        admissions = d[d.status == "admitted"]
        if len(admissions):
            groups = admissions.groupby("date")
            if (groups.size() > config["max_entries_per_session"]).any():
                findings.append("Session admission count exceeded")
            budgets = (groups.session_budget_at_admission.first() if "session_budget_at_admission" in admissions else config["session_risk_budget"])
            if (groups.planned_risk.sum() > budgets+1e-7).any():
                findings.append("Session admission risk exceeded")
            if "equity_at_admission" in admissions:
                if (admissions.planned_risk > config["per_trade_risk_fraction"]*admissions.equity_at_admission+1e-7).any():
                    findings.append("Per-trade equity risk exceeded")
            if "weekly_budget_at_admission" in admissions and (admissions.projected_weekly_required > admissions.weekly_budget_at_admission+1e-7).any():
                findings.append("Weekly admission risk exceeded")
        considered = d[d.status.isin(["admitted", "rejected"])]
        if len(considered) and (considered.groupby("date").size() > config["max_candidates_per_session"]).any():
            findings.append("Candidate consideration allowance exceeded")
    excess = e.get("projected_risk_excess", pd.Series(dtype=float))
    pending_exit = e.get("mandatory_exit_pending", pd.Series(dtype=bool))
    return {"violations": findings, "controllable_violations": len(findings),
            "observed_protective_risk_excess_sessions": int((excess > 1e-7).sum()),
            "maximum_observed_protective_risk_excess": float(excess.max()) if len(excess) else 0.,
            "close_exit_queued_sessions": int(pending_exit.sum()) if len(pending_exit) else 0}


def software_evidence():
    path = ROOT / "artifacts" / "test-results.xml"
    if not path.exists():
        return {"passed": False, "reason": "pytest XML missing"}
    tree = ET.parse(path)
    suites = list(tree.iter("testsuite"))
    tests = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0))+int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"passed": tests > 0 and failures == 0, "tests": tests,
            "failures": failures, "skipped": skipped}


if __name__ == "__main__":
    from .v2 import main
    sys.exit(main())
