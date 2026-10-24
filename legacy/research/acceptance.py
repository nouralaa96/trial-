"""Evidence gates are deliberately distinct from software unit-test results."""
from __future__ import annotations


def evaluate_gates(scenarios, *, software_passed, historical_complete,
                   years, robustness_reviewed=False, initial_equity=1000.):
    """Evaluate each share mode separately, requiring both cost scenarios.

    A missing sample is inconclusive. Explicit software violations fail.
    Passing numerical metrics alone cannot certify concentration/stability.
    """
    if not software_passed:
        return {"status": "FAIL", "reason": "Software correctness not established"}
    if not historical_complete:
        return {"status": "INCONCLUSIVE", "reason": "Complete validated historical data unavailable"}
    if any(s.get("controllable_violations", 0) > 0 for s in scenarios.values()):
        return {"status": "FAIL", "reason": "Observed controllable rule violations"}
    def above(value, threshold, inclusive=False):
        return value is not None and (value >= threshold if inclusive else value > threshold)
    result = {}
    for mode in ("whole", "fractional"):
        checks = {}
        enough = years >= 2
        for cost in ("base", "stress"):
            entry = scenarios.get(f"{cost}_{mode}", {})
            metrics, comparison = entry.get("ridge", {}), entry.get("comparison", {})
            enough &= metrics.get("completed_trades", 0) >= 100
            pnl = metrics.get("net_pnl")
            dd = metrics.get("max_drawdown")
            checks[cost] = {
                "positive_net": pnl is not None and pnl > 0,
                "beats_cash_and_trend": above(comparison.get("incremental_pnl"), 0) and pnl is not None and pnl > 0,
                "annual_increment_at_least_2pct": above(comparison.get("annualized_incremental_pnl"), .02*initial_equity, True),
                "bootstrap_lower_positive": above(comparison.get("bootstrap_lower"), 0),
                "no_weekly_breaches": metrics.get("weekly_breach_count") == 0,
                "drawdown_at_most_10pct": dd is not None and dd <= .10,
                "no_rule_violations": entry.get("controllable_violations") == 0,
            }
        if not enough:
            state = "INCONCLUSIVE"
        elif not all(all(c.values()) for c in checks.values()):
            state = "FAIL"
        elif not robustness_reviewed:
            state = "INCONCLUSIVE"
        else:
            state = "HISTORICAL GATES PASSED — PROSPECTIVE TESTING REQUIRED"
        result[mode] = {"status": state, "sufficient_sample": bool(enough), "checks": checks}
    states = [v["status"] for v in result.values()]
    status = ("HISTORICAL GATES PASSED — PROSPECTIVE TESTING REQUIRED"
              if all(s.startswith("HISTORICAL") for s in states)
              else "FAIL" if "FAIL" in states else "INCONCLUSIVE")
    return {"status": status, "by_share_mode": result,
            "robustness_reviewed": robustness_reviewed,
            "prospective_testing_completed": False}
