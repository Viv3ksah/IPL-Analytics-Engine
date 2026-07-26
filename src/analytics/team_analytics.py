"""Team season performance, head-to-head, and chase/defend analytics."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def team_season_table(season: int | None = None) -> pd.DataFrame:
    params: dict = {}
    season_filter = ""
    if season is not None:
        season_filter = "WHERE season = :season"
        params["season"] = season
    q = f"""
    SELECT team_name, season, matches_played, wins, losses, win_pct
    FROM v_team_season
    {season_filter}
    ORDER BY season DESC, win_pct DESC, wins DESC
    """
    return read_sql(q, params)


def team_head_to_head(team_a: str, team_b: str) -> pd.DataFrame:
    q = """
    SELECT
        m.season,
        m.match_date,
        t1.team_name AS team1,
        t2.team_name AS team2,
        w.team_name AS winner,
        m.win_by_runs,
        m.win_by_wickets,
        v.venue_name
    FROM matches m
    JOIN teams t1 ON t1.team_id = m.team1_id
    JOIN teams t2 ON t2.team_id = m.team2_id
    LEFT JOIN teams w ON w.team_id = m.winner_id
    JOIN venues v ON v.venue_id = m.venue_id
    WHERE (t1.team_name = :a AND t2.team_name = :b)
       OR (t1.team_name = :b AND t2.team_name = :a)
    ORDER BY m.match_date DESC
    """
    return read_sql(q, {"a": team_a, "b": team_b})


def team_h2h_summary(team_a: str, team_b: str) -> dict:
    df = team_head_to_head(team_a, team_b)
    if df.empty:
        return {"matches": 0, team_a: 0, team_b: 0, "ties": 0}
    wins_a = int((df["winner"] == team_a).sum())
    wins_b = int((df["winner"] == team_b).sum())
    ties = int(df["winner"].isna().sum()) + int((~df["winner"].isin([team_a, team_b])).sum())
    return {"matches": len(df), team_a: wins_a, team_b: wins_b, "ties": ties, "recent": df.head(10)}


def chase_defend_profile(season: int | None = None) -> pd.DataFrame:
    params: dict = {}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season
    q = f"""
    WITH base AS (
        SELECT
            t.team_name,
            m.match_id,
            m.winner_id,
            t.team_id,
            i1.batting_team_id AS first_bat,
            CASE WHEN t.team_id = i1.batting_team_id THEN 'bat_first' ELSE 'chase' END AS role,
            CASE WHEN m.winner_id = t.team_id THEN 1 ELSE 0 END AS won
        FROM teams t
        JOIN matches m ON t.team_id IN (m.team1_id, m.team2_id)
        JOIN innings i1 ON i1.match_id = m.match_id AND i1.innings_number = 1
        WHERE m.winner_id IS NOT NULL {season_filter}
    )
    SELECT
        team_name,
        role,
        COUNT(*) AS matches,
        SUM(won) AS wins,
        ROUND(100.0 * AVG(won), 1) AS win_pct
    FROM base
    GROUP BY team_name, role
    ORDER BY team_name, role
    """
    return read_sql(q, params)


def season_run_rate_trends() -> pd.DataFrame:
    q = """
    SELECT
        m.season,
        d.phase,
        ROUND(AVG(d.runs_total) * 6, 2) AS run_rate,
        ROUND(100.0 * AVG(d.is_wicket), 2) AS wicket_pct,
        ROUND(100.0 * AVG(d.is_boundary + d.is_six), 2) AS boundary_pct
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    GROUP BY m.season, d.phase
    ORDER BY m.season, CASE d.phase
        WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END
    """
    return read_sql(q)


def list_teams() -> pd.DataFrame:
    return read_sql("SELECT team_id, team_name, short_name, city FROM teams ORDER BY team_name")


def match_summary(season: int | None = None, limit: int = 200) -> pd.DataFrame:
    params: dict = {"limit": limit}
    season_filter = ""
    if season is not None:
        season_filter = "WHERE season = :season"
        params["season"] = season
    return read_sql(
        f"SELECT * FROM v_match_summary {season_filter} ORDER BY match_date DESC LIMIT :limit",
        params,
    )
