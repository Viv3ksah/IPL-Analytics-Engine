"""Fantasy Dream Team builder from season performance."""

from __future__ import annotations

import pandas as pd

from src.utils.db import read_sql


def player_fantasy_pool(season: int, min_balls: int = 24) -> pd.DataFrame:
    """Build a fantasy-eligible pool with bat/bowl/allrounder scores."""
    bat = read_sql(
        """
        SELECT
            p.player_id,
            p.player_name,
            COALESCE(p.role, 'unknown') AS role,
            SUM(d.runs_batter) AS runs,
            COUNT(*) AS bat_balls,
            SUM(d.is_boundary) AS fours,
            SUM(d.is_six) AS sixes,
            SUM(d.is_wicket) AS outs
        FROM players p
        JOIN deliveries d ON d.striker_id = p.player_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
        GROUP BY p.player_id, p.player_name, p.role
        """,
        {"season": season},
    )
    bowl = read_sql(
        """
        SELECT
            p.player_id,
            SUM(d.is_wicket) AS wickets,
            COUNT(*) AS bowl_balls,
            SUM(d.runs_total) AS runs_conceded,
            SUM(CASE WHEN d.runs_total = 0 THEN 1 ELSE 0 END) AS dots
        FROM players p
        JOIN deliveries d ON d.bowler_id = p.player_id
        JOIN matches m ON m.match_id = d.match_id
        WHERE m.season = :season
          AND (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
        GROUP BY p.player_id
        """,
        {"season": season},
    )
    df = bat.merge(bowl, on="player_id", how="outer")
    # attach names for bowl-only
    names = read_sql("SELECT player_id, player_name, COALESCE(role, 'unknown') AS role FROM players")
    df = names.merge(df.drop(columns=[c for c in ("player_name", "role") if c in df.columns], errors="ignore"), on="player_id", how="inner")
    for col in ("runs", "bat_balls", "fours", "sixes", "outs", "wickets", "bowl_balls", "runs_conceded", "dots"):
        if col in df.columns:
            df[col] = df[col].fillna(0)
        else:
            df[col] = 0

    df = df[(df["bat_balls"] >= min_balls) | (df["bowl_balls"] >= min_balls)].copy()

    df["bat_pts"] = (
        df["runs"]
        + df["fours"]
        + df["sixes"] * 2
        + (df["runs"] >= 50).astype(int) * 8
        + (df["runs"] >= 100).astype(int) * 16
    )
    df["bowl_pts"] = df["wickets"] * 25 + df["dots"] * 0.5
    # economy bonus for meaningful overs
    overs = (df["bowl_balls"] / 6.0).replace(0, pd.NA)
    eco = df["runs_conceded"] / overs
    df["bowl_pts"] = df["bowl_pts"] + ((eco < 7) & (df["bowl_balls"] >= 24)).astype(int) * 6
    df["total_pts"] = (df["bat_pts"] + df["bowl_pts"]).round(1)

    # infer role if unknown
    def _infer(row):
        if row["role"] and row["role"] != "unknown":
            return row["role"]
        if row["wickets"] >= 8 and row["runs"] >= 120:
            return "allrounder"
        if row["wickets"] >= 10 and row["runs"] < 120:
            return "bowler"
        if row["runs"] >= 150:
            return "batsman"
        return "allrounder"

    df["role_inferred"] = df.apply(_infer, axis=1)
    # Fantasy-style credits (~5.5–10) so a full XI fits near 100
    pts = df["total_pts"].astype(float)
    pmin, pmax = pts.min(), pts.max()
    if pmax == pmin:
        df["credit"] = 8.0
    else:
        df["credit"] = (5.5 + (pts - pmin) / (pmax - pmin) * 4.5).round(1)
    return df.sort_values("total_pts", ascending=False).reset_index(drop=True)


def build_dream_team(
    season: int,
    team_size: int = 11,
    max_credits: float = 100.0,
    min_balls: int = 24,
) -> pd.DataFrame:
    """
    Greedy fantasy XI:
    - 11 players
    - at least 3 bat-leaning, 3 bowl-leaning, 1 allrounder
    - credit cap
    """
    pool = player_fantasy_pool(season, min_balls=min_balls)
    if pool.empty:
        return pool

    selected: list[pd.Series] = []
    used_credits = 0.0
    counts = {"batsman": 0, "bowler": 0, "allrounder": 0}

    def role_bucket(role: str) -> str:
        if role in ("batsman", "wicketkeeper"):
            return "batsman"
        if role == "bowler":
            return "bowler"
        return "allrounder"

    remaining = pool.copy()
    min_credit = float(pool["credit"].min())

    def room_for_rest(after_add_credit: float) -> bool:
        slots_after = team_size - (len(selected) + 1)
        return used_credits + after_add_credit + slots_after * min_credit <= max_credits + 1e-9

    def try_add(row, enforce_reserve: bool = True) -> bool:
        nonlocal used_credits, remaining
        if len(selected) >= team_size:
            return False
        credit = float(row["credit"])
        if used_credits + credit > max_credits:
            return False
        if enforce_reserve and not room_for_rest(credit):
            return False
        selected.append(row)
        used_credits += credit
        bucket = role_bucket(row["role_inferred"])
        counts[bucket] = counts.get(bucket, 0) + 1
        remaining = remaining[remaining["player_id"] != row["player_id"]]
        return True

    # Pass 1: satisfy minimum role mix (best available in each bucket)
    for need_role, need_n in [("batsman", 3), ("bowler", 3), ("allrounder", 1)]:
        cand = remaining[remaining["role_inferred"].map(role_bucket) == need_role]
        for _, row in cand.iterrows():
            if counts.get(need_role, 0) >= need_n:
                break
            try_add(row, enforce_reserve=True)

    # Pass 2: fill by points/credit value
    remaining = remaining.assign(value=remaining["total_pts"] / remaining["credit"]).sort_values(
        "value", ascending=False
    )
    for _, row in remaining.iterrows():
        if len(selected) >= team_size:
            break
        try_add(row, enforce_reserve=True)

    # Pass 3: finish XI with cheapest affordable players (tiny soft overspend OK)
    if len(selected) < team_size:
        soft_cap = max_credits + 1.0
        for _, row in remaining.sort_values(["credit", "total_pts"], ascending=[True, False]).iterrows():
            if len(selected) >= team_size:
                break
            credit = float(row["credit"])
            if used_credits + credit > soft_cap:
                continue
            selected.append(row)
            used_credits += credit
            bucket = role_bucket(row["role_inferred"])
            counts[bucket] = counts.get(bucket, 0) + 1
            remaining = remaining[remaining["player_id"] != row["player_id"]]

    if not selected:
        return pd.DataFrame()

    xi = pd.DataFrame(selected).sort_values("total_pts", ascending=False).reset_index(drop=True)
    xi["credits_used"] = round(used_credits, 1)
    return xi[
        [
            "player_name",
            "role_inferred",
            "runs",
            "wickets",
            "bat_pts",
            "bowl_pts",
            "total_pts",
            "credit",
            "credits_used",
        ]
    ]
