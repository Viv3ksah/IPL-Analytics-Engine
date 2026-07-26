# IPL Analytics Engine

End-to-end cricket analytics platform built on **250K+ ball-by-ball records**, with ETL pipelines, a SQL analytics warehouse, interactive Streamlit dashboards, Power BI exports, and machine learning models for **match outcome** and **score prediction**.

**Stack:** Python · SQL · Pandas · Scikit-learn · Streamlit · Power BI · Plotly · XGBoost-ready sklearn ensembles

---

## Features

| Area | What you get |
|------|----------------|
| **ETL** | Cricsheet download (when available) or high-fidelity synthetic IPL generator → cleaned parquet/CSV → SQLite star schema |
| **SQL warehouse** | `teams`, `venues`, `players`, `matches`, `innings`, `deliveries` + analytics views |
| **Player lab** | Batting/bowling leaderboards, phase profiles, fantasy points, **form index**, batter-vs-bowler matchups |
| **Venue lab** | Scoring patterns, batting/bowling difficulty index, toss conversion |
| **Team lab** | Season standings, chase vs defend, head-to-head |
| **ML** | Match winner classifier, first-innings score regressor, **live chase win-probability** model |
| **Streamlit** | Multi-page interactive dashboard with Plotly visuals |
| **Caps & specialists** | Orange/Purple Cap race charts + phase strike-rate/economy leaders |
| **Compare & Dream Team** | Multi-player radar comparison + fantasy XI builder |
| **Match simulator** | Monte Carlo chase engine with ML win-prob comparison |
| **Power BI** | Star-schema CSV/XLSX exports + relationship guide |

### Upgrades beyond a basic portfolio build

1. **Live win-probability model** — chase state → P(win) with over-by-over curve  
2. **Player form index** — rolling momentum across recent innings  
3. **Batter vs bowler matchup explorer**  
4. **Venue batting/bowling indices** (league-normalized)  
5. **In-app SQL workbench** (read-only)  
6. **Fantasy point estimates** on leaderboards  
7. **One-command pipeline** (`scripts/run_all.py`)  
8. **Orange / Purple Cap race** charts + phase specialists  
9. **Player comparison radar** (2–4 players)  
10. **Dream Team XI builder** (role + credit constraints)  
11. **Monte Carlo chase simulator** (empirical ball model vs ML win-prob)  
12. **Cap Hall of Fame photo cards** for Orange/Purple Cap winners across all seasons  
13. **Player-aware win prediction** — pick key players using last-season form

---

## Quick start

```bash
# 1) Install
python -m pip install -r requirements.txt

# 2) Build data + models + Power BI exports
python scripts/run_all.py

# 3) Launch dashboard
streamlit run app/streamlit_app.py
```

## Deploy (Streamlit Cloud)

See **[DEPLOY.md](DEPLOY.md)** for full steps.

Short version:
1. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub  
2. **Create app** → repo `Viv3ksah/Projects`  
3. Branch: `cursor/ipl-analytics-engine-3a6e` (or `main` after merge)  
4. Main file: `app/streamlit_app.py` → **Deploy**  

First launch auto-builds the warehouse + models.

Individual steps:

```bash
python scripts/run_etl.py --source auto          # warehouse
python scripts/train_models.py                  # ML artifacts → data/models/
python scripts/export_powerbi.py                # data/exports/
pytest -q                                       # smoke tests
```

---

## Project layout

```
├── app/                    # Streamlit dashboard
├── config/settings.py      # paths, franchises, venues
├── db/schema.sql           # star schema + views
├── sql/analytics_queries.sql
├── powerbi/README.md       # Desktop modeling guide
├── scripts/
│   ├── run_etl.py
│   ├── train_models.py
│   ├── export_powerbi.py
│   └── run_all.py
├── src/
│   ├── etl/                # Cricsheet + synthetic + load
│   ├── analytics/          # player / venue / team
│   ├── ml/                 # features + models
│   └── utils/db.py
├── data/
│   ├── processed/          # parquet/csv snapshots
│   ├── models/             # joblib + metrics JSON
│   └── exports/            # Power BI feeds
└── tests/
```

---

## Data notes

- **`--source auto`** tries [Cricsheet](https://cricsheet.org/) IPL JSON first.  
- If the download is unavailable or under 250K balls, the **synthetic generator** builds a full multi-season T20 ball-by-ball corpus (matches, wickets, phases, toss, venues) sized for analytics/ML demos.  
- All downstream code consumes the same warehouse schema either way.

---

## Power BI

See [`powerbi/README.md`](powerbi/README.md). After export, open `data/exports/ipl_powerbi_model.xlsx` or connect CSVs using the relationship map in `powerbi_relationships.txt`.

---

## Example SQL

```sql
SELECT player_name, runs, strike_rate, sixes
FROM v_player_batting
WHERE season = 2024 AND balls_faced >= 60
ORDER BY runs DESC
LIMIT 10;
```

More recipes in `sql/analytics_queries.sql`.

---

## License / data credit

Synthetic mode is original to this repo. When using Cricsheet, respect their [terms](https://cricsheet.org/register/).
