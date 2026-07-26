"""Match outcome classifier + chase win-probability model."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import MODELS_DIR, RANDOM_SEED
from src.ml.features import build_live_chase_frame, build_match_feature_frame

MATCH_FEATURES = [
    "venue_id",
    "team1_id",
    "team2_id",
    "team1_won_toss",
    "chose_bat",
    "team1_win_rate",
    "team2_win_rate",
    "win_rate_diff",
    "venue_avg_score",
    "season",
]

CHASE_FEATURES = [
    "runs_needed",
    "balls_left",
    "wickets_left",
    "required_rr",
    "cum_runs",
    "over_number",
]


def train_match_outcome_model(
    test_size: float = 0.2,
    model_dir: Path | None = None,
) -> dict:
    model_dir = model_dir or MODELS_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    df = build_match_feature_frame()
    X = df[MATCH_FEATURES].fillna(0)
    y = df["team1_won"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_SEED, stratify=y
    )

    pipe = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "clf",
                GradientBoostingClassifier(
                    random_state=RANDOM_SEED,
                    n_estimators=180,
                    max_depth=3,
                    learning_rate=0.08,
                ),
            ),
        ]
    )
    pipe.fit(X_train, y_train)
    proba = pipe.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    metrics = {
        "model": "match_outcome",
        "accuracy": float(accuracy_score(y_test, pred)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "brier": float(brier_score_loss(y_test, proba)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "report": classification_report(y_test, pred, output_dict=True),
        "feature_importance": dict(
            zip(MATCH_FEATURES, pipe.named_steps["clf"].feature_importances_.round(4).tolist())
        ),
    }

    joblib.dump({"pipeline": pipe, "features": MATCH_FEATURES}, model_dir / "match_outcome.joblib")
    (model_dir / "match_outcome_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def train_win_probability_model(
    test_size: float = 0.2,
    model_dir: Path | None = None,
) -> dict:
    """Upgrade: live chase win probability from match state."""
    model_dir = model_dir or MODELS_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    df = build_live_chase_frame()
    X = df[CHASE_FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)
    y = df["chasing_team_won"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_SEED, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=20,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    proba = clf.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    metrics = {
        "model": "win_probability",
        "accuracy": float(accuracy_score(y_test, pred)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "brier": float(brier_score_loss(y_test, proba)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "feature_importance": dict(
            zip(CHASE_FEATURES, clf.feature_importances_.round(4).tolist())
        ),
    }
    joblib.dump({"model": clf, "features": CHASE_FEATURES}, model_dir / "win_probability.joblib")
    (model_dir / "win_probability_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def predict_match_outcome(feature_row: dict, model_dir: Path | None = None) -> dict:
    model_dir = model_dir or MODELS_DIR
    bundle = joblib.load(model_dir / "match_outcome.joblib")
    X = pd.DataFrame([{f: feature_row.get(f, 0) for f in bundle["features"]}])
    proba = float(bundle["pipeline"].predict_proba(X)[0, 1])
    return {"team1_win_probability": proba, "team2_win_probability": 1 - proba}


def predict_chase_win_prob(state: dict, model_dir: Path | None = None) -> float:
    model_dir = model_dir or MODELS_DIR
    bundle = joblib.load(model_dir / "win_probability.joblib")
    X = pd.DataFrame([{f: state.get(f, 0) for f in bundle["features"]}])
    return float(bundle["model"].predict_proba(X)[0, 1])
