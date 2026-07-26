"""Smoke tests for ETL analytics and ML wiring (isolated temp warehouse)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def small_warehouse(tmp_path_factory):
    """Build a tiny warehouse in a temp directory without touching project DB."""
    out = tmp_path_factory.mktemp("processed")
    db_dir = tmp_path_factory.mktemp("db")
    models = tmp_path_factory.mktemp("models")
    db_path = db_dir / "test_ipl.db"

    from config import settings

    settings.PROCESSED_DIR = out
    settings.DB_DIR = db_dir
    settings.DB_PATH = db_path
    settings.DB_URL = f"sqlite:///{db_path}"
    settings.MODELS_DIR = models

    from src.etl.generate_synthetic import generate_synthetic_ipl
    from src.etl.load import load_tables_from_dir
    from src.utils import db as db_mod

    generate_synthetic_ipl(
        seasons=[2022, 2023],
        matches_per_season=8,
        seed=1,
        output_dir=out,
        min_balls=None,
    )
    counts = load_tables_from_dir(out)
    return {"counts": counts, "db": db_mod, "settings": settings}


def test_synthetic_generates_deliveries(small_warehouse):
    counts = small_warehouse["counts"]
    assert counts["deliveries"] > 1000
    assert counts["matches"] >= 16
    assert small_warehouse["db"].table_exists("deliveries")


def test_analytics_queries(small_warehouse):
    from src.analytics.player_analytics import batting_leaderboard
    from src.analytics.team_analytics import team_season_table

    bat = batting_leaderboard(season=2023, min_balls=10, limit=5)
    assert isinstance(bat, pd.DataFrame)
    standings = team_season_table(2023)
    assert not standings.empty
    assert {"wins", "win_pct"}.issubset(standings.columns)


def test_ml_trains(small_warehouse, tmp_path):
    from src.ml.match_outcome import train_match_outcome_model
    from src.ml.score_prediction import train_score_model

    metrics = train_match_outcome_model(model_dir=tmp_path)
    assert "accuracy" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0
    score = train_score_model(model_dir=tmp_path)
    assert "selected" in score
