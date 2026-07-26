"""Monte Carlo chase simulator for T20 match states."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.settings import RANDOM_SEED
from src.utils.db import read_sql


@dataclass
class ChaseState:
    target: int
    runs: int
    wickets: int
    overs_done: float  # e.g. 12.3 → handled as balls
    balls_per_innings: int = 120

    @property
    def balls_faced(self) -> int:
        overs = int(self.overs_done)
        balls = int(round((self.overs_done - overs) * 10))
        balls = min(max(balls, 0), 5)
        return overs * 6 + balls

    @property
    def balls_left(self) -> int:
        return max(self.balls_per_innings - self.balls_faced, 0)

    @property
    def runs_needed(self) -> int:
        return max(self.target - self.runs, 0)

    @property
    def wickets_left(self) -> int:
        return max(10 - self.wickets, 0)


def empirical_ball_model(season: int | None = None) -> dict[str, np.ndarray]:
    """Estimate outcome probabilities from warehouse deliveries by phase."""
    params: dict = {}
    season_filter = ""
    if season is not None:
        season_filter = "AND m.season = :season"
        params["season"] = season
    df = read_sql(
        f"""
        SELECT d.phase, d.runs_total, d.is_wicket
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        WHERE (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
          {season_filter}
        """,
        params,
    )
    model: dict[str, np.ndarray] = {}
    # outcomes: wicket, 0, 1, 2, 3, 4, 6
    labels = ["wicket", 0, 1, 2, 3, 4, 6]
    for phase, g in df.groupby("phase"):
        n = max(len(g), 1)
        wicket_p = float(g["is_wicket"].mean())
        legal = g[g["is_wicket"] == 0]["runs_total"]
        # clamp rare values
        legal = legal.clip(0, 6)
        counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 6: 0}
        for v, c in legal.value_counts().items():
            if int(v) in counts:
                counts[int(v)] = int(c)
            elif int(v) == 5:
                counts[4] += int(c)
        total_legal = sum(counts.values()) or 1
        run_ps = {k: (1 - wicket_p) * (counts[k] / total_legal) for k in counts}
        probs = np.array(
            [wicket_p, run_ps[0], run_ps[1], run_ps[2], run_ps[3], run_ps[4], run_ps[6]],
            dtype=float,
        )
        probs = probs / probs.sum()
        model[str(phase)] = probs
        model[f"{phase}_labels"] = np.array(labels, dtype=object)
    # fallback
    if "middle" not in model:
        model["middle"] = np.array([0.05, 0.35, 0.35, 0.10, 0.02, 0.09, 0.04])
        model["middle_labels"] = np.array(labels, dtype=object)
    return model


def _phase_for_ball(balls_faced: int) -> str:
    over = balls_faced // 6 + 1
    if over <= 6:
        return "powerplay"
    if over <= 15:
        return "middle"
    return "death"


def simulate_chase(
    state: ChaseState,
    n_sims: int = 2000,
    season: int | None = None,
    seed: int = RANDOM_SEED,
) -> dict:
    """Return win probability and score distribution from current chase state."""
    rng = np.random.default_rng(seed)
    model = empirical_ball_model(season)
    wins = 0
    finals = []
    wickets_end = []

    for _ in range(n_sims):
        runs = state.runs
        wickets = state.wickets
        balls = state.balls_faced
        target = state.target

        while balls < state.balls_per_innings and wickets < 10 and runs < target:
            phase = _phase_for_ball(balls)
            probs = model.get(phase, model["middle"])
            labels = model.get(f"{phase}_labels", model["middle_labels"])
            outcome = rng.choice(labels, p=probs)
            if outcome == "wicket":
                wickets += 1
            else:
                runs += int(outcome)
            balls += 1

        finals.append(runs)
        wickets_end.append(wickets)
        if runs >= target:
            wins += 1

    finals_arr = np.array(finals)
    return {
        "win_probability": wins / n_sims,
        "mean_final_score": float(finals_arr.mean()),
        "p10": float(np.percentile(finals_arr, 10)),
        "p50": float(np.percentile(finals_arr, 50)),
        "p90": float(np.percentile(finals_arr, 90)),
        "avg_wickets": float(np.mean(wickets_end)),
        "n_sims": n_sims,
        "runs_needed": state.runs_needed,
        "balls_left": state.balls_left,
        "required_rr": (
            state.runs_needed / (state.balls_left / 6.0) if state.balls_left else None
        ),
        "distribution": pd.Series(finals_arr).value_counts().sort_index(),
    }
