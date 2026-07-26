"""Multi-player comparison metrics for radar / side-by-side views."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def player_season_profile(player_name: str, season: int | None = None) -> dict:
    params: dict = {"player": player_name}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season

    bat = read_sql(
        f"""
        SELECT
            COALESCE(SUM(d.runs_batter), 0) AS runs,
            COUNT(*) AS balls,
            COALESCE(SUM(d.is_boundary), 0) AS fours,
            COALESCE(SUM(d.is_six), 0) AS sixes,
            COALESCE(SUM(d.is_wicket), 0) AS outs,
            ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
            ROUND(1.0 * SUM(d.runs_batter) / NULLIF(SUM(d.is_wicket), 0), 2) AS average
        FROM deliveries d
        JOIN players p ON p.player_id = d.striker_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE p.player_name = :player {season_filter}
        """,
        params,
    )
    bowl = read_sql(
        f"""
        SELECT
            COUNT(*) AS balls_bowled,
            COALESCE(SUM(d.runs_total), 0) AS runs_conceded,
            COALESCE(SUM(d.is_wicket), 0) AS wickets,
            ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy
        FROM deliveries d
        JOIN players p ON p.player_id = d.bowler_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE p.player_name = :player
          AND (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
          {season_filter}
        """,
        params,
    )

    b = bat.iloc[0].to_dict() if not bat.empty else {}
    w = bowl.iloc[0].to_dict() if not bowl.empty else {}
    return {
        "player_name": player_name,
        "runs": float(b.get("runs") or 0),
        "balls": float(b.get("balls") or 0),
        "strike_rate": float(b.get("strike_rate") or 0),
        "average": float(b.get("average") or 0),
        "fours": float(b.get("fours") or 0),
        "sixes": float(b.get("sixes") or 0),
        "wickets": float(w.get("wickets") or 0),
        "economy": float(w.get("economy") or 0),
        "balls_bowled": float(w.get("balls_bowled") or 0),
    }


def compare_players(players: list[str], season: int | None = None) -> pd.DataFrame:
    rows = [player_season_profile(p, season) for p in players]
    return pd.DataFrame(rows)


def radar_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize selected metrics 0-100 for radar charting."""
    if df.empty:
        return df
    metrics = {
        "runs": True,
        "strike_rate": True,
        "average": True,
        "sixes": True,
        "wickets": True,
        "economy": False,  # lower is better
    }
    out = df[["player_name"]].copy()
    for col, higher_better in metrics.items():
        series = df[col].fillna(0).astype(float)
        mn, mx = series.min(), series.max()
        if mx == mn:
            norm = pd.Series([50.0] * len(series))
        elif higher_better:
            norm = 100 * (series - mn) / (mx - mn)
        else:
            norm = 100 * (mx - series) / (mx - mn)
        out[col] = norm.round(1)
    return out
