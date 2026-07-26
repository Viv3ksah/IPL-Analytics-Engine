"""Orange Cap / Purple Cap race and phase specialist rankings."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def orange_cap_race(season: int, top_n: int = 10) -> pd.DataFrame:
    """Cumulative run race by match date for top batters in a season."""
    q = """
    WITH per_match AS (
        SELECT
            p.player_name,
            m.match_date,
            m.match_id,
            SUM(d.runs_batter) AS runs
        FROM deliveries d
        JOIN players p ON p.player_id = d.striker_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
        GROUP BY p.player_name, m.match_date, m.match_id
    ),
    ranked AS (
        SELECT
            player_name,
            match_date,
            match_id,
            runs,
            SUM(runs) OVER (
                PARTITION BY player_name ORDER BY match_date, match_id
            ) AS cum_runs
        FROM per_match
    ),
    leaders AS (
        SELECT player_name
        FROM ranked
        GROUP BY player_name
        ORDER BY MAX(cum_runs) DESC
        LIMIT :top_n
    )
    SELECT r.player_name, r.match_date, r.match_id, r.runs, r.cum_runs
    FROM ranked r
    JOIN leaders l ON l.player_name = r.player_name
    ORDER BY r.match_date, r.match_id, r.player_name
    """
    return read_sql(q, {"season": season, "top_n": top_n})


def purple_cap_race(season: int, top_n: int = 10) -> pd.DataFrame:
    """Cumulative wicket race by match date for top bowlers in a season."""
    q = """
    WITH per_match AS (
        SELECT
            p.player_name,
            m.match_date,
            m.match_id,
            SUM(d.is_wicket) AS wickets
        FROM deliveries d
        JOIN players p ON p.player_id = d.bowler_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
          AND d.is_wicket = 1
          AND (
            d.dismissal_kind IS NULL
            OR d.dismissal_kind NOT IN ('run out', 'retired hurt', 'obstructing the field')
          )
        GROUP BY p.player_name, m.match_date, m.match_id
    ),
    ranked AS (
        SELECT
            player_name,
            match_date,
            match_id,
            wickets,
            SUM(wickets) OVER (
                PARTITION BY player_name ORDER BY match_date, match_id
            ) AS cum_wickets
        FROM per_match
    ),
    leaders AS (
        SELECT player_name
        FROM ranked
        GROUP BY player_name
        ORDER BY MAX(cum_wickets) DESC
        LIMIT :top_n
    )
    SELECT r.player_name, r.match_date, r.match_id, r.wickets, r.cum_wickets
    FROM ranked r
    JOIN leaders l ON l.player_name = r.player_name
    ORDER BY r.match_date, r.match_id, r.player_name
    """
    return read_sql(q, {"season": season, "top_n": top_n})


def phase_specialists(season: int | None = None, min_balls: int = 36) -> dict[str, pd.DataFrame]:
    """Best batters/bowlers by phase (powerplay / middle / death)."""
    params: dict = {"min_balls": min_balls}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season

    bat_q = f"""
    SELECT
        p.player_name,
        d.phase,
        COUNT(*) AS balls,
        SUM(d.runs_batter) AS runs,
        ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
        SUM(d.is_six) AS sixes
    FROM deliveries d
    JOIN players p ON p.player_id = d.striker_id
    JOIN matches m ON m.match_id = d.match_id
    WHERE 1=1 {season_filter}
    GROUP BY p.player_name, d.phase
    HAVING COUNT(*) >= :min_balls
    ORDER BY d.phase, strike_rate DESC
    """
    bowl_q = f"""
    SELECT
        p.player_name,
        d.phase,
        COUNT(*) AS balls,
        SUM(d.is_wicket) AS wickets,
        ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy
    FROM deliveries d
    JOIN players p ON p.player_id = d.bowler_id
    JOIN matches m ON m.match_id = d.match_id
    WHERE (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
      {season_filter}
    GROUP BY p.player_name, d.phase
    HAVING COUNT(*) >= :min_balls
    ORDER BY d.phase, economy ASC
    """
    return {"batting": read_sql(bat_q, params), "bowling": read_sql(bowl_q, params)}


def cap_standings(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Final Orange / Purple Cap tables for a season."""
    orange = read_sql(
        """
        SELECT
            p.player_name,
            SUM(d.runs_batter) AS runs,
            COUNT(*) AS balls,
            ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
            SUM(d.is_boundary) AS fours,
            SUM(d.is_six) AS sixes
        FROM deliveries d
        JOIN players p ON p.player_id = d.striker_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
        GROUP BY p.player_name
        ORDER BY runs DESC
        LIMIT 15
        """,
        {"season": season},
    )
    purple = read_sql(
        """
        SELECT
            p.player_name,
            SUM(d.is_wicket) AS wickets,
            COUNT(*) AS balls,
            ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy,
            ROUND(1.0 * SUM(d.runs_total) / NULLIF(SUM(d.is_wicket), 0), 2) AS average
        FROM deliveries d
        JOIN players p ON p.player_id = d.bowler_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
          AND (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
        GROUP BY p.player_name
        HAVING SUM(d.is_wicket) > 0
        ORDER BY wickets DESC, economy ASC
        LIMIT 15
        """,
        {"season": season},
    )
    return orange, purple


def all_season_cap_winners() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Orange & Purple Cap winners for every season (rank-1 only)."""
    orange = read_sql(
        """
        WITH bat AS (
            SELECT
                m.season,
                p.player_name,
                SUM(d.runs_batter) AS runs,
                COUNT(*) AS balls,
                ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
                SUM(d.is_six) AS sixes,
                ROW_NUMBER() OVER (
                    PARTITION BY m.season
                    ORDER BY SUM(d.runs_batter) DESC, COUNT(*) ASC
                ) AS rk
            FROM deliveries d
            JOIN players p ON p.player_id = d.striker_id
            JOIN matches m ON m.match_id = d.match_id
            GROUP BY m.season, p.player_name
        )
        SELECT season, player_name, runs, balls, strike_rate, sixes
        FROM bat
        WHERE rk = 1
        ORDER BY season
        """
    )
    purple = read_sql(
        """
        WITH bowl AS (
            SELECT
                m.season,
                p.player_name,
                SUM(d.is_wicket) AS wickets,
                COUNT(*) AS balls,
                ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy,
                ROW_NUMBER() OVER (
                    PARTITION BY m.season
                    ORDER BY SUM(d.is_wicket) DESC, SUM(d.runs_total) ASC
                ) AS rk
            FROM deliveries d
            JOIN players p ON p.player_id = d.bowler_id
            JOIN matches m ON m.match_id = d.match_id
            WHERE (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
            GROUP BY m.season, p.player_name
            HAVING SUM(d.is_wicket) > 0
        )
        SELECT season, player_name, wickets, balls, economy
        FROM bowl
        WHERE rk = 1
        ORDER BY season
        """
    )
    return orange, purple
