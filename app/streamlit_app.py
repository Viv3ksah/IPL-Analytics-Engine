#!/usr/bin/env python3
"""IPL Analytics Engine — interactive Streamlit dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.styles import inject
from config.settings import DB_PATH, MODELS_DIR
from src.analytics.caps_race import (
    all_season_cap_winners,
    cap_standings,
    orange_cap_race,
    phase_specialists,
    purple_cap_race,
)
from src.analytics.comparison import compare_players, radar_frame
from src.analytics.dream_team import build_dream_team, player_fantasy_pool
from src.analytics.player_analytics import (
    batting_leaderboard,
    bowling_leaderboard,
    head_to_head_batter_vs_bowler,
    list_players,
    player_form_index,
    player_phase_profile,
)
from src.analytics.player_photos import render_cap_gallery
from src.analytics.team_players import (
    adjust_win_probability,
    player_impact_score,
    previous_season,
    team_batters_last_season,
    team_bowlers_last_season,
)
from src.analytics.team_analytics import (
    chase_defend_profile,
    list_teams,
    match_summary,
    season_run_rate_trends,
    team_h2h_summary,
    team_head_to_head,
    team_season_table,
)
from src.analytics.venue_analytics import list_venues, toss_venue_impact, venue_difficulty_index
from src.ml.match_outcome import predict_chase_win_prob, predict_match_outcome
from src.ml.match_simulator import ChaseState, simulate_chase
from src.ml.score_prediction import predict_final_score
from src.utils.db import read_sql, row_count, table_exists

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Source Sans 3, sans-serif", color="#10241c"),
    margin=dict(l=40, r=20, t=50, b=40),
)
COLORWAY = ["#0f3d2e", "#1f7a4d", "#c6f135", "#d9782d", "#245b4a", "#8fbf5a"]


@st.cache_resource(show_spinner=False)
def _bootstrap_if_needed() -> bool:
    """Build warehouse + models once per server process when missing (cloud deploy)."""
    models_ok = (MODELS_DIR / "match_outcome.joblib").exists()
    if DB_PATH.exists() and table_exists("deliveries") and models_ok:
        return True

    import importlib.util

    boot_path = ROOT / "scripts" / "bootstrap_deploy.py"
    spec = importlib.util.spec_from_file_location("bootstrap_deploy", boot_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load bootstrap script: {boot_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.bootstrap(force=False)
    return DB_PATH.exists() and table_exists("deliveries")


def _require_warehouse() -> bool:
    try:
        with st.spinner("Preparing analytics warehouse & models (first run only)…"):
            ok = _bootstrap_if_needed()
    except Exception as exc:
        st.error(
            "Could not prepare data automatically. "
            "Run `python scripts/bootstrap_deploy.py` or `python scripts/run_all.py`.\n\n"
            f"Details: {exc}"
        )
        return False
    if not ok:
        st.error("Warehouse not found. Run `python scripts/run_all.py` first.")
        return False
    return True


def _seasons() -> list[int]:
    df = read_sql("SELECT DISTINCT season FROM matches ORDER BY season")
    return df["season"].astype(int).tolist()


def page_overview() -> None:
    balls = row_count("deliveries")
    matches = row_count("matches")
    players = row_count("players")
    seasons = _seasons()

    st.markdown(
        f"""
        <div class="hero">
          <h1>IPL ANALYTICS ENGINE</h1>
          <p>End-to-end cricket intelligence on {balls:,}+ ball-by-ball records —
          ETL pipelines, SQL warehouse, player & venue labs, and ML models for
          match outcome and score prediction.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="metric-strip">
          <div class="metric-chip"><span>Deliveries</span><strong>{balls:,}</strong></div>
          <div class="metric-chip"><span>Matches</span><strong>{matches:,}</strong></div>
          <div class="metric-chip"><span>Players</span><strong>{players:,}</strong></div>
          <div class="metric-chip"><span>Seasons</span><strong>{seasons[0]}–{seasons[-1]}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    season = st.selectbox("Season filter", ["All"] + seasons, index=len(seasons))
    season_val = None if season == "All" else int(season)

    standings = team_season_table(season_val)
    if season_val is None:
        # latest season snapshot
        latest = standings["season"].max()
        standings = standings[standings["season"] == latest]

    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.subheader("Points race")
        fig = px.bar(
            standings.sort_values("wins"),
            x="wins",
            y="team_name",
            orientation="h",
            color="win_pct",
            color_continuous_scale=["#0f3d2e", "#c6f135"],
            labels={"wins": "Wins", "team_name": "", "win_pct": "Win %"},
        )
        fig.update_layout(**PLOTLY_LAYOUT, colorway=COLORWAY, height=420)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Phase run rates over years")
        trends = season_run_rate_trends()
        fig2 = px.line(
            trends,
            x="season",
            y="run_rate",
            color="phase",
            markers=True,
            color_discrete_sequence=COLORWAY,
        )
        fig2.update_layout(**PLOTLY_LAYOUT, height=420)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Recent matches")
    st.dataframe(match_summary(season_val, limit=30), use_container_width=True, hide_index=True)


