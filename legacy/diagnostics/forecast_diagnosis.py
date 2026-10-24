"""Describe the frozen Ridge forecasts; never fit a model or alter research inputs.

Run with .venv/bin/python diagnostics/forecast_diagnosis.py from the v2 root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


PARTITION_ENDS = {
    "development": "2021-12-31",
    "validation": "2023-12-31",
    "final": "2026-10-19",
}


def summarize(frame: pd.DataFrame) -> dict:
    prediction = frame["prediction"].to_numpy(dtype=float)
    realized = frame["label"].to_numpy(dtype=float)
    ridge_mse = float(np.mean((prediction - realized) ** 2))
    zero_mse = float(np.mean(realized ** 2))
    pearson = float(frame["prediction"].corr(frame["label"]))
    spearman = float(frame["prediction"].rank().corr(frame["label"].rank()))
    return {
        "n": len(frame),
        "decision_date_min": frame["date"].min().date().isoformat(),
        "decision_date_max": frame["date"].max().date().isoformat(),
        "label_maturity_max": frame["label_matured"].max().date().isoformat(),
        "ridge_mse": ridge_mse,
        "zero_mse": zero_mse,
        "ridge_rmse_pct": 100 * math.sqrt(ridge_mse),
        "zero_rmse_pct": 100 * math.sqrt(zero_mse),
        "mse_improvement_vs_zero_pct": 100 * (1 - ridge_mse / zero_mse),
        "ridge_direction_accuracy": float(np.mean(np.sign(prediction) == np.sign(realized))),
        "always_positive_direction_accuracy": float(np.mean(realized > 0)),
        "zero_direction_accuracy": float(np.mean(realized == 0)),
        "prediction_mean": float(np.mean(prediction)),
        "realized_mean": float(np.mean(realized)),
        "prediction_std_population": float(np.std(prediction, ddof=0)),
        "realized_std_population": float(np.std(realized, ddof=0)),
        "pearson_descriptive": pearson if math.isfinite(pearson) else None,
        "spearman_descriptive": spearman if math.isfinite(spearman) else None,
    }


def verify_saved(computed: dict, saved: dict) -> dict:
    fields = {
        "n": "n", "mse": "ridge_mse", "zero_mse": "zero_mse",
        "direction_accuracy": "ridge_direction_accuracy",
        "zero_direction_accuracy": "zero_direction_accuracy",
    }
    checks = []
    groups = [("all", computed["all"], saved)]
    for group_type in ("by_partition", "by_asset"):
        groups.extend((f"{group_type}/{key}", value, saved[group_type][key])
                      for key, value in computed[group_type].items())
    for group, actual, expected in groups:
        for source_key, target_key in fields.items():
            delta = abs(actual[target_key] - expected[source_key])
            passed = (delta == 0) if source_key == "n" else bool(
                np.isclose(actual[target_key], expected[source_key], rtol=1e-11, atol=1e-14)
            )
            checks.append({"group": group, "field": source_key,
                           "absolute_difference": delta, "passed": passed})
    assert all(check["passed"] for check in checks), "Saved forecast metrics did not reconcile"
    return {"all_passed": True, "checks": checks,
            "tolerance": "N exact; other fields rtol=1e-11, atol=1e-14"}


def accuracy_table(groups: dict) -> str:
    rows = ["| Sample | N | Ridge MSE | Zero MSE | Ridge RMSE % | MSE improvement % | Ridge direction % | Positive direction % | Pearson | Spearman |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, m in groups.items():
        rows.append(f"| {name} | {m['n']} | {m['ridge_mse']:.9f} | {m['zero_mse']:.9f} | "
                    f"{m['ridge_rmse_pct']:.3f} | {m['mse_improvement_vs_zero_pct']:.3f} | "
                    f"{100*m['ridge_direction_accuracy']:.2f} | {100*m['always_positive_direction_accuracy']:.2f} | "
                    f"{m['pearson_descriptive']:.4f} | {m['spearman_descriptive']:.4f} |")
    return "\n".join(rows)


def write_note(result: dict, path: Path) -> None:
    groups = {"all": result["all"], **result["by_partition"]}
    moments = ["| Sample | Mean prediction % | Mean realized % | Prediction std % | Realized std % |",
               "|---|---:|---:|---:|---:|"]
    for name, m in groups.items():
        moments.append(f"| {name} | {100*m['prediction_mean']:.3f} | {100*m['realized_mean']:.3f} | "
                       f"{100*m['prediction_std_population']:.3f} | {100*m['realized_std_population']:.3f} |")
    text = "\n\n".join([
        "# Frozen forecast diagnosis",
        "Ridge shows weak predictive value before any trading fees are applied. Its MSE improvement over "
        "a zero-return forecast is 0.485% overall, -0.006% in development, -0.799% in validation, and "
        "2.071% in final. The final improvement is small in absolute terms: RMSE is 2.448% versus "
        "2.474% for zero. These forecast errors alone cannot attribute the strategy P&L gap to prediction, "
        "selection, exits, or costs; combine this evidence with the frozen-trade cost attribution.",
        "The following counts and original MSE/direction fields reproduce inputs/prediction_metrics.json "
        "within numerical tolerance (35 checks). Only finite forecasts and labels whose label_matured is "
        "within its own partition end are included: development through 2021-12-31, validation through "
        "2023-12-31, final through 2026-10-19. Of 5,790 saved forecast rows, 45 are excluded: 15 per "
        "partition. In development and validation these labels cross the partition boundary; final has "
        "15 unavailable labels/maturities. No missing labels are imputed.",
        accuracy_table(groups),
        "Positive direction means predicting an upward move on every row of the exact same sample; it "
        "is a descriptive class-frequency baseline and is not a proposed or simulated trading strategy. "
        "Ridge direction accuracy is below that baseline in each partition: development 54.45% versus "
        "61.73%, validation 49.93% versus 53.16%, final 59.29% versus 60.50%. The saved zero_direction_accuracy "
        "counts exactly flat labels, so it is not an economically useful direction benchmark. "
        "Direction uses exact three-way signs; flat realized returns count as misses for the positive baseline.",
        "\n".join(moments),
        "Means, standard deviations, and RMSE are expressed in percentage points of return; MSE uses "
        "squared decimal returns. Standard deviations use ddof=0. MSE improvement is "
        "100 × (1 − Ridge MSE / zero MSE), so negative means worse than zero. Correlations are "
        "descriptive Pearson and Spearman (average ranks for ties), with no IID significance test or "
        "confidence claim. Daily five-session labels overlap, pooled assets share dates and market exposure, "
        "and quarterly fits repeat across many rows. N is a row count, not an independent-sample count.",
        "## Asset totals",
        accuracy_table(result["by_asset"]),
        "## Each partition and asset",
        accuracy_table({f"{partition}/{asset}": metric
                        for partition, assets in result["by_partition_asset"].items()
                        for asset, metric in assets.items()}),
        "The label is the saved gross fixed-horizon total return: " + result["label_definition"] + ". "
        "It does not deduct trading fees. Actual filled trades can stop out, reach a target, time out, "
        "or remain open, and their fills and position sizes differ from this universe of forecasts. "
        "A forecast-label error is therefore not a trade-return error. The simple trend rule does not "
        "supply a like-for-like numerical return forecast here; its comparison belongs in the portfolio "
        "and trade attribution tables, rather than inventing a trend forecast target.",
        "The combined sample includes development, which was used to choose alpha, and must not be "
        "described as a wholly untouched test. Saved metadata records development decision alpha=1, "
        "later selected alpha=100 for both equity and gold, quarterly fits, a 10-session training embargo, "
        "and 10 excluded sessions at partition starts. This diagnostic reads those frozen outputs and "
        "does no fitting, parameter selection, or strategy change. Filtering label maturity is an "
        "evaluation boundary check; it does not independently prove absence of all future-data leakage. "
        "Final is a retrospective historical evaluation and has now been inspected.",
    ])
    path.write_text(text + "\n")


def run(root: Path, output: Path) -> dict:
    input_dir = root / "inputs"
    manifest = json.loads((input_dir / "manifest.json").read_text())
    hashes = {}
    for name in ("ridge_explanations.csv", "prediction_metrics.json", "model_metadata.json"):
        digest = hashlib.sha256((input_dir / name).read_bytes()).hexdigest()
        assert digest == manifest["sha256"][name], f"Frozen input hash mismatch: {name}"
        hashes[name] = digest
    frame = pd.read_csv(input_dir / "ridge_explanations.csv",
                        parse_dates=["date", "label_matured"])
    assert not frame.duplicated(["date", "symbol"]).any(), "Duplicate forecast keys"
    assert set(frame["partition"].unique()) == set(PARTITION_ENDS)
    saved = json.loads((input_dir / "prediction_metrics.json").read_text())
    metadata = json.loads((input_dir / "model_metadata.json").read_text())
    frames, exclusions = {}, {}
    for partition, end in PARTITION_ENDS.items():
        part = frame[frame["partition"] == partition]
        finite = np.isfinite(part["prediction"]) & np.isfinite(part["label"])
        matured = part["label_matured"].notna() & (part["label_matured"] <= pd.Timestamp(end))
        eligible = finite & matured
        frames[partition] = part[eligible]
        assert (frames[partition]["date"] <= frames[partition]["label_matured"]).all()
        exclusions[partition] = {
            "input_rows": len(part), "included_rows": int(eligible.sum()),
            "excluded_rows": int((~eligible).sum()),
            "missing_or_nonfinite_forecast_or_label": int((~finite).sum()),
            "missing_label_maturity": int(part["label_matured"].isna().sum()),
            "maturity_after_partition_end": int((part["label_matured"] > pd.Timestamp(end)).sum()),
        }
    eligible = pd.concat(frames.values(), ignore_index=True)
    result = {
        "description": "Frozen Ridge forecast diagnosis before trading costs; no fitting or retuning",
        "input_sha256": hashes, "partition_maturity_limits": PARTITION_ENDS,
        "label_definition": metadata["label_definition"],
        "exclusions": exclusions,
        "all": summarize(eligible),
        "by_partition": {p: summarize(f) for p, f in frames.items()},
        "by_asset": {symbol: summarize(f) for symbol, f in eligible.groupby("symbol")},
        "by_partition_asset": {p: {symbol: summarize(f) for symbol, f in part.groupby("symbol")}
                               for p, part in frames.items()},
        "interpretation_limits": [
            "Overlapping labels and common asset dates: row N is not independent N",
            "Correlations descriptive only; no IID significance estimates",
            "Gross fixed-horizon labels differ from actual trade fills and exits",
            "Development participated in alpha selection; final is retrospective and inspected",
            "Maturity filtering does not establish complete freedom from future-data leakage",
            "Always-positive direction is a same-sample descriptive baseline, not a new strategy",
        ],
    }
    result["saved_metric_reconciliation"] = verify_saved(result, saved)
    output.mkdir(parents=True, exist_ok=True)
    (output / "forecast_metrics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    write_note(result, output / "forecast_note.md")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or args.root / "analysis" / "cost_attribution"
    result = run(args.root, destination)
    print(json.dumps({"saved_metrics_reconciled": result["saved_metric_reconciliation"]["all_passed"],
                      "all": result["all"], "output": str(destination)}, indent=2))
