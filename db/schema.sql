-- IPL Analytics Engine — star-schema warehouse (SQLite)
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS innings;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS venues;
DROP TABLE IF EXISTS teams;
DROP VIEW IF EXISTS v_match_summary;
DROP VIEW IF EXISTS v_player_batting;
DROP VIEW IF EXISTS v_player_bowling;
DROP VIEW IF EXISTS v_venue_stats;
DROP VIEW IF EXISTS v_team_season;

CREATE TABLE teams (
    team_id     INTEGER PRIMARY KEY,
    team_name   TEXT NOT NULL UNIQUE,
    short_name  TEXT,
    city        TEXT
);

CREATE TABLE venues (
    venue_id    INTEGER PRIMARY KEY,
    venue_name  TEXT NOT NULL UNIQUE,
    city        TEXT,
    country     TEXT DEFAULT 'India',
    capacity    INTEGER
);

CREATE TABLE players (
    player_id   INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL UNIQUE,
    batting_hand TEXT,
    bowling_style TEXT,
    role        TEXT
);

CREATE TABLE matches (
    match_id        INTEGER PRIMARY KEY,
    season          INTEGER NOT NULL,
    match_date      TEXT,
    venue_id        INTEGER REFERENCES venues(venue_id),
    team1_id        INTEGER REFERENCES teams(team_id),
    team2_id        INTEGER REFERENCES teams(team_id),
    toss_winner_id  INTEGER REFERENCES teams(team_id),
    toss_decision   TEXT,
    winner_id       INTEGER REFERENCES teams(team_id),
    win_by_runs     INTEGER DEFAULT 0,
    win_by_wickets  INTEGER DEFAULT 0,
    player_of_match_id INTEGER REFERENCES players(player_id),
    result          TEXT,
    overs_limit     REAL DEFAULT 20.0
);

CREATE TABLE innings (
    innings_id      INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    innings_number  INTEGER NOT NULL,
    batting_team_id INTEGER REFERENCES teams(team_id),
    bowling_team_id INTEGER REFERENCES teams(team_id),
    total_runs      INTEGER,
    total_wickets   INTEGER,
    total_overs     REAL,
    extras          INTEGER,
    UNIQUE(match_id, innings_number)
);

CREATE TABLE deliveries (
    delivery_id     INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    innings_id      INTEGER NOT NULL REFERENCES innings(innings_id),
    innings_number  INTEGER NOT NULL,
    over_number     INTEGER NOT NULL,
    ball_number     INTEGER NOT NULL,
    batting_team_id INTEGER REFERENCES teams(team_id),
    bowling_team_id INTEGER REFERENCES teams(team_id),
    striker_id      INTEGER REFERENCES players(player_id),
    non_striker_id  INTEGER REFERENCES players(player_id),
    bowler_id       INTEGER REFERENCES players(player_id),
    runs_batter     INTEGER DEFAULT 0,
    runs_extras     INTEGER DEFAULT 0,
    runs_total      INTEGER DEFAULT 0,
    extras_type     TEXT,
    is_wicket       INTEGER DEFAULT 0,
    dismissal_kind  TEXT,
    player_dismissed_id INTEGER REFERENCES players(player_id),
    is_dot           INTEGER DEFAULT 0,
    is_boundary      INTEGER DEFAULT 0,
    is_six           INTEGER DEFAULT 0,
    phase            TEXT  -- powerplay / middle / death
);

CREATE INDEX idx_deliveries_match ON deliveries(match_id);
CREATE INDEX idx_deliveries_striker ON deliveries(striker_id);
CREATE INDEX idx_deliveries_bowler ON deliveries(bowler_id);
CREATE INDEX idx_deliveries_venue_season ON deliveries(match_id);
CREATE INDEX idx_matches_season ON matches(season);
CREATE INDEX idx_innings_match ON innings(match_id);