def page_players() -> None:
    st.header("Player Lab")
    seasons = _seasons()
    season = st.selectbox("Season", ["Career"] + seasons, index=len(seasons))
    season_val = None if season == "Career" else int(season)
    min_balls = st.slider("Minimum balls", 30, 200, 60, 10)

    tab1, tab2, tab3, tab4 = st.tabs(["Batting", "Bowling", "Form Index", "Matchup"])
    with tab1:
        bat = batting_leaderboard(season_val, min_balls=min_balls, limit=40)
        fig = px.scatter(
            bat,
            x="strike_rate",
            y="runs",
            size="balls",
            hover_name="player_name",
            color="sixes",
            color_continuous_scale=["#0f3d2e", "#d9782d"],
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=480)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(bat, use_container_width=True, hide_index=True)

    with tab2:
        bowl = bowling_leaderboard(season_val, min_balls=min_balls, limit=40)
        fig = px.scatter(
            bowl,
            x="economy",
            y="wickets",
            size="balls",
            hover_name="player_name",
            color="average",
            color_continuous_scale=["#c6f135", "#0f3d2e"],
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=480)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(bowl, use_container_width=True, hide_index=True)

    with tab3:
        players = list_players(800)["player_name"].tolist()
        default = players[0] if players else ""
        # prefer a known-looking name if present
        for candidate in players:
            if " " in candidate:
                default = candidate
                break
        player = st.selectbox("Player", players, index=players.index(default) if default in players else 0)
        form = player_form_index(player, last_n_matches=10)
        phase = player_phase_profile(player, season_val)
        if form.empty:
            st.info("No batting innings for this player.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=form["match_date"], y=form["form_index"],
                mode="lines+markers", name="Form", line=dict(color="#1f7a4d", width=3),
            ))
            fig.add_trace(go.Scatter(
                x=form["match_date"], y=form["rolling_form"],
                mode="lines", name="Rolling form", line=dict(color="#d9782d", width=2, dash="dot"),
            ))
            fig.update_layout(**PLOTLY_LAYOUT, height=360, title=f"{player} — form index")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(form, use_container_width=True, hide_index=True)
        if not phase.empty:
            figp = px.bar(phase, x="phase", y="strike_rate", color="runs", color_continuous_scale=["#0f3d2e", "#c6f135"])
            figp.update_layout(**PLOTLY_LAYOUT, height=320, title="Phase strike rates")
            st.plotly_chart(figp, use_container_width=True)

    with tab4:
        players = list_players(800)["player_name"].tolist()
        c1, c2 = st.columns(2)
        batter = c1.selectbox("Batter", players, key="h2h_bat")
        bowler = c2.selectbox("Bowler", players, key="h2h_bowl")
        h2h = head_to_head_batter_vs_bowler(batter, bowler)
        st.dataframe(h2h, use_container_width=True, hide_index=True)


