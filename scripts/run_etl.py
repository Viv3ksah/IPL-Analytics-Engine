#!/usr/bin/env python3
"""End-to-end ETL: acquire data → process → load SQLite warehouse."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import PROCESSED_DIR, TARGET_MIN_BALLS
from src.etl.download_cricsheet import try_load_cricsheet
from src.etl.generate_synthetic import generate_synthetic_ipl
from src.etl.load import load_tables_from_dir, warehouse_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IPL Analytics ETL pipeline")
    parser.add_argument(
        "--source",
        choices=["auto", "cricsheet", "synthetic"],
        default="auto",
        help="Data source (default: auto tries Cricsheet then synthetic)",
    )
    parser.add_argument("--matches-per-season", type=int, default=70)
    args = parser.parse_args()

    tables = None
    source_used = args.source

    if args.source in ("auto", "cricsheet"):
        tables = try_load_cricsheet()
        if tables is not None:
            source_used = "cricsheet"
            if len(tables["deliveries"]) < TARGET_MIN_BALLS and args.source == "auto":
                print(
                    f"[etl] Cricsheet has {len(tables['deliveries'])} balls "
                    f"(< {TARGET_MIN_BALLS}); augmenting with synthetic for portfolio scale"
                )
                tables = None
                source_used = "synthetic"

    if tables is None:
        print("[etl] Generating synthetic IPL ball-by-ball dataset…")
        tables = generate_synthetic_ipl(matches_per_season=args.matches_per_season)
        source_used = "synthetic"

    print("[etl] Loading warehouse…")
    counts = load_tables_from_dir(PROCESSED_DIR)
    print(f"[etl] Source: {source_used}")
    for table, n in counts.items():
        print(f"  {table:12s} {n:,}")
    print("\nWarehouse summary:")
    print(warehouse_summary().to_string(index=False))
    print("\n[etl] Done.")


if __name__ == "__main__":
    main()
