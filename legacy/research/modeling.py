"""Chronological pooled Ridge with auditable, matured-label training cutoffs."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS

ALPHAS = (0.1, 1., 10., 100.)
GROUPS = {"equity": ("SPY", "QQQ"), "gold": ("GLD",)}
PARTITIONS = (("development", "2019-01-01", "2021-12-31"),
              ("validation", "2022-01-01", "2023-12-31"),
              ("final", "2024-01-01", "2026-10-19"))


def _pooled(features: dict[str, pd.DataFrame], symbols: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        if symbol in features:
            f = features[symbol].copy()
            f["symbol"], f["date"] = symbol, f.index
            rows.append(f)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["date", "symbol"]).reset_index(drop=True)


def _eligible(rows: pd.DataFrame) -> pd.Series:
    valid = np.isfinite(rows[FEATURE_COLUMNS]).all(axis=1) & np.isfinite(rows.label)
    # Purge globally: a boundary-crossing target never enters a later refit.
    for boundary in ("2019-01-01", "2022-01-01", "2024-01-01"):
        valid &= ~((rows.date < boundary) & (rows.label_matured >= boundary))
    return valid


def _fit(rows: pd.DataFrame, alpha: float) -> Pipeline:
    model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
    model.fit(rows[FEATURE_COLUMNS], rows.label)
    return model


def select_alpha(rows: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[float, dict]:
    """Initial 2010-18 training, development-only MSE; all cutoffs purged."""
    dev_sessions = calendar[(calendar >= "2019-01-01") & (calendar <= "2021-12-31")]
    if len(dev_sessions) <= 10:
        return 1., {"status": "insufficient_development", "scores": {}}
    start = dev_sessions[10]
    train = rows[_eligible(rows) & (rows.date >= "2010-01-01") &
                 (rows.label_matured < "2019-01-01")]
    dev = rows[_eligible(rows) & (rows.date >= start) &
               (rows.label_matured <= "2021-12-31")]
    if len(train) < 100 or len(dev) < 20:
        return 1., {"status": "insufficient_development", "scores": {},
                    "training_rows": len(train), "development_rows": len(dev)}
    scores = {str(a): float(np.mean((_fit(train, a).predict(dev[FEATURE_COLUMNS])-dev.label)**2))
              for a in ALPHAS}
    selected = min(ALPHAS, key=lambda a: (scores[str(a)], a))
    return selected, {"status": "selected", "criterion": "development_predictive_MSE",
                      "scores": scores, "selected": selected,
                      "training_rows": len(train), "development_rows": len(dev),
                      "training_max_maturity": str(train.label_matured.max()),
                      "development_max_maturity": str(dev.label_matured.max())}


def walk_forward_predictions(features: dict[str, pd.DataFrame],
                             calendar: pd.DatetimeIndex | None = None
                             ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Quarterly expanding refits with ten full sessions between cutoff and use.

    Development predictions use predeclared alpha=1 because the development
    winner is only known at its end. Validation and final use that frozen winner.
    First ten sessions of each evaluation partition have no predictions. All
    labels must mature by ten sessions before the quarterly first decision.
    """
    if calendar is None:
        calendar = pd.DatetimeIndex(sorted(set().union(*(f.index for f in features.values()))))
    calendar = pd.DatetimeIndex(calendar).sort_values().unique()
    wide = pd.DataFrame(np.nan, index=calendar, columns=list(features))
    explanations, fit_logs, selections = [], [], {}
    for group, symbols in GROUPS.items():
        rows = _pooled(features, symbols)
        if rows.empty:
            continue
        selected, selection = select_alpha(rows, calendar)
        selections[group] = selection
        for partition, begin, end in PARTITIONS:
            sessions = calendar[(calendar >= begin) & (calendar <= end)]
            if len(sessions) <= 10:
                continue
            allowed = sessions[10:]
            for quarter in allowed.to_period("Q").unique():
                decision_dates = allowed[allowed.to_period("Q") == quarter]
                first = decision_dates[0]
                location = calendar.get_loc(first)
                if location < 11:
                    continue
                cutoff = calendar[location-11]  # ten full intervening sessions
                train = rows[_eligible(rows) & (rows.date >= "2010-01-01") &
                             (rows.label_matured <= cutoff)]
                if len(train) < 100:
                    continue
                alpha = 1. if partition == "development" else selected
                model = _fit(train, alpha)
                valid = np.isfinite(rows[FEATURE_COLUMNS]).all(axis=1)
                test = rows[valid & rows.date.isin(decision_dates)]
                if test.empty:
                    continue
                prediction = model.predict(test[FEATURE_COLUMNS])
                standardized = model.named_steps["scale"].transform(test[FEATURE_COLUMNS])
                ridge = model.named_steps["ridge"]
                contributions = standardized * ridge.coef_
                for i, (_, row) in enumerate(test.iterrows()):
                    wide.loc[row.date, row.symbol] = prediction[i]
                    record = {"date": row.date, "symbol": row.symbol,
                              "prediction": float(prediction[i]), "intercept": float(ridge.intercept_),
                              "partition": partition, "quarter": str(quarter), "alpha": alpha,
                              "training_cutoff": cutoff, "training_rows": len(train),
                              "label": row.label, "label_matured": row.label_matured}
                    record.update({f"contribution_{name}": float(contributions[i,j])
                                   for j, name in enumerate(FEATURE_COLUMNS)})
                    explanations.append(record)
                fit_logs.append({"group": group, "partition": partition, "quarter": str(quarter),
                                 "first_decision": str(first), "training_cutoff": str(cutoff),
                                 "max_training_maturity": str(train.label_matured.max()),
                                 "training_rows": len(train), "alpha": alpha,
                                 "scaler_mean": model.named_steps["scale"].mean_.tolist(),
                                 "scaler_scale": model.named_steps["scale"].scale_.tolist(),
                                 "coefficients_standardized": ridge.coef_.tolist(),
                                 "intercept": float(ridge.intercept_)})
    return wide, pd.DataFrame(explanations), {
        "alpha_selection": selections, "fits": fit_logs,
        "feature_columns": FEATURE_COLUMNS,
        "label_definition": "(split-adjusted close[t+5] plus entitled cash dividends)/open[t+1]-1",
        "training_embargo_sessions": 10,
        "partition_start_excluded_sessions": 10,
        "development_decision_alpha": 1.,
        "note": "Final evaluation is retrospective; alpha frozen using development only."}


