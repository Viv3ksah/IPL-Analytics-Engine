#!/usr/bin/env python3
"""Bootstrap warehouse + models for cloud deploys (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH, MODELS_DIR, PROCESSED_DIR
from src.etl.generate_synthetic import generate_synthetic_ipl
from src.etl.load import load_tables_from_dir
from src.ml.match_outcome import train_match_outcome_model, train_win_probability_model
from src.ml.score_prediction import train_score_model
from src.utils.db import table_exists


def warehouse_ready() -> bool:
    return DB_PATH.exists() and table_exists("deliveries")


def models_ready() -> bool:
    return (MODELS_DIR / "match_outcome.joblib").exists() and (
        MODELS_DIR / "score_prediction.joblib"
    ).exists() and (MODELS_DIR / "win_probability.joblib").exists()


def bootstrap(force: bool = False, matches_per_season: int = 55) -> dict:
    """Create processed data, SQLite warehouse, and ML models if missing."""
    summary = {"warehouse": "skipped", "models": "skipped"}

    if force or not warehouse_ready():
        print("[bootstrap] Generating synthetic IPL dataset…")
        generate_synthetic_ipl(matches_per_season=matches_per_season)
        print("[bootstrap] Loading warehouse…")
        counts = load_tables_from_dir(PROCESSED_DIR)
        summary["warehouse"] = "built"
        summary["counts"] = counts
    else:
        summary["warehouse"] = "exists"

    if force or not models_ready():
        print("[bootstrap] Training models…")
        train_match_outcome_model()
        train_score_model()
        train_win_probability_model()
        summary["models"] = "trained"
    else:
        summary["models"] = "exists"

    print("[bootstrap] Ready:", summary)
    return summary


if __name__ == "__main__":
    force = "--force" in sys.argv
    bootstrap(force=force)
