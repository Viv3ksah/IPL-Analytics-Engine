"""Download and parse Cricsheet IPL JSON when network access is available."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from config.settings import (
    CRICSHEET_EXTRACT_DIR,
    CRICSHEET_IPL_URL,
    CRICSHEET_ZIP,
    PROCESSED_DIR,
    TEAM_ALIASES,
)


def normalize_team(name: str) -> str:
    key = (name or "").strip().lower()
    return TEAM_ALIASES.get(key, name.strip())


def download_cricsheet(url: str = CRICSHEET_IPL_URL, timeout: int = 60) -> Path:
    CRICSHEET_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(CRICSHEET_ZIP, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc="Downloading Cricsheet IPL"
        ) as bar:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))
    return CRICSHEET_ZIP


def extract_cricsheet(zip_path: Path = CRICSHEET_ZIP) -> Path:
    CRICSHEET_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(CRICSHEET_EXTRACT_DIR)
    return CRICSHEET_EXTRACT_DIR


def _phase(over: int) -> str:
    if over <= 6:
        return "powerplay"
    if over <= 15:
        return "middle"
    return "death"


def parse_cricsheet_json(extract_dir: Path = CRICSHEET_EXTRACT_DIR) -> dict[str, pd.DataFrame]:
    """Parse Cricsheet match JSON files into warehouse tables."""
    files = sorted(extract_dir.rglob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files under {extract_dir}")

    team_names: set[str] = set()
    venue_map: dict[str, str] = {}
    player_names: set[str] = set()

    match_rows = []
    innings_rows = []
    delivery_rows = []

    match_id = 1
    innings_id = 1
    delivery_id = 1

    for path in tqdm(files, desc="Parsing Cricsheet JSON"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        info = doc.get("info", {})
        if info.get("gender") not in (None, "male"):
            # keep men's IPL primarily
            pass
        teams = [normalize_team(t) for t in info.get("teams", [])]
        if len(teams) != 2:
            continue
        team_names.update(teams)

        venue = info.get("venue") or "Unknown"
        city = info.get("city") or ""
        venue_map[venue] = city

        dates = info.get("dates") or []
        match_date = dates[0] if dates else None
        season_raw = info.get("season")
        try:
            season = int(str(season_raw)[:4])
        except Exception:
            season = int(str(match_date)[:4]) if match_date else None

        toss = info.get("toss", {})
        toss_winner = normalize_team(toss.get("winner", "")) if toss.get("winner") else None
        toss_decision = toss.get("decision")
        outcome = info.get("outcome", {})
        winner = normalize_team(outcome.get("winner", "")) if outcome.get("winner") else None
        by = outcome.get("by") or {}
        win_by_runs = int(by.get("runs") or 0)
        win_by_wickets = int(by.get("wickets") or 0)
        pom_list = info.get("player_of_match") or []
        pom = pom_list[0] if pom_list else None
        if pom:
            player_names.add(pom)

        # registry players
        registry = (info.get("registry") or {}).get("people") or {}
        for pname in registry:
            player_names.add(pname)

        match_rows.append(
            {
                "match_id": match_id,
                "season": season,
                "match_date": match_date,
                "venue_name": venue,
                "city": city,
                "team1": teams[0],
                "team2": teams[1],
                "toss_winner": toss_winner,
                "toss_decision": toss_decision,
                "winner": winner,
                "win_by_runs": win_by_runs,
                "win_by_wickets": win_by_wickets,
                "player_of_match": pom,
                "result": "chased" if win_by_wickets else ("defended" if win_by_runs else outcome.get("result")),
                "overs_limit": float((info.get("overs") or 20)),
            }
        )

        for innings_number, inn in enumerate(doc.get("innings", []), start=1):
            batting_team = normalize_team(inn.get("team", ""))
            bowling_team = teams[0] if batting_team == teams[1] else teams[1]
            team_names.add(batting_team)
            team_names.add(bowling_team)
            total_runs = 0
            total_wickets = 0
            extras = 0
            balls = 0

            for over_block in inn.get("overs", []):
                over_no = int(over_block.get("over", 0)) + 1  # 1-based
                for ball_idx, delivery in enumerate(over_block.get("deliveries", []), start=1):
                    batter = delivery.get("batter")
                    non_striker = delivery.get("non_striker")
                    bowler = delivery.get("bowler")
                    for p in (batter, non_striker, bowler):
                        if p:
                            player_names.add(p)

                    runs = delivery.get("runs") or {}
                    runs_batter = int(runs.get("batter") or 0)
                    runs_extras = int(runs.get("extras") or 0)
                    runs_total = int(runs.get("total") or (runs_batter + runs_extras))
                    extras_obj = delivery.get("extras") or {}
                    extras_type = next(iter(extras_obj.keys()), None) if extras_obj else None
                    wickets = delivery.get("wickets") or []
                    is_wicket = 1 if wickets else 0
                    dismissal_kind = wickets[0].get("kind") if wickets else None
                    player_dismissed = wickets[0].get("player_out") if wickets else None
                    if player_dismissed:
                        player_names.add(player_dismissed)

                    total_runs += runs_total
                    extras += runs_extras
                    total_wickets += is_wicket
                    balls += 1

                    delivery_rows.append(
                        {
                            "delivery_id": delivery_id,
                            "match_id": match_id,
                            "innings_id": innings_id,
                            "innings_number": innings_number,
                            "over_number": over_no,
                            "ball_number": ball_idx,
                            "batting_team": batting_team,
                            "bowling_team": bowling_team,
                            "striker": batter,
                            "non_striker": non_striker,
                            "bowler": bowler,
                            "runs_batter": runs_batter,
                            "runs_extras": runs_extras,
                            "runs_total": runs_total,
                            "extras_type": extras_type,
                            "is_wicket": is_wicket,
                            "dismissal_kind": dismissal_kind,
                            "player_dismissed": player_dismissed,
                            "is_dot": int(runs_total == 0 and not is_wicket),
                            "is_boundary": int(runs_batter == 4),
                            "is_six": int(runs_batter == 6),
                            "phase": _phase(over_no),
                        }
                    )
                    delivery_id += 1

            total_overs = round(balls / 6.0, 1)
            innings_rows.append(
                {
                    "innings_id": innings_id,
                    "match_id": match_id,
                    "innings_number": innings_number,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "total_runs": total_runs,
                    "total_wickets": total_wickets,
                    "total_overs": total_overs,
                    "extras": extras,
                }
            )
            innings_id += 1

        match_id += 1

    teams = pd.DataFrame({"team_name": sorted(team_names)})
    teams["team_id"] = range(1, len(teams) + 1)
    teams["short_name"] = teams["team_name"].str[:3].str.upper()
    teams["city"] = None

    venues = pd.DataFrame(
        [{"venue_name": v, "city": c} for v, c in sorted(venue_map.items())]
    )
    venues["venue_id"] = range(1, len(venues) + 1)
    venues["country"] = "India"
    venues["capacity"] = None

    players = pd.DataFrame({"player_name": sorted(player_names)})
    players["player_id"] = range(1, len(players) + 1)
    players["batting_hand"] = None
    players["bowling_style"] = None
    players["role"] = None

    team_id = dict(zip(teams["team_name"], teams["team_id"]))
    venue_id = dict(zip(venues["venue_name"], venues["venue_id"]))
    player_id = dict(zip(players["player_name"], players["player_id"]))

    matches = pd.DataFrame(match_rows)
    matches["venue_id"] = matches["venue_name"].map(venue_id)
    matches["team1_id"] = matches["team1"].map(team_id)
    matches["team2_id"] = matches["team2"].map(team_id)
    matches["toss_winner_id"] = matches["toss_winner"].map(team_id)
    matches["winner_id"] = matches["winner"].map(team_id)
    matches["player_of_match_id"] = matches["player_of_match"].map(player_id)
    matches = matches[
        [
            "match_id", "season", "match_date", "venue_id", "team1_id", "team2_id",
            "toss_winner_id", "toss_decision", "winner_id", "win_by_runs",
            "win_by_wickets", "player_of_match_id", "result", "overs_limit",
        ]
    ]

    innings = pd.DataFrame(innings_rows)
    innings["batting_team_id"] = innings["batting_team"].map(team_id)
    innings["bowling_team_id"] = innings["bowling_team"].map(team_id)
    innings = innings[
        [
            "innings_id", "match_id", "innings_number", "batting_team_id",
            "bowling_team_id", "total_runs", "total_wickets", "total_overs", "extras",
        ]
    ]

    deliveries = pd.DataFrame(delivery_rows)
    deliveries["batting_team_id"] = deliveries["batting_team"].map(team_id)
    deliveries["bowling_team_id"] = deliveries["bowling_team"].map(team_id)
    deliveries["striker_id"] = deliveries["striker"].map(player_id)
    deliveries["non_striker_id"] = deliveries["non_striker"].map(player_id)
    deliveries["bowler_id"] = deliveries["bowler"].map(player_id)
    deliveries["player_dismissed_id"] = deliveries["player_dismissed"].map(player_id)
    deliveries = deliveries[
        [
            "delivery_id", "match_id", "innings_id", "innings_number", "over_number",
            "ball_number", "batting_team_id", "bowling_team_id", "striker_id",
            "non_striker_id", "bowler_id", "runs_batter", "runs_extras", "runs_total",
            "extras_type", "is_wicket", "dismissal_kind", "player_dismissed_id",
            "is_dot", "is_boundary", "is_six", "phase",
        ]
    ]

    tables = {
        "teams": teams[["team_id", "team_name", "short_name", "city"]],
        "venues": venues[["venue_id", "venue_name", "city", "country", "capacity"]],
        "players": players[["player_id", "player_name", "batting_hand", "bowling_style", "role"]],
        "matches": matches,
        "innings": innings,
        "deliveries": deliveries,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)

    meta = pd.DataFrame(
        [{
            "source": "cricsheet",
            "matches": len(matches),
            "deliveries": len(deliveries),
            "players": len(players),
        }]
    )
    meta.to_csv(PROCESSED_DIR / "dataset_meta.csv", index=False)
    return tables


def try_load_cricsheet() -> dict[str, pd.DataFrame] | None:
    try:
        if not CRICSHEET_ZIP.exists():
            download_cricsheet()
        if not any(CRICSHEET_EXTRACT_DIR.rglob("*.json")):
            extract_cricsheet()
        return parse_cricsheet_json()
    except Exception as exc:
        print(f"[cricsheet] unavailable ({exc}); will use synthetic data")
        return None