def page_venues() -> None:
    st.header("Venue Lab")
    seasons = _seasons()
    season = st.selectbox("Season", ["All"] + seasons, index=0, key="venue_season")
    season_val = None if season == "All" else int(season)
    idx = venue_difficulty_index(season_val)
    st.subheader("Batting friendliness index (100 = league average)")
    fig = px.bar(
        idx.sort_values("batting_index"),
        x="batting_index",
        y="venue_name",
        orientation="h",
        color="chase_friendliness",
        color_continuous_scale=["#0f3d2e", "#d9782d"],
        hover_data=["avg_first_innings", "matches", "city"],
    )
    fig.update_layout(**PLOTLY_LAYOUT, height=520)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(idx, use_container_width=True, hide_index=True)

    st.subheader("Toss conversion by venue")
    venues = ["All"] + list_venues()["venue_name"].tolist()
    venue = st.selectbox("Venue", venues)
    toss = toss_venue_impact(None if venue == "All" else venue)
    fig2 = px.bar(
        toss,
        x="venue_name",
        y="toss_win_convert_pct",
        color="toss_decision",
        barmode="group",
        color_discrete_sequence=COLORWAY,
    )
    fig2.update_layout(**PLOTLY_LAYOUT, height=400, xaxis_tickangle=-35)
    st.plotly_chart(fig2, use_container_width=True)


