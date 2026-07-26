#!/usr/bin/env python3
"""Train match-outcome, score, and win-probability models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.match_outcome import train_match_outcome_model, train_win_probability_model
from src.ml.score_prediction import train_score_model
from src.utils.db import table_exists


def main() -> None:
    if not table_exists("deliveries"):
        raise SystemExit("Warehouse empty. Run: python scripts/run_etl.py")

    print("[ml] Training match outcome model…")
    m1 = train_match_outcome_model()
    print(json.dumps({k: m1[k] for k in ("accuracy", "roc_auc", "brier", "n_train", "n_test")}, indent=2))

    print("[ml] Training score prediction model…")
    m2 = train_score_model()
    print(json.dumps(m2, indent=2))

    print("[ml] Training live win-probability model…")
    m3 = train_win_probability_model()
    print(json.dumps({k: m3[k] for k in ("accuracy", "roc_auc", "brier", "n_train", "n_test")}, indent=2))

    print("[ml] All models trained and saved to data/models/")


if __name__ == "__main__":
    main()