def prediction_metrics(explanations: pd.DataFrame) -> dict:
    result = {}
    if explanations.empty:
        return {"n": 0, "mse": None, "zero_mse": None, "direction_accuracy": None,
                "zero_direction_accuracy": None}
    rows = explanations.dropna(subset=["prediction", "label", "label_matured"])
    # Only outcomes that mature within their own evaluation partition count.
    ends = {name: pd.Timestamp(end) for name, _, end in PARTITIONS}
    rows = rows[rows.apply(lambda r: r.label_matured <= ends[r.partition], axis=1)]
    def scores(f):
        if f.empty:
            return {"n": 0, "mse": None, "zero_mse": None,
                    "direction_accuracy": None, "zero_direction_accuracy": None}
        return {"n": len(f), "mse": float(np.mean((f.prediction-f.label)**2)),
                "zero_mse": float(np.mean(f.label**2)),
                "direction_accuracy": float(np.mean(np.sign(f.prediction)==np.sign(f.label))),
                "zero_direction_accuracy": float(np.mean(np.sign(f.label)==0))}
    result.update(scores(rows))
    result["by_partition"] = {str(k): scores(g) for k,g in rows.groupby("partition")}
    result["by_asset"] = {str(k): scores(g) for k,g in rows.groupby("symbol")}
    return result