-- Analytics views for Power BI / Streamlit SQL layer
CREATE VIEW v_match_summary AS
SELECT
    m.match_id,
    m.season,
    m.match_date,
    v.venue_name,
    v.city AS venue_city,
    t1.team_name AS team1,
    t2.team_name AS team2,
    tw.team_name AS toss_winner,
    m.toss_decision,
    w.team_name AS winner,
    m.win_by_runs,
    m.win_by_wickets,
    m.result,
    i1.total_runs AS innings1_runs,
    i1.total_wickets AS innings1_wickets,
    i2.total_runs AS innings2_runs,
    i2.total_wickets AS innings2_wickets
FROM matches m
LEFT JOIN venues v ON m.venue_id = v.venue_id
LEFT JOIN teams t1 ON m.team1_id = t1.team_id
LEFT JOIN teams t2 ON m.team2_id = t2.team_id
LEFT JOIN teams tw ON m.toss_winner_id = tw.team_id
LEFT JOIN teams w ON m.winner_id = w.team_id
LEFT JOIN innings i1 ON i1.match_id = m.match_id AND i1.innings_number = 1
LEFT JOIN innings i2 ON i2.match_id = m.match_id AND i2.innings_number = 2;

CREATE VIEW v_player_batting AS
SELECT
    p.player_id,
    p.player_name,
    m.season,
    COUNT(*) AS balls_faced,
    SUM(d.runs_batter) AS runs,
    SUM(d.is_dot) AS dots,
    SUM(d.is_boundary) AS fours,
    SUM(d.is_six) AS sixes,
    SUM(d.is_wicket) AS dismissals,
    ROUND(100.0 * SUM(d.runs_batter) / NULLIF(COUNT(*), 0), 2) AS strike_rate,
    ROUND(1.0 * SUM(d.runs_batter) / NULLIF(SUM(d.is_wicket), 0), 2) AS average
FROM deliveries d
JOIN players p ON d.striker_id = p.player_id
JOIN matches m ON d.match_id = m.match_id
GROUP BY p.player_id, p.player_name, m.season;

CREATE VIEW v_player_bowling AS
SELECT
    p.player_id,
    p.player_name,
    m.season,
    COUNT(*) AS balls_bowled,
    SUM(d.runs_total) AS runs_conceded,
    SUM(d.is_wicket) AS wickets,
    ROUND(COUNT(*) / 6.0, 2) AS overs,
    ROUND(6.0 * SUM(d.runs_total) / NULLIF(COUNT(*), 0), 2) AS economy,
    ROUND(1.0 * SUM(d.runs_total) / NULLIF(SUM(d.is_wicket), 0), 2) AS bowling_avg,
    ROUND(1.0 * COUNT(*) / NULLIF(SUM(d.is_wicket), 0), 2) AS strike_rate
FROM deliveries d
JOIN players p ON d.bowler_id = p.player_id
JOIN matches m ON d.match_id = m.match_id
WHERE d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs')
GROUP BY p.player_id, p.player_name, m.season;

CREATE VIEW v_venue_stats AS
SELECT
    v.venue_id,
    v.venue_name,
    v.city,
    m.season,
    COUNT(DISTINCT m.match_id) AS matches,
    ROUND(AVG(i.total_runs), 2) AS avg_innings_score,
    ROUND(AVG(CASE WHEN m.win_by_runs > 0 THEN 1.0 ELSE 0.0 END) * 100, 2) AS bat_first_win_pct
FROM venues v
JOIN matches m ON m.venue_id = v.venue_id
JOIN innings i ON i.match_id = m.match_id AND i.innings_number = 1
GROUP BY v.venue_id, v.venue_name, v.city, m.season;

CREATE VIEW v_team_season AS
SELECT
    t.team_id,
    t.team_name,
    m.season,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN m.winner_id = t.team_id THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id != t.team_id THEN 1 ELSE 0 END) AS losses,
    ROUND(
        100.0 * SUM(CASE WHEN m.winner_id = t.team_id THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS win_pct
FROM teams t
JOIN matches m ON t.team_id IN (m.team1_id, m.team2_id)
GROUP BY t.team_id, t.team_name, m.season;
