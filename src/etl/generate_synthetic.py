"""Generate realistic IPL-scale ball-by-ball data (≥250K deliveries).

Used when Cricsheet downloads are unavailable. Produces matches, innings,
and deliveries with season/team/venue/player structure suitable for
analytics and ML.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    FRANCHISES,
    PROCESSED_DIR,
    RANDOM_SEED,
    SYNTHETIC_MATCHES_PER_SEASON,
    SYNTHETIC_SEASONS,
    TARGET_MIN_BALLS,
    VENUES,
)

FIRST_NAMES = [
    "Virat", "Rohit", "MS", "Jasprit", "Ravindra", "Hardik", "KL", "Shubman",
    "Rishabh", "Suryakumar", "Yuzvendra", "Bhuvneshwar", "Mohammed", "Kagiso",
    "Trent", "Jos", "David", "AB", "Chris", "Andre", "Sunil", "Rashid",
    "Nicholas", "Faf", "Glenn", "Pat", "Mitchell", "Kane", "Quinton", "Shimron",
    "Prithvi", "Ishan", "Sanju", "Shreyas", "Axar", "Ravichandran", "Kuldeep",
    "Mayank", "Deepak", "Arshdeep", "Harshal", "Varun", "Rinku", "Tilak",
    "Yashasvi", "Ruturaj", "Devon", "Tim", "Marcus", "Cameron", "Liam",
    "Jason", "Sam", "Ben", "Harry", "Phil", "Moeen", "Adil", "Imran",
]

LAST_NAMES = [
    "Kohli", "Sharma", "Dhoni", "Bumrah", "Jadeja", "Pandya", "Rahul", "Gill",
    "Pant", "Yadav", "Chahal", "Kumar", "Siraj", "Rabada", "Boult", "Buttler",
    "Warner", "de Villiers", "Gayle", "Russell", "Narine", "Khan", "Pooran",
    "du Plessis", "Maxwell", "Cummins", "Starc", "Williamson", "de Kock",
    "Hetmyer", "Shaw", "Kishan", "Samson", "Iyer", "Patel", "Ashwin",
    "Yadav", "Agarwal", "Chahar", "Singh", "Patel", "Chakravarthy", "Singh",
    "Varma", "Jaiswal", "Gaikwad", "Conway", "David", "Stoinis", "Green",
    "Livingstone", "Roy", "Curran", "Stokes", "Brook", "Salt", "Ali",
    "Rashid", "Tahir", "Pathan",
]

SHORT = {
    "Chennai Super Kings": "CSK",
    "Mumbai Indians": "MI",
    "Royal Challengers Bangalore": "RCB",
    "Kolkata Knight Riders": "KKR",
    "Rajasthan Royals": "RR",
    "Delhi Capitals": "DC",
    "Punjab Kings": "PBKS",
    "Sunrisers Hyderabad": "SRH",
    "Gujarat Titans": "GT",
    "Lucknow Super Giants": "LSG",
    "Deccan Chargers": "DCH",
    "Gujarat Lions": "GL",
    "Rising Pune Supergiant": "RPS",
    "Pune Warriors": "PWI",
    "Kochi Tuskers Kerala": "KTK",
}


def _season_teams(season: int) -> list[str]:
    base = FRANCHISES[:8]
    if season <= 2012:
        return base[:8]
    if season in (2016, 2017):
        return base[:8]
    if season >= 2022:
        return FRANCHISES[:10]
    return FRANCHISES[:8]


def _build_players(rng: np.random.Generator, n: int = 420) -> pd.DataFrame:
    names = []
    for i, (fn, ln) in enumerate(itertools.product(FIRST_NAMES, LAST_NAMES)):
        names.append(f"{fn} {ln}")
        if len(names) >= n:
            break
    # ensure uniqueness
    seen = set()
    unique = []
    for name in names:
        if name in seen:
            name = f"{name} {len(unique)}"
        seen.add(name)
        unique.append(name)

    roles = rng.choice(
        ["batsman", "bowler", "allrounder", "wicketkeeper"],
        size=len(unique),
        p=[0.35, 0.30, 0.25, 0.10],
    )
    return pd.DataFrame(
        {
            "player_id": np.arange(1, len(unique) + 1),
            "player_name": unique,
            "batting_hand": rng.choice(["Right", "Left"], size=len(unique), p=[0.7, 0.3]),
            "bowling_style": rng.choice(
                ["Right-arm fast", "Left-arm fast", "Right-arm spin", "Left-arm spin", "None"],
                size=len(unique),
                p=[0.25, 0.15, 0.25, 0.15, 0.20],
            ),
            "role": roles,
        }
    )


def _phase(over: int) -> str:
    if over <= 6:
        return "powerplay"
    if over <= 15:
        return "middle"
    return "death"


def _simulate_innings(
    rng: np.random.Generator,
    batting_ids: list[int],
    bowling_ids: list[int],
    batting_strength: float,
    bowling_strength: float,
    target: int | None = None,
) -> tuple[list[dict], int, int, float, int]:
    """Simulate one T20 innings ball-by-ball."""
    deliveries: list[dict] = []
    score = 0
    wickets = 0
    striker_idx = 0
    non_striker_idx = 1
    next_batter = 2
    legal_balls_in_over = 0
    over = 1
    ball_in_over = 0
    extras_total = 0

    # rate modifiers by phase
    while over <= 20 and wickets < 10:
        if target is not None and score >= target:
            break

        bowler = bowling_ids[(over - 1) % len(bowling_ids)]
        phase = _phase(over)
        base_run = {
            "powerplay": 1.45,
            "middle": 1.25,
            "death": 1.70,
        }[phase]
        run_rate = base_run * batting_strength / max(bowling_strength, 0.6)
        wicket_p = {"powerplay": 0.035, "middle": 0.045, "death": 0.06}[phase]
        wicket_p *= bowling_strength / max(batting_strength, 0.6)
        wicket_p = min(0.18, max(0.01, wicket_p))

        # outcome distribution for legal deliveries
        # 0,1,2,3,4,6 + rare wickets handled separately
        probs = np.array([0.34, 0.38, 0.10, 0.02, 0.11, 0.05], dtype=float)
        # shift toward boundaries when run_rate high
        shift = np.clip((run_rate - 1.3) * 0.08, -0.08, 0.12)
        probs[0] -= shift
        probs[4] += shift * 0.6
        probs[5] += shift * 0.4
        probs = np.clip(probs, 0.01, None)
        probs /= probs.sum()
        outcomes = np.array([0, 1, 2, 3, 4, 6])

        # extras chance
        if rng.random() < 0.04:
            extras_type = rng.choice(["wides", "noballs", "byes", "legbyes"], p=[0.45, 0.2, 0.15, 0.2])
            extra_runs = int(rng.choice([1, 1, 1, 2, 4], p=[0.55, 0.2, 0.1, 0.1, 0.05]))
            batter_runs = 0
            if extras_type == "noballs":
                batter_runs = int(rng.choice([0, 1, 2, 4, 6], p=[0.4, 0.3, 0.1, 0.15, 0.05]))
            total = extra_runs + batter_runs
            score += total
            extras_total += extra_runs
            ball_in_over += 1
            deliveries.append(
                {
                    "over_number": over,
                    "ball_number": ball_in_over,
                    "striker_id": batting_ids[striker_idx],
                    "non_striker_id": batting_ids[non_striker_idx],
                    "bowler_id": bowler,
                    "runs_batter": batter_runs,
                    "runs_extras": extra_runs,
                    "runs_total": total,
                    "extras_type": extras_type,
                    "is_wicket": 0,
                    "dismissal_kind": None,
                    "player_dismissed_id": None,
                    "is_dot": int(total == 0),
                    "is_boundary": int(batter_runs == 4),
                    "is_six": int(batter_runs == 6),
                    "phase": phase,
                }
            )
            if extras_type in ("wides", "noballs"):
                # not a legal ball — continue same over slot conceptually
                # simplify: count as ball but don't advance legal count
                pass
            else:
                legal_balls_in_over += 1
            if legal_balls_in_over >= 6:
                over += 1
                legal_balls_in_over = 0
                ball_in_over = 0
                striker_idx, non_striker_idx = non_striker_idx, striker_idx
            continue

        ball_in_over += 1
        is_wicket = 0
        dismissal_kind = None
        dismissed = None
        batter_runs = 0

        if rng.random() < wicket_p:
            is_wicket = 1
            dismissal_kind = rng.choice(
                ["caught", "bowled", "lbw", "run out", "stumped", "caught and bowled"],
                p=[0.55, 0.18, 0.12, 0.08, 0.04, 0.03],
            )
            dismissed = batting_ids[striker_idx]
            if dismissal_kind == "run out" and rng.random() < 0.35:
                dismissed = batting_ids[non_striker_idx]
            wickets += 1
        else:
            batter_runs = int(rng.choice(outcomes, p=probs))

        total = batter_runs
        score += total
        legal_balls_in_over += 1

        deliveries.append(
            {
                "over_number": over,
                "ball_number": ball_in_over,
                "striker_id": batting_ids[striker_idx],
                "non_striker_id": batting_ids[non_striker_idx],
                "bowler_id": bowler,
                "runs_batter": batter_runs,
                "runs_extras": 0,
                "runs_total": total,
                "extras_type": None,
                "is_wicket": is_wicket,
                "dismissal_kind": dismissal_kind,
                "player_dismissed_id": dismissed,
                "is_dot": int(total == 0 and not is_wicket),
                "is_boundary": int(batter_runs == 4),
                "is_six": int(batter_runs == 6),
                "phase": phase,
            }
        )

        if is_wicket:
            if dismissed == batting_ids[striker_idx]:
                if next_batter < len(batting_ids):
                    striker_idx = next_batter
                    next_batter += 1
                else:
                    break
            else:
                if next_batter < len(batting_ids):
                    non_striker_idx = next_batter
                    next_batter += 1
                else:
                    break
        elif batter_runs % 2 == 1:
            striker_idx, non_striker_idx = non_striker_idx, striker_idx

        if legal_balls_in_over >= 6:
            over += 1
            legal_balls_in_over = 0
            ball_in_over = 0
            striker_idx, non_striker_idx = non_striker_idx, striker_idx

    total_overs = (over - 1) + legal_balls_in_over / 6.0 if over <= 20 else 20.0
    if over > 20:
        total_overs = 20.0
    return deliveries, score, wickets, round(total_overs, 1), extras_total


def generate_synthetic_ipl(
    seasons: list[int] | None = None,
    matches_per_season: int | None = None,
    seed: int = RANDOM_SEED,
    output_dir: Path | None = None,
    min_balls: int | None = TARGET_MIN_BALLS,
) -> dict[str, pd.DataFrame]:
    """Generate full synthetic IPL dataset and write parquet/csv snapshots."""
    seasons = seasons or SYNTHETIC_SEASONS
    matches_per_season = matches_per_season or SYNTHETIC_MATCHES_PER_SEASON
    output_dir = output_dir or PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    players = _build_players(rng)

    teams = pd.DataFrame(
        {
            "team_id": np.arange(1, len(FRANCHISES) + 1),
            "team_name": FRANCHISES,
            "short_name": [SHORT.get(t, t[:3].upper()) for t in FRANCHISES],
            "city": [
                "Chennai", "Mumbai", "Bengaluru", "Kolkata", "Jaipur",
                "Delhi", "Mohali", "Hyderabad", "Ahmedabad", "Lucknow",
            ],
        }
    )
    # extend for historical sides used occasionally
    extra_teams = [
        ("Deccan Chargers", "DCH", "Hyderabad"),
        ("Gujarat Lions", "GL", "Rajkot"),
        ("Rising Pune Supergiant", "RPS", "Pune"),
        ("Pune Warriors", "PWI", "Pune"),
        ("Kochi Tuskers Kerala", "KTK", "Kochi"),
    ]
    for name, short, city in extra_teams:
        if name not in set(teams["team_name"]):
            teams = pd.concat(
                [
                    teams,
                    pd.DataFrame(
                        [{
                            "team_id": int(teams["team_id"].max()) + 1,
                            "team_name": name,
                            "short_name": short,
                            "city": city,
                        }]
                    ),
                ],
                ignore_index=True,
            )

    venues = pd.DataFrame(
        {
            "venue_id": np.arange(1, len(VENUES) + 1),
            "venue_name": [v[0] for v in VENUES],
            "city": [v[1] for v in VENUES],
            "country": "India",
            "capacity": rng.integers(25000, 110000, size=len(VENUES)),
        }
    )

    team_strength = {tid: float(rng.uniform(0.85, 1.15)) for tid in teams["team_id"]}
    player_bat = {pid: float(rng.uniform(0.75, 1.30)) for pid in players["player_id"]}
    player_bowl = {pid: float(rng.uniform(0.75, 1.30)) for pid in players["player_id"]}

    # roster: assign ~25 players per team
    roster: dict[int, list[int]] = {}
    pid_pool = players["player_id"].tolist()
    rng.shuffle(pid_pool)
    for i, tid in enumerate(teams["team_id"]):
        start = (i * 22) % max(1, len(pid_pool) - 22)
        roster[tid] = pid_pool[start : start + 22]
        if len(roster[tid]) < 11:
            roster[tid] = pid_pool[:22]

    match_rows = []
    innings_rows = []
    delivery_rows = []
    match_id = 1
    innings_id = 1
    delivery_id = 1

    for season in seasons:
        season_teams = _season_teams(season)
        team_ids = teams.set_index("team_name").loc[season_teams, "team_id"].tolist()
        # round-robin-ish schedule
        pairs = []
        for a, b in itertools.combinations(team_ids, 2):
            pairs.append((a, b))
            pairs.append((b, a))
        rng.shuffle(pairs)
        pairs = pairs[:matches_per_season]
        # pad if needed
        while len(pairs) < matches_per_season:
            a, b = rng.choice(team_ids, size=2, replace=False)
            pairs.append((int(a), int(b)))

        # sequential calendar across Mar–May to avoid colliding fixtures
        day_cursor = 0
        for mi, (t1, t2) in enumerate(pairs):
            venue_id = int(rng.choice(venues["venue_id"]))
            day_cursor += 1
            # map to Mar(31)+Apr(30)+May(31) window, wrapping if needed
            ordinal = (day_cursor - 1) % (31 + 30 + 31)
            if ordinal < 31:
                month, day = 3, ordinal + 1
            elif ordinal < 61:
                month, day = 4, ordinal - 31 + 1
            else:
                month, day = 5, ordinal - 61 + 1
            match_date = f"{season}-{month:02d}-{day:02d}"
            toss_winner = int(rng.choice([t1, t2]))
            toss_decision = str(rng.choice(["bat", "field"], p=[0.35, 0.65]))

            if toss_decision == "bat":
                bat1, bowl1 = toss_winner, (t2 if toss_winner == t1 else t1)
            else:
                bowl1 = toss_winner
                bat1 = t2 if toss_winner == t1 else t1

            xi1 = list(rng.choice(roster[bat1], size=11, replace=False))
            xi2 = list(rng.choice(roster[bowl1], size=11, replace=False))
            # bowlers: last 6 of XI
            bowl_attack = xi2[5:]
            bat_order = sorted(xi1, key=lambda p: -player_bat[p])

            d1, s1, w1, o1, e1 = _simulate_innings(
                rng, bat_order, bowl_attack,
                batting_strength=team_strength[bat1],
                bowling_strength=team_strength[bowl1],
            )
            # chase
            bat_order2 = sorted(xi2, key=lambda p: -player_bat[p])
            bowl_attack2 = xi1[5:]
            d2, s2, w2, o2, e2 = _simulate_innings(
                rng, bat_order2, bowl_attack2,
                batting_strength=team_strength[bowl1],
                bowling_strength=team_strength[bat1],
                target=s1 + 1,
            )

            if s2 > s1:
                winner = bowl1
                win_by_runs = 0
                win_by_wickets = 10 - w2
                result = "chased"
            elif s2 < s1:
                winner = bat1
                win_by_runs = s1 - s2
                win_by_wickets = 0
                result = "defended"
            else:
                winner = None
                win_by_runs = 0
                win_by_wickets = 0
                result = "tie"

            # player of match: top batter or bowler heuristic
            batter_runs: dict[int, int] = {}
            for d in d1 + d2:
                batter_runs[d["striker_id"]] = batter_runs.get(d["striker_id"], 0) + d["runs_batter"]
            pom = max(batter_runs, key=batter_runs.get) if batter_runs else xi1[0]

            match_rows.append(
                {
                    "match_id": match_id,
                    "season": season,
                    "match_date": match_date,
                    "venue_id": venue_id,
                    "team1_id": t1,
                    "team2_id": t2,
                    "toss_winner_id": toss_winner,
                    "toss_decision": toss_decision,
                    "winner_id": winner,
                    "win_by_runs": win_by_runs,
                    "win_by_wickets": max(0, win_by_wickets),
                    "player_of_match_id": pom,
                    "result": result,
                    "overs_limit": 20.0,
                }
            )

            for innings_number, (dlist, score, wkts, overs, extras, bt, bl) in enumerate(
                [
                    (d1, s1, w1, o1, e1, bat1, bowl1),
                    (d2, s2, w2, o2, e2, bowl1, bat1),
                ],
                start=1,
            ):
                innings_rows.append(
                    {
                        "innings_id": innings_id,
                        "match_id": match_id,
                        "innings_number": innings_number,
                        "batting_team_id": bt,
                        "bowling_team_id": bl,
                        "total_runs": score,
                        "total_wickets": wkts,
                        "total_overs": overs,
                        "extras": extras,
                    }
                )
                for d in dlist:
                    delivery_rows.append(
                        {
                            "delivery_id": delivery_id,
                            "match_id": match_id,
                            "innings_id": innings_id,
                            "innings_number": innings_number,
                            "batting_team_id": bt,
                            "bowling_team_id": bl,
                            **d,
                        }
                    )
                    delivery_id += 1
                innings_id += 1

            match_id += 1

    matches = pd.DataFrame(match_rows)
    innings = pd.DataFrame(innings_rows)
    deliveries = pd.DataFrame(delivery_rows)

    # Auto-scale only when caller wants the portfolio-size target
    if min_balls and len(deliveries) < min_balls and matches_per_season < 100:
        return generate_synthetic_ipl(
            seasons=seasons,
            matches_per_season=min(100, matches_per_season + 25),
            seed=seed,
            output_dir=output_dir,
            min_balls=min_balls,
        )

    tables = {
        "teams": teams,
        "venues": venues,
        "players": players,
        "matches": matches,
        "innings": innings,
        "deliveries": deliveries,
    }

    for name, df in tables.items():
        df.to_parquet(output_dir / f"{name}.parquet", index=False)
        df.to_csv(output_dir / f"{name}.csv", index=False)

    meta = pd.DataFrame(
        [{
            "source": "synthetic",
            "seasons": f"{min(seasons)}-{max(seasons)}",
            "matches": len(matches),
            "deliveries": len(deliveries),
            "players": len(players),
        }]
    )
    meta.to_csv(output_dir / "dataset_meta.csv", index=False)
    return tables


if __name__ == "__main__":
    data = generate_synthetic_ipl()
    print({k: len(v) for k, v in data.items()})
