"""Team squad / last-season player performance helpers."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def previous_season(season: int) -> int | None:
    seasons = read_sql("SELECT DISTINCT season FROM matches ORDER BY season")
    vals = seasons["season"].astype(int).tolist()
    prior = [s for s in vals if s < season]
    return max(prior) if prior else None


def team_id_for_name(team_name: str) -> int | None:
    df = read_sql("SELECT team_id FROM teams WHERE team_name = :n", {"n": team_name})
    if df.empty:
        return None
    return int(df.iloc[0]["team_id"])


def team_batters_last_season(team_name: str, season: int, limit: int = 20) -> pd.DataFrame:
    """Top batters for a team in the previous season."""
    prev = previous_season(season)
    if prev is None:
        return pd.DataFrame()
    tid = team_id_for_name(team_name)
    if tid is None:
        return pd.DataFrame()
    return read_sql(
        """
        SELECT
            p.player_id,
            p.player_name,
            :prev AS form_season,
            COUNT(DISTINCT d.match_id) AS innings,
            SUM(d.runs_batter) AS runs,
            COUNT(*) AS balls,
            ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
            ROUND(1.0 * SUM(d.runs_batter) / NULLIF(SUM(d.is_wicket), 0), 2) AS average,
            SUM(d.is_six) AS sixes
        FROM deliveries d
        JOIN players p ON p.player_id = d.striker_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :prev
          AND d.batting_team_id = :tid
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(*) >= 12
        ORDER BY runs DESC, strike_rate DESC
        LIMIT :limit
        """,
        {"prev": prev, "tid": tid, "limit": limit},
    )


def team_bowlers_last_season(team_name: str, season: int, limit: int = 20) -> pd.DataFrame:
    """Top bowlers for a team in the previous season."""
    prev = previous_season(season)
    if prev is None:
        return pd.DataFrame()
    tid = team_id_for_name(team_name)
    if tid is None:
        return pd.DataFrame()
    return read_sql(
        """
        SELECT
            p.player_id,
            p.player_name,
            :prev AS form_season,
            COUNT(DISTINCT d.match_id) AS innings,
            SUM(d.is_wicket) AS wickets,
            COUNT(*) AS balls,
            ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy,
            ROUND(1.0 * SUM(d.runs_total) / NULLIF(SUM(d.is_wicket), 0), 2) AS average
        FROM deliveries d
        JOIN players p ON p.player_id = d.bowler_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :prev
          AND d.bowling_team_id = :tid
          AND (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(*) >= 12
        ORDER BY wickets DESC, economy ASC
        LIMIT :limit
        """,
        {"prev": prev, "tid": tid, "limit": limit},
    )


def player_impact_score(batters: pd.DataFrame, bowlers: pd.DataFrame, selected: list[str]) -> float:
    """
    Normalize selected players' last-season form into an impact score ~[-0.15, +0.15].
    Higher means stronger lineup for that team.
    """
    if not selected:
        return 0.0

    score = 0.0
    n = 0
    if batters is not None and not batters.empty:
        b = batters[batters["player_name"].isin(selected)]
        if not b.empty:
            # runs and SR vs pool averages
            run_z = (b["runs"] - batters["runs"].mean()) / max(batters["runs"].std(ddof=0), 1)
            sr_z = (b["strike_rate"].fillna(0) - batters["strike_rate"].fillna(0).mean()) / max(
                batters["strike_rate"].fillna(0).std(ddof=0), 1
            )
            score += float((0.65 * run_z + 0.35 * sr_z).mean())
            n += 1
    if bowlers is not None and not bowlers.empty:
        w = bowlers[bowlers["player_name"].isin(selected)]
        if not w.empty:
            wicket_z = (w["wickets"] - bowlers["wickets"].mean()) / max(bowlers["wickets"].std(ddof=0), 1)
            # lower economy is better
            eco_z = (bowlers["economy"].mean() - w["economy"]) / max(bowlers["economy"].std(ddof=0), 1)
            score += float((0.7 * wicket_z + 0.3 * eco_z).mean())
            n += 1
    if n == 0:
        return 0.0
    # squash
    impact = max(-1.5, min(1.5, score / n))
    return round(0.10 * impact, 4)  # map to roughly +/- 0.15


def adjust_win_probability(base_p_team1: float, team1_impact: float, team2_impact: float) -> dict:
    """Shift team1 win probability using relative player impacts."""
    delta = team1_impact - team2_impact
    adjusted = min(0.95, max(0.05, base_p_team1 + delta))
    return {
        "team1_win_probability": float(adjusted),
        "team2_win_probability": float(1.0 - adjusted),
        "base_team1_win_probability": float(base_p_team1),
        "team1_player_impact": float(team1_impact),
        "team2_player_impact": float(team2_impact),
        "impact_delta": float(delta),
    }
