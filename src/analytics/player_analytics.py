"""Player batting, bowling, form, and fantasy analytics."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def batting_leaderboard(
    season: int | None = None,
    min_balls: int = 60,
    limit: int = 25,
) -> pd.DataFrame:
    where = ["1=1"]
    params: dict = {"min_balls": min_balls, "limit": limit}
    if season is not None:
        where.append("m.season = :season")
        params["season"] = season
    q = f"""
    SELECT
        p.player_name,
        m.season,
        COUNT(DISTINCT d.match_id) AS innings,
        SUM(d.runs_batter) AS runs,
        COUNT(*) AS balls,
        SUM(d.is_boundary) AS fours,
        SUM(d.is_six) AS sixes,
        SUM(d.is_wicket) AS outs,
        ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
        ROUND(1.0 * SUM(d.runs_batter) / NULLIF(SUM(d.is_wicket), 0), 2) AS average,
        ROUND(
            SUM(d.runs_batter) * 1.0
            + SUM(d.is_boundary) * 1.0
            + SUM(d.is_six) * 2.0
            + CASE WHEN SUM(d.runs_batter) >= 50 THEN 8 ELSE 0 END
            + CASE WHEN SUM(d.runs_batter) >= 100 THEN 16 ELSE 0 END,
            1
        ) AS fantasy_bat_pts
    FROM deliveries d
    JOIN players p ON p.player_id = d.striker_id
    JOIN matches m ON m.match_id = d.match_id
    WHERE {' AND '.join(where)}
    GROUP BY p.player_name, m.season
    HAVING COUNT(*) >= :min_balls
    ORDER BY runs DESC
    LIMIT :limit
    """
    return read_sql(q, params)


def bowling_leaderboard(
    season: int | None = None,
    min_balls: int = 60,
    limit: int = 25,
) -> pd.DataFrame:
    where = ["(d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))"]
    params: dict = {"min_balls": min_balls, "limit": limit}
    if season is not None:
        where.append("m.season = :season")
        params["season"] = season
    q = f"""
    SELECT
        p.player_name,
        m.season,
        COUNT(DISTINCT d.match_id) AS innings,
        COUNT(*) AS balls,
        ROUND(COUNT(*) / 6.0, 1) AS overs,
        SUM(d.runs_total) AS runs_conceded,
        SUM(d.is_wicket) AS wickets,
        ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy,
        ROUND(1.0 * SUM(d.runs_total) / NULLIF(SUM(d.is_wicket), 0), 2) AS average,
        ROUND(1.0 * COUNT(*) / NULLIF(SUM(d.is_wicket), 0), 2) AS strike_rate,
        ROUND(SUM(d.is_wicket) * 25.0 + SUM(CASE WHEN d.runs_total = 0 THEN 1 ELSE 0 END) * 1.0, 1) AS fantasy_bowl_pts
    FROM deliveries d
    JOIN players p ON p.player_id = d.bowler_id
    JOIN matches m ON m.match_id = d.match_id
    WHERE {' AND '.join(where)}
    GROUP BY p.player_name, m.season
    HAVING COUNT(*) >= :min_balls
    ORDER BY wickets DESC, economy ASC
    LIMIT :limit
    """
    return read_sql(q, params)


def player_phase_profile(player_name: str, season: int | None = None) -> pd.DataFrame:
    params: dict = {"player": player_name}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season
    q = f"""
    SELECT
        d.phase,
        COUNT(*) AS balls,
        SUM(d.runs_batter) AS runs,
        ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
        SUM(d.is_boundary) AS fours,
        SUM(d.is_six) AS sixes,
        SUM(d.is_wicket) AS dismissals
    FROM deliveries d
    JOIN players p ON p.player_id = d.striker_id
    JOIN matches m ON m.match_id = d.match_id
    WHERE p.player_name = :player {season_filter}
    GROUP BY d.phase
    ORDER BY CASE d.phase
        WHEN 'powerplay' THEN 1
        WHEN 'middle' THEN 2
        ELSE 3 END
    """
    return read_sql(q, params)


def player_form_index(player_name: str, last_n_matches: int = 8) -> pd.DataFrame:
    """Rolling form: runs, SR, and a 0-100 form index over recent matches."""
    q = """
    WITH match_bat AS (
        SELECT
            m.match_id,
            m.match_date,
            m.season,
            SUM(d.runs_batter) AS runs,
            COUNT(*) AS balls,
            SUM(d.is_wicket) AS out
        FROM deliveries d
        JOIN players p ON p.player_id = d.striker_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE p.player_name = :player
        GROUP BY m.match_id, m.match_date, m.season
    )
    SELECT * FROM match_bat
    ORDER BY match_date DESC
    LIMIT :n
    """
    df = read_sql(q, {"player": player_name, "n": last_n_matches})
    if df.empty:
        return df
    df = df.sort_values("match_date")
    df["strike_rate"] = (100 * df["runs"] / df["balls"].replace(0, pd.NA)).round(2)
    # form index: blend of runs and SR, scaled
    df["form_index"] = (
        (df["runs"].clip(0, 100) * 0.6)
        + (df["strike_rate"].fillna(0).clip(0, 200) * 0.2)
        + ((1 - df["out"].clip(0, 1)) * 10)
    ).round(1)
    df["rolling_form"] = df["form_index"].rolling(3, min_periods=1).mean().round(1)
    return df


def head_to_head_batter_vs_bowler(batter: str, bowler: str) -> pd.DataFrame:
    q = """
    SELECT
        COUNT(*) AS balls,
        SUM(d.runs_batter) AS runs,
        SUM(d.is_wicket) AS dismissals,
        SUM(d.is_boundary) AS fours,
        SUM(d.is_six) AS sixes,
        ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate
    FROM deliveries d
    JOIN players b ON b.player_id = d.striker_id
    JOIN players bw ON bw.player_id = d.bowler_id
    WHERE b.player_name = :batter AND bw.player_name = :bowler
    """
    return read_sql(q, {"batter": batter, "bowler": bowler})


def list_players(limit: int = 500) -> pd.DataFrame:
    return read_sql(
        "SELECT player_id, player_name, role FROM players ORDER BY player_name LIMIT :n",
        {"n": limit},
    )
