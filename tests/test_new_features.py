"""Tests for caps race, dream team, and match simulator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def tiny_db(tmp_path_factory):
    out = tmp_path_factory.mktemp("processed")
    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "feat.db"

    from config import settings

    settings.PROCESSED_DIR = out
    settings.DB_DIR = db_dir
    settings.DB_PATH = db_path
    settings.DB_URL = f"sqlite:///{db_path}"

    from src.etl.generate_synthetic import generate_synthetic_ipl
    from src.etl.load import load_tables_from_dir

    generate_synthetic_ipl(
        seasons=[2023, 2024],
        matches_per_season=10,
        seed=2,
        output_dir=out,
        min_balls=None,
    )
    load_tables_from_dir(out)
    return 2024


def test_caps_and_specialists(tiny_db):
    from src.analytics.caps_race import cap_standings, orange_cap_race, phase_specialists

    race = orange_cap_race(tiny_db, top_n=5)
    assert not race.empty
    assert "cum_runs" in race.columns
    orange, purple = cap_standings(tiny_db)
    assert len(orange) > 0 and len(purple) > 0
    specs = phase_specialists(tiny_db, min_balls=12)
    assert not specs["batting"].empty


def test_dream_team_xi(tiny_db):
    from src.analytics.dream_team import build_dream_team

    xi = build_dream_team(tiny_db, max_credits=100)
    assert len(xi) == 11
    assert float(xi["credit"].sum()) <= 101.0


def test_match_simulator(tiny_db):
    from src.ml.match_simulator import ChaseState, simulate_chase

    result = simulate_chase(
        ChaseState(target=170, runs=80, wickets=2, overs_done=10.0),
        n_sims=300,
        season=tiny_db,
    )
    assert 0.0 <= result["win_probability"] <= 1.0
    assert result["balls_left"] > 0
