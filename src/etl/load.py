"""Load processed parquet tables into the SQLite analytics warehouse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import settings
from src.utils.db import get_engine, init_schema, row_count


TABLE_ORDER = ["teams", "venues", "players", "matches", "innings", "deliveries"]


def load_tables_from_dir(processed_dir: Path | None = None) -> dict[str, int]:
    processed_dir = processed_dir or settings.PROCESSED_DIR
    init_schema()
    engine = get_engine()

    counts: dict[str, int] = {}
    for table in TABLE_ORDER:
        parquet = processed_dir / f"{table}.parquet"
        csv = processed_dir / f"{table}.csv"
        if parquet.exists():
            df = pd.read_parquet(parquet)
        elif csv.exists():
            df = pd.read_csv(csv)
        else:
            raise FileNotFoundError(f"Missing processed table: {table}")

        df.to_sql(table, engine, if_exists="append", index=False, chunksize=5000)
        counts[table] = len(df)

    for table in TABLE_ORDER:
        counts[table] = row_count(table)
    return counts


def warehouse_summary() -> pd.DataFrame:
    rows = []
    for table in TABLE_ORDER:
        rows.append({"table": table, "rows": row_count(table)})
    return pd.DataFrame(rows)
