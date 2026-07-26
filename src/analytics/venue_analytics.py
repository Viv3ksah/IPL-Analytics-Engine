"""Venue scoring patterns, toss impact, and pitch indices."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def venue_overview(season: int | None = None) -> pd.DataFrame:
    params: dict = {}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season
    q = f"""
    WITH phase_rr AS (
        SELECT
            m.venue_id,
            ROUND(AVG(CASE WHEN d.phase = 'powerplay' THEN d.runs_total END) * 6, 2) AS pp_run_rate,
            ROUND(AVG(CASE WHEN d.phase = 'death' THEN d.runs_total END) * 6, 2) AS death_run_rate
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        WHERE 1=1 {season_filter}
        GROUP BY m.venue_id
    )
    SELECT
        v.venue_name,
        v.city,
        COUNT(DISTINCT m.match_id) AS matches,
        ROUND(AVG(i1.total_runs), 1) AS avg_first_innings,
        ROUND(AVG(i2.total_runs), 1) AS avg_second_innings,
        ROUND(AVG(i1.total_runs + COALESCE(i2.total_runs, 0)), 1) AS avg_match_total,
        ROUND(100.0 * AVG(CASE WHEN m.win_by_runs > 0 THEN 1.0 ELSE 0.0 END), 1) AS bat_first_win_pct,
        ROUND(100.0 * AVG(CASE WHEN m.win_by_wickets > 0 THEN 1.0 ELSE 0.0 END), 1) AS chase_win_pct,
        pr.pp_run_rate,
        pr.death_run_rate
    FROM venues v
    JOIN matches m ON m.venue_id = v.venue_id
    LEFT JOIN innings i1 ON i1.match_id = m.match_id AND i1.innings_number = 1
    LEFT JOIN innings i2 ON i2.match_id = m.match_id AND i2.innings_number = 2
    LEFT JOIN phase_rr pr ON pr.venue_id = v.venue_id
    WHERE 1=1 {season_filter}
    GROUP BY v.venue_name, v.city, pr.pp_run_rate, pr.death_run_rate
    HAVING COUNT(DISTINCT m.match_id) >= 3
    ORDER BY avg_first_innings DESC
    """
    return read_sql(q, params)


def venue_difficulty_index(season: int | None = None) -> pd.DataFrame:
    """Relative batting friendliness: 100 = league-average first-innings score."""
    df = venue_overview(season)
    if df.empty:
        return df
    league_avg = df["avg_first_innings"].mean()
    df["batting_index"] = (100 * df["avg_first_innings"] / league_avg).round(1)
    df["bowling_index"] = (200 - df["batting_index"]).round(1)
    df["chase_friendliness"] = df["chase_win_pct"]
    return df.sort_values("batting_index", ascending=False)


def toss_venue_impact(venue_name: str | None = None) -> pd.DataFrame:
    params: dict = {}
    venue_filter = ""
    if venue_name:
        venue_filter = "AND v.venue_name = :venue"
        params["venue"] = venue_name
    q = f"""
    SELECT
        v.venue_name,
        m.toss_decision,
        COUNT(*) AS matches,
        ROUND(100.0 * AVG(CASE WHEN m.toss_winner_id = m.winner_id THEN 1.0 ELSE 0.0 END), 1) AS toss_win_convert_pct
    FROM matches m
    JOIN venues v ON v.venue_id = m.venue_id
    WHERE m.winner_id IS NOT NULL {venue_filter}
    GROUP BY v.venue_name, m.toss_decision
    ORDER BY v.venue_name, m.toss_decision
    """
    return read_sql(q, params)


def list_venues() -> pd.DataFrame:
    return read_sql("SELECT venue_id, venue_name, city FROM venues ORDER BY venue_name")
