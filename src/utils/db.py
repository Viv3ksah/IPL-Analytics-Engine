"""Database helpers for the IPL analytics warehouse."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd
from sqlalchemy import create_engine, text

from config import settings


def get_engine(echo: bool = False):
    return create_engine(settings.DB_URL, echo=echo, future=True)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(schema_path: Path | None = None) -> None:
    schema_path = schema_path or (settings.PROJECT_ROOT / "db" / "schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(sql)


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def table_exists(table: str) -> bool:
    df = read_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:name",
        {"name": table},
    )
    return not df.empty


def row_count(table: str) -> int:
    df = read_sql(f"SELECT COUNT(*) AS n FROM {table}")
    return int(df.iloc[0]["n"])
