"""Tests for cap hall-of-fame and player-aware win adjustment."""

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
    db_path = db_dir / "caps.db"

    from config import settings

    settings.PROCESSED_DIR = out
    settings.DB_DIR = db_dir
    settings.DB_PATH = db_path
    settings.DB_URL = f"sqlite:///{db_path}"

    from src.etl.generate_synthetic import generate_synthetic_ipl
    from src.etl.load import load_tables_from_dir

    generate_synthetic_ipl(
        seasons=[2022, 2023, 2024],
        matches_per_season=8,
        seed=3,
        output_dir=out,
        min_balls=None,
    )
    load_tables_from_dir(out)
    return True


def test_all_season_cap_winners(tiny_db):
    from src.analytics.caps_race import all_season_cap_winners
    from src.analytics.player_photos import avatar_data_uri, render_cap_gallery

    orange, purple = all_season_cap_winners()
    assert len(orange) >= 3
    assert len(purple) >= 3
    assert set(orange.columns) >= {"season", "player_name", "runs"}
    uri = avatar_data_uri(orange.iloc[0]["player_name"], "orange")
    assert uri.startswith("data:image/svg+xml;base64,")
    html = render_cap_gallery(
        [{
            "season": int(orange.iloc[0]["season"]),
            "player_name": orange.iloc[0]["player_name"],
            "metric_label": "Runs",
            "metric_value": int(orange.iloc[0]["runs"]),
        }],
        accent="orange",
    )
    assert "Orange Cap" in html


def test_player_impact_adjustment(tiny_db):
    from src.analytics.team_players import (
        adjust_win_probability,
        player_impact_score,
        team_batters_last_season,
        team_bowlers_last_season,
    )
    from src.utils.db import read_sql

    team = read_sql(
        """
        SELECT t.team_name
        FROM teams t
        JOIN matches m ON t.team_id IN (m.team1_id, m.team2_id)
        WHERE m.season = 2023
        LIMIT 1
        """
    ).iloc[0]["team_name"]
    bat = team_batters_last_season(team, 2024)
    bowl = team_bowlers_last_season(team, 2024)
    assert not bat.empty or not bowl.empty
    names = (bat["player_name"].head(2).tolist() if not bat.empty else []) + (
        bowl["player_name"].head(1).tolist() if not bowl.empty else []
    )
    impact = player_impact_score(bat, bowl, names)
    out = adjust_win_probability(0.55, impact, 0.0)
    assert 0.05 <= out["team1_win_probability"] <= 0.95
