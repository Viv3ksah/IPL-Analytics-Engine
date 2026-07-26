# Power BI Guide — IPL Analytics Engine

This project exports a star-schema model you can open directly in Power BI Desktop.

## 1. Generate export files

```bash
python scripts/run_etl.py
python scripts/export_powerbi.py
```

Artifacts land in `data/exports/`:

| File | Role |
|------|------|
| `ipl_powerbi_model.xlsx` | Dimension + aggregate tables (fast start) |
| `dim_*.csv` / `fact_*.csv` | Full CSV star schema |
| `fact_deliveries.parquet` | Ball-by-ball fact (large) |
| `powerbi_relationships.txt` | Relationship map |

## 2. Connect in Power BI Desktop

**Option A — Excel (quickest)**  
Home → Get data → Excel workbook → `ipl_powerbi_model.xlsx` → select all sheets → Load.

**Option B — Folder of CSVs**  
Get data → Folder → `data/exports` → Combine / load individual CSVs.

**Option C — SQLite (live)**  
Use a SQLite ODBC/connector to `db/ipl_analytics.db` and import views `v_*`.

## 3. Model relationships

Create these relationships (single direction, many-to-one):

- `dim_teams[team_id]` → `fact_matches[team1_id]`
- `dim_teams[team_id]` → `fact_matches[team2_id]` (role-playing: duplicate dim or inactive)
- `dim_venues[venue_id]` → `fact_matches[venue_id]`
- `dim_players[player_id]` → `fact_matches[player_of_match_id]`
- `fact_matches[match_id]` → `fact_innings[match_id]`
- `fact_matches[match_id]` → `fact_deliveries[match_id]`

For role-playing team dimensions in Power BI, duplicate `dim_teams` as `dim_team1`, `dim_team2`, `dim_winner`.

## 4. Suggested report pages

1. **Season Pulse** — slicer on season; cards for matches/runs/wickets; bar of win %.
2. **Player Bat & Bowl** — scatter SR vs runs; wickets vs economy.
3. **Venue Lab** — map or bar of avg first-innings; chase win %.
4. **Toss Lab** — bat vs field conversion by venue.
5. **Match Explorer** — matrix from `v_match_summary`.

## 5. Example DAX

```dax
Win % =
DIVIDE(
    CALCULATE(COUNTROWS(fact_matches), fact_matches[winner_id] = SELECTEDVALUE(dim_teams[team_id])),
    COUNTROWS(fact_matches)
)

Boundary % =
DIVIDE(
    SUMX(fact_deliveries, fact_deliveries[is_boundary] + fact_deliveries[is_six]),
    COUNTROWS(fact_deliveries)
)
```

## 6. Refresh workflow

Re-run ETL + export after new seasons, then refresh the Power BI dataset.