def page_teams() -> None:
    st.header("Team & Head-to-Head")
    # Prefer teams that actually appear in matches for meaningful H2H
    active = read_sql(
        """
        SELECT DISTINCT t.team_name
        FROM teams t
        JOIN matches m ON t.team_id IN (m.team1_id, m.team2_id)
        ORDER BY t.team_name
        """
    )["team_name"].tolist()
    teams = active or list_teams()["team_name"].tolist()
    seasons = _seasons()
    season = st.selectbox("Season", ["All"] + seasons, index=len(seasons), key="team_season")
    season_val = None if season == "All" else int(season)

    st.subheader("Chase vs defend")
    cdf = chase_defend_profile(season_val)
    fig = px.bar(
        cdf,
        x="team_name",
        y="win_pct",
        color="role",
        barmode="group",
        color_discrete_sequence=["#0f3d2e", "#d9782d"],
    )
    fig.update_layout(**PLOTLY_LAYOUT, height=420, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Head-to-head")
    c1, c2 = st.columns(2)
    a = c1.selectbox("Team A", teams, index=0)
    b_options = [t for t in teams if t != a] or teams
    b = c2.selectbox("Team B", b_options, index=0)
    if a == b:
        st.warning("Pick two different teams.")
        return
    summary = team_h2h_summary(a, b)
    m1, m2, m3 = st.columns(3)
    m1.metric("Meetings", summary["matches"])
    m2.metric(f"{a} wins", summary[a])
    m3.metric(f"{b} wins", summary[b])
    st.dataframe(team_head_to_head(a, b), use_container_width=True, hide_index=True)


def page_predictions() -> None:
    st.header("ML Predictions")
    st.caption("Models: Gradient Boosting / Random Forest trained on warehouse features.")

    has_models = (MODELS_DIR / "match_outcome.joblib").exists()
    if not has_models:
        st.warning("Models not trained yet. Run `python scripts/train_models.py`.")
        return

    with open(MODELS_DIR / "match_outcome_metrics.json") as f:
        m_out = json.load(f)
    with open(MODELS_DIR / "score_prediction_metrics.json") as f:
        m_score = json.load(f)
    with open(MODELS_DIR / "win_probability_metrics.json") as f:
        m_wp = json.load(f)

    c1, c2, c3 = st.columns(3)
    c1.metric("Outcome ROC-AUC", f"{m_out['roc_auc']:.3f}")
    sel = m_score["selected"]
    c2.metric("Score MAE", f"{m_score[sel]['mae']:.2f}")
    c3.metric("Win-prob ROC-AUC", f"{m_wp['roc_auc']:.3f}")

    tab1, tab2, tab3 = st.tabs(["Match outcome", "Score projection", "Live win probability"])

    teams = list_teams()
    venues = list_venues()
    seasons = _seasons()

    with tab1:
        active_teams = read_sql(
            """
            SELECT DISTINCT t.team_id, t.team_name
            FROM teams t
            JOIN matches m ON t.team_id IN (m.team1_id, m.team2_id)
            ORDER BY t.team_name
            """
        )
        team_names = active_teams["team_name"].tolist() or teams["team_name"].tolist()
        c1, c2 = st.columns(2)
        t1 = c1.selectbox("Team 1", team_names, key="pred_t1")
        t2_options = [t for t in team_names if t != t1] or team_names
        t2 = c2.selectbox("Team 2", t2_options, key="pred_t2")
        venue = st.selectbox("Venue", venues["venue_name"], key="pred_venue")
        season = st.selectbox("Season context", seasons, index=len(seasons) - 1, key="pred_season")
        toss = st.radio("Toss winner", ["Team 1", "Team 2"], horizontal=True)
        decision = st.radio("Toss decision", ["field", "bat"], horizontal=True)

        prev = previous_season(int(season))
        st.markdown("#### Key players (last season form)")
        if prev is None:
            st.info("No previous season available — prediction uses team/venue features only.")
            t1_bat = t1_bowl = t2_bat = t2_bowl = pd.DataFrame()
            pick_t1 = pick_t2 = []
        else:
            st.caption(f"Select impact players using **{prev}** performance for each side.")
            t1_bat = team_batters_last_season(t1, int(season))
            t1_bowl = team_bowlers_last_season(t1, int(season))
            t2_bat = team_batters_last_season(t2, int(season))
            t2_bowl = team_bowlers_last_season(t2, int(season))

            t1_opts = sorted(set(t1_bat["player_name"].tolist() + t1_bowl["player_name"].tolist()))
            t2_opts = sorted(set(t2_bat["player_name"].tolist() + t2_bowl["player_name"].tolist()))

            pc1, pc2 = st.columns(2)
            with pc1:
                default_t1 = t1_opts[:3]
                pick_t1 = st.multiselect(
                    f"{t1} players",
                    t1_opts,
                    default=default_t1,
                    max_selections=5,
                    key="pred_players_t1",
                )
                if not t1_bat.empty:
                    st.dataframe(
                        t1_bat[t1_bat["player_name"].isin(pick_t1)][
                            ["player_name", "runs", "strike_rate", "sixes"]
                        ]
                        if pick_t1
                        else t1_bat.head(5)[["player_name", "runs", "strike_rate", "sixes"]],
                        use_container_width=True,
                        hide_index=True,
                    )
            with pc2:
                default_t2 = t2_opts[:3]
                pick_t2 = st.multiselect(
                    f"{t2} players",
                    t2_opts,
                    default=default_t2,
                    max_selections=5,
                    key="pred_players_t2",
                )
                if not t2_bat.empty:
                    st.dataframe(
                        t2_bat[t2_bat["player_name"].isin(pick_t2)][
                            ["player_name", "runs", "strike_rate", "sixes"]
                        ]
                        if pick_t2
                        else t2_bat.head(5)[["player_name", "runs", "strike_rate", "sixes"]],
                        use_container_width=True,
                        hide_index=True,
                    )

        id_map = dict(zip(active_teams["team_name"], active_teams["team_id"])) if not active_teams.empty else dict(zip(teams["team_name"], teams["team_id"]))
        t1_id = int(id_map[t1])
        t2_id = int(id_map[t2])
        v_id = int(venues.loc[venues["venue_name"] == venue, "venue_id"].iloc[0])

        rates = read_sql(
            """
            SELECT team_id, AVG(win) AS win_rate FROM (
              SELECT team1_id AS team_id, CASE WHEN winner_id=team1_id THEN 1.0 ELSE 0.0 END AS win FROM matches WHERE winner_id IS NOT NULL
              UNION ALL
              SELECT team2_id AS team_id, CASE WHEN winner_id=team2_id THEN 1.0 ELSE 0.0 END AS win FROM matches WHERE winner_id IS NOT NULL
            ) GROUP BY team_id
            """
        )
        rate_map = dict(zip(rates["team_id"], rates["win_rate"]))
        vavg = read_sql(
            "SELECT AVG(i.total_runs) AS a FROM innings i JOIN matches m ON m.match_id=i.match_id WHERE i.innings_number=1 AND m.venue_id=:v",
            {"v": v_id},
        )
        venue_avg = float(vavg.iloc[0]["a"] or 165)

        features = {
            "venue_id": v_id,
            "team1_id": t1_id,
            "team2_id": t2_id,
            "team1_won_toss": 1 if toss == "Team 1" else 0,
            "chose_bat": 1 if decision == "bat" else 0,
            "team1_win_rate": float(rate_map.get(t1_id, 0.5)),
            "team2_win_rate": float(rate_map.get(t2_id, 0.5)),
            "win_rate_diff": float(rate_map.get(t1_id, 0.5) - rate_map.get(t2_id, 0.5)),
            "venue_avg_score": venue_avg,
            "season": int(season),
        }
        if st.button("Predict winner", type="primary"):
            base = predict_match_outcome(features)
            impact1 = player_impact_score(t1_bat, t1_bowl, pick_t1)
            impact2 = player_impact_score(t2_bat, t2_bowl, pick_t2)
            out = adjust_win_probability(base["team1_win_probability"], impact1, impact2)

            fig = go.Figure(
                data=[
                    go.Bar(
                        name="Base model",
                        x=[t1, t2],
                        y=[
                            out["base_team1_win_probability"] * 100,
                            (1 - out["base_team1_win_probability"]) * 100,
                        ],
                        marker_color=["#8fbf5a", "#e0a36b"],
                    ),
                    go.Bar(
                        name="With selected players",
                        x=[t1, t2],
                        y=[out["team1_win_probability"] * 100, out["team2_win_probability"] * 100],
                        marker_color=["#0f3d2e", "#d9782d"],
                    ),
                ]
            )
            fig.update_layout(
                **PLOTLY_LAYOUT,
                barmode="group",
                yaxis_title="Win probability %",
                height=380,
                title="Win prediction — team model + last-season player form",
            )
            st.plotly_chart(fig, use_container_width=True)

            m1, m2, m3 = st.columns(3)
            m1.metric(f"{t1} win %", f"{out['team1_win_probability']*100:.1f}%")
            m2.metric(f"{t2} win %", f"{out['team2_win_probability']*100:.1f}%")
            m3.metric("Player impact Δ", f"{out['impact_delta']*100:+.1f} pts")
            if pick_t1 or pick_t2:
                st.caption(
                    f"Selected — {t1}: {', '.join(pick_t1) or 'none'} · "
                    f"{t2}: {', '.join(pick_t2) or 'none'}"
                )

    with tab2:
        st.write("Project final first-innings score from a live checkpoint.")
        over = st.slider("Overs completed", 5, 16, 10)
        cum_runs = st.number_input("Runs so far", 20, 250, 78)
        cum_wickets = st.slider("Wickets down", 0, 9, 2)
        venue_id = int(venues.loc[venues["venue_name"] == st.selectbox("Venue ", venues["venue_name"], key="score_v"), "venue_id"].iloc[0])
        season = st.selectbox("Season ", seasons, index=len(seasons) - 1, key="score_s")
        balls = over * 6
        state = {
            "over_number": over,
            "cum_runs": cum_runs,
            "cum_wickets": cum_wickets,
            "balls_faced": balls,
            "current_rr": cum_runs / max(over, 1),
            "wickets_in_hand": 10 - cum_wickets,
            "overs_left": 20 - over,
            "proj_naive": (cum_runs / max(over, 1)) * 20,
            "venue_id": venue_id,
            "season": int(season),
        }
        if st.button("Project score", type="primary"):
            pred = predict_final_score(state)
            st.metric("Predicted final score", f"{pred:.0f}")
            fig = go.Figure()
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=pred,
                gauge={
                    "axis": {"range": [80, 260]},
                    "bar": {"color": "#1f7a4d"},
                    "steps": [
                        {"range": [80, 140], "color": "#dfe8d8"},
                        {"range": [140, 180], "color": "#c6f135"},
                        {"range": [180, 260], "color": "#d9782d"},
                    ],
                },
            ))
            fig.update_layout(**PLOTLY_LAYOUT, height=300)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.write("Upgrade: chase win probability from match state.")
        target = st.number_input("Target", 100, 280, 180)
        overs_done = st.slider("Overs bowled in chase", 1, 19, 12, key="wp_over")
        runs = st.number_input("Runs scored", 0, 280, 110, key="wp_runs")
        wickets = st.slider("Wickets lost", 0, 9, 3, key="wp_w")
        balls_faced = overs_done * 6
        runs_needed = max(target - runs, 0)
        balls_left = max(120 - balls_faced, 0)
        req_rr = (runs_needed / (balls_left / 6.0)) if balls_left else 99.0
        state = {
            "runs_needed": runs_needed,
            "balls_left": balls_left,
            "wickets_left": 10 - wickets,
            "required_rr": req_rr,
            "cum_runs": runs,
            "over_number": overs_done,
        }
        if st.button("Compute win probability", type="primary"):
            p = predict_chase_win_prob(state)
            # simple curve around current state
            xs = list(range(max(1, overs_done - 5), min(20, overs_done + 6)))
            ys = []
            for o in xs:
                bf = o * 6
                bl = max(120 - bf, 0)
                # assume linear scoring continuation
                proj_runs = runs + (runs / max(overs_done, 1)) * (o - overs_done)
                rn = max(target - proj_runs, 0)
                rr = (rn / (bl / 6.0)) if bl else 99
                ys.append(
                    predict_chase_win_prob(
                        {
                            "runs_needed": rn,
                            "balls_left": bl,
                            "wickets_left": 10 - wickets,
                            "required_rr": rr,
                            "cum_runs": proj_runs,
                            "over_number": o,
                        }
                    )
                    * 100
                )
            st.metric("Chasing side win probability", f"{p*100:.1f}%")
            fig = px.line(x=xs, y=ys, markers=True, labels={"x": "Over", "y": "Win %"})
            fig.update_traces(line_color="#0f3d2e")
            fig.update_layout(**PLOTLY_LAYOUT, height=360)
            st.plotly_chart(fig, use_container_width=True)


