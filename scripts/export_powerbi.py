#!/usr/bin/env python3
"""Export star-schema CSVs and a Power BI-ready Excel workbook."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import EXPORTS_DIR
from src.utils.db import read_sql, table_exists


VIEWS = [
    ("dim_teams", "SELECT * FROM teams"),
    ("dim_venues", "SELECT * FROM venues"),
    ("dim_players", "SELECT * FROM players"),
    ("fact_matches", "SELECT * FROM matches"),
    ("fact_innings", "SELECT * FROM innings"),
    ("v_match_summary", "SELECT * FROM v_match_summary"),
    ("v_player_batting", "SELECT * FROM v_player_batting"),
    ("v_player_bowling", "SELECT * FROM v_player_bowling"),
    ("v_venue_stats", "SELECT * FROM v_venue_stats"),
    ("v_team_season", "SELECT * FROM v_team_season"),
]


def export_fact_deliveries_sample(limit: int = 200_000) -> pd.DataFrame:
    """Full deliveries can be huge in Excel; export parquet + capped CSV."""
    return read_sql(f"SELECT * FROM deliveries LIMIT {int(limit)}")


def main() -> None:
    if not table_exists("matches"):
        raise SystemExit("Warehouse empty. Run: python scripts/run_etl.py")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}

    for name, query in VIEWS:
        df = read_sql(query)
        frames[name] = df
        df.to_csv(EXPORTS_DIR / f"{name}.csv", index=False)
        print(f"  wrote {name}.csv ({len(df):,} rows)")

    deliveries = export_fact_deliveries_sample()
    deliveries.to_csv(EXPORTS_DIR / "fact_deliveries.csv", index=False)
    deliveries.to_parquet(EXPORTS_DIR / "fact_deliveries.parquet", index=False)
    print(f"  wrote fact_deliveries.csv/parquet ({len(deliveries):,} rows)")

    # Power BI often prefers xlsx sheets for dims + aggregates
    xlsx_path = EXPORTS_DIR / "ipl_powerbi_model.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for name in [
            "dim_teams",
            "dim_venues",
            "dim_players",
            "fact_matches",
            "fact_innings",
            "v_match_summary",
            "v_player_batting",
            "v_player_bowling",
            "v_venue_stats",
            "v_team_season",
        ]:
            # Excel sheet name limit 31
            frames[name].to_excel(writer, sheet_name=name[:31], index=False)
    print(f"  wrote {xlsx_path.name}")

    # relationship guide
    guide = EXPORTS_DIR / "powerbi_relationships.txt"
    guide.write_text(
        """Power BI relationship guide (star schema)
========================================
dim_teams[team_id]      -> fact_matches[team1_id]
dim_teams[team_id]      -> fact_matches[team2_id]
dim_teams[team_id]      -> fact_matches[winner_id]
dim_venues[venue_id]    -> fact_matches[venue_id]
dim_players[player_id]  -> fact_matches[player_of_match_id]
fact_matches[match_id]  -> fact_innings[match_id]
fact_matches[match_id]  -> fact_deliveries[match_id]
dim_players[player_id]  -> fact_deliveries[striker_id]
dim_players[player_id]  -> fact_deliveries[bowler_id]

Suggested pages:
1. Season Overview — wins, run rates, toss impact
2. Player Bat/Bowl — leaderboards from v_player_*
3. Venue Lab — batting index, chase %
4. Match Explorer — v_match_summary slicers
""",
        encoding="utf-8",
    )
    print(f"  wrote {guide.name}")
    print("[export] Power BI assets ready in data/exports/")


if __name__ == "__main__":
    main()
