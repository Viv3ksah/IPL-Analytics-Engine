"""Feature engineering for match-outcome and score models."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def build_match_feature_frame() -> pd.DataFrame:
    """One row per match with pre-result features + labels."""
    q = """
    WITH team_hist AS (
        SELECT
            m.match_id,
            m.season,
            m.match_date,
            m.venue_id,
            m.team1_id,
            m.team2_id,
            m.toss_winner_id,
            m.toss_decision,
            m.winner_id,
            m.win_by_runs,
            m.win_by_wickets,
            i1.total_runs AS innings1_runs,
            i1.total_wickets AS innings1_wickets,
            i2.total_runs AS innings2_runs,
            i2.total_wickets AS innings2_wickets
        FROM matches m
        LEFT JOIN innings i1 ON i1.match_id = m.match_id AND i1.innings_number = 1
        LEFT JOIN innings i2 ON i2.match_id = m.match_id AND i2.innings_number = 2
        WHERE m.winner_id IS NOT NULL
    ),
    venue_avg AS (
        SELECT venue_id, AVG(total_runs) AS venue_avg_score
        FROM matches m
        JOIN innings i ON i.match_id = m.match_id AND i.innings_number = 1
        GROUP BY venue_id
    ),
    team_win AS (
        SELECT team_id, AVG(win) AS win_rate FROM (
            SELECT team1_id AS team_id, CASE WHEN winner_id = team1_id THEN 1.0 ELSE 0.0 END AS win
            FROM matches WHERE winner_id IS NOT NULL
            UNION ALL
            SELECT team2_id AS team_id, CASE WHEN winner_id = team2_id THEN 1.0 ELSE 0.0 END AS win
            FROM matches WHERE winner_id IS NOT NULL
        ) GROUP BY team_id
    )
    SELECT
        h.*,
        v.venue_avg_score,
        tw1.win_rate AS team1_win_rate,
        tw2.win_rate AS team2_win_rate,
        CASE WHEN h.toss_winner_id = h.team1_id THEN 1 ELSE 0 END AS team1_won_toss,
        CASE WHEN h.toss_decision = 'bat' THEN 1 ELSE 0 END AS chose_bat,
        CASE WHEN h.winner_id = h.team1_id THEN 1 ELSE 0 END AS team1_won,
        CASE WHEN h.win_by_wickets > 0 THEN 1 ELSE 0 END AS chased_successful
    FROM team_hist h
    LEFT JOIN venue_avg v ON v.venue_id = h.venue_id
    LEFT JOIN team_win tw1 ON tw1.team_id = h.team1_id
    LEFT JOIN team_win tw2 ON tw2.team_id = h.team2_id
    """
    df = read_sql(q)
    df["win_rate_diff"] = df["team1_win_rate"] - df["team2_win_rate"]
    df["season"] = df["season"].astype(int)
    return df.dropna(subset=["innings1_runs", "team1_won"])


def build_score_feature_frame() -> pd.DataFrame:
    """Over-level progressive features for first-innings score prediction."""
    q = """
    SELECT
        d.match_id,
        d.innings_id,
        d.innings_number,
        m.season,
        m.venue_id,
        d.over_number,
        d.batting_team_id,
        d.bowling_team_id,
        i.total_runs AS final_score,
        SUM(d.runs_total) OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cum_runs,
        SUM(d.is_wicket) OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cum_wickets,
        ROW_NUMBER() OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
        ) AS balls_faced
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.innings_id = d.innings_id
    WHERE d.innings_number = 1
    """
    ball = read_sql(q)
    # sample end-of-over snapshots for modeling efficiency
    over_end = (
        ball.sort_values(["innings_id", "balls_faced"])
        .groupby(["innings_id", "over_number"], as_index=False)
        .tail(1)
    )
    over_end = over_end[over_end["over_number"].between(5, 16)].copy()
    over_end["current_rr"] = over_end["cum_runs"] / (over_end["balls_faced"] / 6.0)
    over_end["wickets_in_hand"] = 10 - over_end["cum_wickets"]
    over_end["overs_left"] = 20 - over_end["over_number"]
    over_end["proj_naive"] = over_end["current_rr"] * 20
    return over_end.dropna()


def build_live_chase_frame() -> pd.DataFrame:
    """Second-innings ball states for win-probability modeling."""
    q = """
    SELECT
        d.match_id,
        d.innings_id,
        m.winner_id,
        i.batting_team_id,
        i1.total_runs AS target_raw,
        d.over_number,
        d.ball_number,
        SUM(d.runs_total) OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
        ) AS cum_runs,
        SUM(d.is_wicket) OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
        ) AS cum_wickets,
        ROW_NUMBER() OVER (
            PARTITION BY d.innings_id ORDER BY d.over_number, d.ball_number
        ) AS balls_faced
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.innings_id = d.innings_id
    JOIN innings i1 ON i1.match_id = d.match_id AND i1.innings_number = 1
    WHERE d.innings_number = 2 AND m.winner_id IS NOT NULL
    """
    df = read_sql(q)
    df["target"] = df["target_raw"] + 1
    df["runs_needed"] = (df["target"] - df["cum_runs"]).clip(lower=0)
    df["balls_left"] = (120 - df["balls_faced"]).clip(lower=0)
    df["wickets_left"] = (10 - df["cum_wickets"]).clip(lower=0)
    df["required_rr"] = df.apply(
        lambda r: (r["runs_needed"] / (r["balls_left"] / 6.0)) if r["balls_left"] > 0 else 99.0,
        axis=1,
    )
    df["chasing_team_won"] = (df["winner_id"] == df["batting_team_id"]).astype(int)
    # end-of-over samples
    snap = (
        df.sort_values(["innings_id", "balls_faced"])
        .groupby(["innings_id", "over_number"], as_index=False)
        .tail(1)
    )
    return snap