def page_sql() -> None:
    st.header("SQL Workbench")
    st.caption("Read-only queries against the analytics warehouse.")
    default = "SELECT * FROM v_match_summary ORDER BY match_date DESC LIMIT 25"
    query = st.text_area("SQL", value=default, height=140)
    if st.button("Run query"):
        banned = ["insert", "update", "delete", "drop", "alter", "attach", "pragma"]
        low = query.lower()
        if any(b in low for b in banned):
            st.error("Only SELECT queries are allowed.")
            return
        try:
            df = read_sql(query)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("Download CSV", df.to_csv(index=False), "query.csv", "text/csv")
        except Exception as exc:
            st.error(f"Query failed: {exc}")


def page_caps() -> None:
    st.header("Caps Race & Specialists")
    seasons = _seasons()
    season = st.selectbox("Season", seasons, index=len(seasons) - 1, key="caps_season")
    tab0, tab1, tab2, tab3 = st.tabs(
        ["Hall of Fame photos", "Orange Cap race", "Purple Cap race", "Phase specialists"]
    )

    with tab0:
        st.subheader("Orange Cap & Purple Cap winners — all seasons")
        st.caption("Portrait cards with cap badges for every season champion.")
        orange_w, purple_w = all_season_cap_winners()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Orange Cap")
            rows = [
                {
                    "season": int(r.season),
                    "player_name": r.player_name,
                    "metric_label": "Runs",
                    "metric_value": int(r.runs),
                    "secondary": f"SR {r.strike_rate} · {int(r.sixes)} sixes",
                }
                for r in orange_w.itertuples(index=False)
            ]
            st.markdown(render_cap_gallery(rows, accent="orange", cols=1), unsafe_allow_html=True)
        with c2:
            st.markdown("#### Purple Cap")
            rows = [
                {
                    "season": int(r.season),
                    "player_name": r.player_name,
                    "metric_label": "Wickets",
                    "metric_value": int(r.wickets),
                    "secondary": f"Econ {r.economy}",
                }
                for r in purple_w.itertuples(index=False)
            ]
            st.markdown(render_cap_gallery(rows, accent="purple", cols=1), unsafe_allow_html=True)
        with st.expander("Full winners table"):
            left, right = st.columns(2)
            left.dataframe(orange_w, use_container_width=True, hide_index=True)
            right.dataframe(purple_w, use_container_width=True, hide_index=True)

    with tab1:
        race = orange_cap_race(int(season), top_n=8)
        standings, _ = cap_standings(int(season))
        if race.empty:
            st.info("No batting data for this season.")
        else:
            if not standings.empty:
                leader = standings.iloc[0]
                st.markdown(
                    render_cap_gallery(
                        [{
                            "season": int(season),
                            "player_name": leader["player_name"],
                            "metric_label": "Runs",
                            "metric_value": int(leader["runs"]),
                            "secondary": f"SR {leader['strike_rate']}",
                        }],
                        accent="orange",
                        cols=1,
                    ),
                    unsafe_allow_html=True,
                )
            fig = px.line(
                race,
                x="match_date",
                y="cum_runs",
                color="player_name",
                markers=True,
                color_discrete_sequence=COLORWAY,
                labels={"cum_runs": "Cumulative runs", "match_date": "Date"},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=420, title=f"Orange Cap race — {season}")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(standings, use_container_width=True, hide_index=True)

    with tab2:
        race = purple_cap_race(int(season), top_n=8)
        _, standings = cap_standings(int(season))
        if race.empty:
            st.info("No bowling data for this season.")
        else:
            if not standings.empty:
                leader = standings.iloc[0]
                st.markdown(
                    render_cap_gallery(
                        [{
                            "season": int(season),
                            "player_name": leader["player_name"],
                            "metric_label": "Wickets",
                            "metric_value": int(leader["wickets"]),
                            "secondary": f"Econ {leader['economy']}",
                        }],
                        accent="purple",
                        cols=1,
                    ),
                    unsafe_allow_html=True,
                )
            fig = px.line(
                race,
                x="match_date",
                y="cum_wickets",
                color="player_name",
                markers=True,
                color_discrete_sequence=COLORWAY,
                labels={"cum_wickets": "Cumulative wickets", "match_date": "Date"},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=420, title=f"Purple Cap race — {season}")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(standings, use_container_width=True, hide_index=True)

    with tab3:
        specs = phase_specialists(int(season), min_balls=30)
        phase = st.selectbox("Phase", ["powerplay", "middle", "death"], key="spec_phase")
        c1, c2 = st.columns(2)
        bat = specs["batting"]
        bowl = specs["bowling"]
        with c1:
            st.subheader("Top strike rates")
            show = bat[bat["phase"] == phase].head(12)
            fig = px.bar(
                show.sort_values("strike_rate"),
                x="strike_rate",
                y="player_name",
                orientation="h",
                color="sixes",
                color_continuous_scale=["#0f3d2e", "#d9782d"],
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=420)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Best economies")
            showb = bowl[bowl["phase"] == phase].head(12)
            fig = px.bar(
                showb.sort_values("economy", ascending=False),
                x="economy",
                y="player_name",
                orientation="h",
                color="wickets",
                color_continuous_scale=["#c6f135", "#0f3d2e"],
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=420)
            st.plotly_chart(fig, use_container_width=True)


