#!/usr/bin/env python3
"""One-shot: ETL → train models → export Power BI assets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("\n>>>", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    py = sys.executable
    run([py, "scripts/run_etl.py", "--source", "auto"])
    run([py, "scripts/train_models.py"])
    run([py, "scripts/export_powerbi.py"])
    print("\n[run_all] Pipeline complete.")
    print("Launch dashboard:  streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
