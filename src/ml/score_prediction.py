"""First-innings final score regression models."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import MODELS_DIR, RANDOM_SEED
from src.ml.features import build_score_feature_frame

SCORE_FEATURES = [
    "over_number",
    "cum_runs",
    "cum_wickets",
    "balls_faced",
    "current_rr",
    "wickets_in_hand",
    "overs_left",
    "proj_naive",
    "venue_id",
    "season",
]


def train_score_model(
    test_size: float = 0.2,
    model_dir: Path | None = None,
) -> dict:
    model_dir = model_dir or MODELS_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    df = build_score_feature_frame()
    X = df[SCORE_FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)
    y = df["final_score"].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_SEED
    )

    # Prefer GradientBoosting; fall back path kept via RF comparison metrics
    gbr = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "reg",
                GradientBoostingRegressor(
                    random_state=RANDOM_SEED,
                    n_estimators=200,
                    max_depth=3,
                    learning_rate=0.08,
                ),
            ),
        ]
    )
    rf = RandomForestRegressor(
        n_estimators=180,
        max_depth=10,
        min_samples_leaf=15,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )

    gbr.fit(X_train, y_train)
    rf.fit(X_train, y_train)

    pred_gbr = gbr.predict(X_test)
    pred_rf = rf.predict(X_test)

    def _metrics(name: str, pred) -> dict:
        return {
            "model": name,
            "mae": float(mean_absolute_error(y_test, pred)),
            "rmse": float(mean_squared_error(y_test, pred) ** 0.5),
            "r2": float(r2_score(y_test, pred)),
        }

    metrics = {
        "gradient_boosting": _metrics("gradient_boosting", pred_gbr),
        "random_forest": _metrics("random_forest", pred_rf),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "selected": "gradient_boosting"
        if mean_absolute_error(y_test, pred_gbr) <= mean_absolute_error(y_test, pred_rf)
        else "random_forest",
    }

    selected = gbr if metrics["selected"] == "gradient_boosting" else rf
    joblib.dump(
        {"model": selected, "features": SCORE_FEATURES, "kind": metrics["selected"]},
        model_dir / "score_prediction.joblib",
    )
    (model_dir / "score_prediction_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def predict_final_score(state: dict, model_dir: Path | None = None) -> float:
    model_dir = model_dir or MODELS_DIR
    bundle = joblib.load(model_dir / "score_prediction.joblib")
    X = pd.DataFrame([{f: state.get(f, 0) for f in bundle["features"]}])
    return float(bundle["model"].predict(X)[0])
