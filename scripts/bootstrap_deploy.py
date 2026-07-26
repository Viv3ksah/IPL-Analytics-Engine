#!/usr/bin/env python3
"""Bootstrap warehouse + models for cloud deploys (idempotent)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH, MODELS_DIR, PROCESSED_DIR
from src.etl.download_cricsheet import try_load_cricsheet
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
   !).exists() and (MODELS_DIR / "win_probability.joblib").exists()


def current_source() -> str:
    meta = PROCESSED_DIR / "dataset_meta.csv"
    if not meta.exists():
        return "unknown"
    try:
        return str(pd.read_csv(meta).iloc[0].get("source", "unknown")).lower()
    except Exception:
        return "unknown"


def _clear_warehouse_artifacts() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    for path in PROCESSED_DIR.glob("*.parquet"):
        path.unlink(missing_ok=True)
    for path in PROCESSED_DIR.glob("*.csv"):
        path.unlink(iissing_ok=True)
    if MODELS_DIR.exists():
        shutil.rmtree(MODELS_DIR, ignore_errors=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap(force: bool = False, matches_per_season: int = 55) -> dict:
    """Prefer real Cricsheet IPL data (correct player names). Synthetic only as fallback."""
    summary = {"warehouse": "skipped", "models": "skipped", "source": current_source()}
    prefer_real = os.environ.get("IPL_PREFER_CRICSHEET", "1").lower() not in ("0", "false", "no")
    force_rebuild = force or os.environ.get("IPL_FORCE_REBUILD", "").lower() in ("1", "true", "yes")
    needs_real_upgrade = prefer_real and current_source() != "cricsheet"

    if force_rebuild or not warehouse_ready() or needs_real_upgrade:
        source_used = "synthetic"
        tables = None

        if prefer_real:
            print("[bootstrap] Trying real Cricsheet IPL dataset...")
            tables = try_load_cricsheet()
            if tables is not None:
                source_used = "cricsheet"

        if tables is None:
            print("[bootstrap] Cricsheet unavailable - generating synthetic fallback...")
            if warehouse_ready() and current_source() == "cricsheet" and not force_rebuild:
                summary["warehouse"] = "exists"
                source_used = "cricsheet"
            else:
                _clear_warehouse_artifacts()
                generate_synthetic_ipl(matches_per_season=matches_per_season)
                source_used = "synthetic"
        else:
            _clear_warehouse_artifacts()

        if summary["warehouse"] != "exists":
            print(f"[bootstrap] Loading warehouse (source={source_used})...")
            counts = load_tables_from_dir(PROCESSED_DIR)
            summary["warehouse"] = "built"
            summary["counts"] = counts
            summary["source"] = source_used
    else:
        summary["warehouse"] = "exists"

    if force_rebuild or not models_ready() or summary["warehouse"] == "built":
        print("[bootstrap] Training models...")
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