def page_compare_dream() -> None:
    st.header("Compare Players & Dream Team")
    seasons = _seasons()
    season = st.selectbox("Season", seasons, index=len(seasons) - 1, key="cmp_season")
    players = list_players(800)["player_name"].tolist()

    tab1, tab2 = st.tabs(["Player comparison", "Dream Team XI"])
    with tab1:
        picks = st.multiselect(
            "Pick 2–4 players",
            players,
            default=players[:3] if len(players) >= 3 else players,
            max_selections=4,
        )
        if len(picks) < 2:
            st.warning("Select at least two players.")
        else:
            raw = compare_players(picks, int(season))
            rad = radar_frame(raw)
            categories = ["runs", "strike_rate", "average", "sixes", "wickets", "economy"]
            fig = go.Figure()
            for _, row in rad.iterrows():
                fig.add_trace(
                    go.Scatterpolar(
                        r=[row[c] for c in categories] + [row[categories[0]]],
                        theta=categories + [categories[0]],
                        fill="toself",
                        name=row["player_name"],
                    )
                )
            fig.update_layout(
                **PLOTLY_LAYOUT,
                height=480,
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title="Normalized skill radar (0–100)",
                colorway=COLORWAY,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(raw, use_container_width=True, hide_index=True)

    with tab2:
        st.caption("Auto-picks an XI from season fantasy points with role + credit constraints.")
        max_credits = st.slider("Max credits", 80.0, 120.0, 100.0, 1.0)
        if st.button("Build Dream Team", type="primary"):
            xi = build_dream_team(int(season), max_credits=max_credits)
            if xi.empty:
                st.warning("Could not build a valid XI for this season.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Total fantasy pts", f"{xi['total_pts'].sum():.0f}")
                c2.metric("Credits used", f"{xi['credit'].sum():.1f}")
                c3.metric("Players", len(xi))
                fig = px.bar(
                    xi.sort_values("total_pts"),
                    x="total_pts",
                    y="player_name",
                    color="role_inferred",
                    orientation="h",
                    color_discrete_sequence=COLORWAY,
                )
                fig.update_layout(**PLOTLY_LAYOUT, height=480, title="Dream Team contribution")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(xi, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download XI CSV",
                    xi.to_csv(index=False),
                    f"dream_team_{season}.csv",
                    "text/csv",
                )
        with st.expander("Browse fantasy pool"):
            pool = player_fantasy_pool(int(season)).head(40)
            st.dataframe(pool, use_container_width=True, hide_index=True)


def page_simulator() -> None:
    st.header("Match Chase Simulator")
    st.caption("Monte Carlo engine using empirical ball outcomes from the warehouse.")
    seasons = _seasons()
    season = st.selectbox("Calibration season", ["All"] + seasons, index=len(seasons), key="sim_season")
    season_val = None if season == "All" else int(season)

    c1, c2, c3, c4 = st.columns(4)
    target = c1.number_input("Target", 100, 280, 185)
    runs = c2.number_input("Runs scored", 0, 280, 95)
    wickets = c3.slider("Wickets lost", 0, 9, 3)
    overs = c4.number_input("Overs done (e.g. 11.2)", 0.0, 19.5, 11.2, 0.1)
    n_sims = st.slider("Simulations", 500, 5000, 2000, 500)

    if st.button("Run simulation", type="primary"):
        state = ChaseState(target=int(target), runs=int(runs), wickets=int(wickets), overs_done=float(overs))
        if state.balls_left <= 0:
            st.error("No balls left to simulate.")
            return
        result = simulate_chase(state, n_sims=n_sims, season=season_val)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Chase win %", f"{result['win_probability'] * 100:.1f}%")
        m2.metric("Median finish", f"{result['p50']:.0f}")
        m3.metric("Required RR", f"{result['required_rr']:.2f}" if result["required_rr"] else "—")
        m4.metric("Balls left", result["balls_left"])

        dist = result["distribution"].reset_index()
        dist.columns = ["final_score", "count"]
        fig = px.area(
            dist,
            x="final_score",
            y="count",
            labels={"final_score": "Projected final score", "count": "Simulations"},
        )
        fig.add_vline(x=target, line_dash="dash", line_color="#d9782d")
        fig.update_traces(line_color="#0f3d2e")
        fig.update_layout(**PLOTLY_LAYOUT, height=400, title="Score distribution vs target")
        st.plotly_chart(fig, use_container_width=True)

        # overlay ML win-prob for comparison
        try:
            ml_p = predict_chase_win_prob(
                {
                    "runs_needed": result["runs_needed"],
                    "balls_left": result["balls_left"],
                    "wickets_left": 10 - wickets,
                    "required_rr": result["required_rr"] or 99,
                    "cum_runs": runs,
                    "over_number": int(overs),
                }
            )
            st.info(
                f"Model comparison — Monte Carlo: {result['win_probability']*100:.1f}% · "
                f"ML win-prob model: {ml_p*100:.1f}%"
            )
        except Exception:
            pass


def main() -> None:
    st.set_page_config(
        page_title="IPL Analytics Engine",
        page_icon="I",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject(st)
    st.sidebar.markdown("## IPL Analytics")
    st.sidebar.caption("Python · SQL · Pandas · Scikit-learn · Streamlit · Power BI")
    page = st.sidebar.radio(
        "Navigate",
        [
            "Overview",
            "Player Lab",
            "Venue Lab",
            "Teams & H2H",
            "Caps & Specialists",
            "Compare & Dream Team",
            "Match Simulator",
            "ML Predictions",
            "SQL Workbench",
        ],
    )
    if not _require_warehouse():
        st.stop()

    pages = {
        "Overview": page_overview,
        "Player Lab": page_players,
        "Venue Lab": page_venues,
        "Teams & H2H": page_teams,
        "Caps & Specialists": page_caps,
        "Compare & Dream Team": page_compare_dream,
        "Match Simulator": page_simulator,
        "ML Predictions": page_predictions,
        "SQL Workbench": page_sql,
    }
    pages[page]()


if __name__ == "__main__":
    main()
