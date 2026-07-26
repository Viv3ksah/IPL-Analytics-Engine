-- IPL Analytics Engine — reusable SQL analytics
-- Run against db/ipl_analytics.db

-- 1) Season standings
SELECT * FROM v_team_season
WHERE season = 2024
ORDER BY win_pct DESC, wins DESC;

-- 2) Top run-scorers (season)
SELECT player_name, season, runs, balls_faced, strike_rate, average, fours, sixes
FROM v_player_batting
WHERE season = 2024 AND balls_faced >= 60
ORDER BY runs DESC
LIMIT 20;

-- 3) Top wicket-takers (season)
SELECT player_name, season, wickets, overs, economy, bowling_avg, strike_rate
FROM v_player_bowling
WHERE season = 2024 AND balls_bowled >= 60
ORDER BY wickets DESC, economy ASC
LIMIT 20;

-- 4) Venue batting parks
SELECT venue_name, city, season, matches, avg_innings_score, bat_first_win_pct
FROM v_venue_stats
WHERE season = 2024
ORDER BY avg_innings_score DESC;

-- 5) Toss decision impact league-wide
SELECT
    toss_decision,
    COUNT(*) AS matches,
    ROUND(100.0 * AVG(CASE WHEN toss_winner_id = winner_id THEN 1.0 ELSE 0.0 END), 1) AS toss_convert_pct
FROM matches
WHERE winner_id IS NOT NULL
GROUP BY toss_decision;

-- 6) Powerplay vs death scoring
SELECT
    m.season,
    d.phase,
    ROUND(AVG(d.runs_total) * 6, 2) AS run_rate,
    ROUND(100.0 * AVG(d.is_six), 2) AS six_pct
FROM deliveries d
JOIN matches m ON m.match_id = d.match_id
GROUP BY m.season, d.phase
ORDER BY m.season, d.phase;

-- 7) Highest successful chases
SELECT
    season, match_date, team2 AS chasing_side, team1 AS defending_side,
    innings1_runs AS target_minus_1, innings2_runs AS chased, venue_name, winner
FROM v_match_summary
WHERE win_by_wickets > 0
ORDER BY innings1_runs DESC
LIMIT 25;

-- 8) Bowler economy in death overs
SELECT
    p.player_name,
    COUNT(*) AS balls,
    ROUND(6.0 * SUM(d.runs_total) / COUNT(*), 2) AS death_economy,
    SUM(d.is_wicket) AS wickets
FROM deliveries d
JOIN players p ON p.player_id = d.bowler_id
WHERE d.phase = 'death'
  AND (d.extras_type IS NULL OR d.extras_type NOT IN ('wides', 'noballs'))
GROUP BY p.player_name
HAVING COUNT(*) >= 48
ORDER BY death_economy ASC
LIMIT 20;

-- 9) Team boundary rate
SELECT
    t.team_name,
    m.season,
    ROUND(100.0 * AVG(d.is_boundary + d.is_six), 2) AS boundary_ball_pct,
    ROUND(AVG(d.runs_total) * 6, 2) AS scoring_rate
FROM deliveries d
JOIN teams t ON t.team_id = d.batting_team_id
JOIN matches m ON m.match_id = d.match_id
GROUP BY t.team_name, m.season
ORDER BY m.season DESC, scoring_rate DESC;

-- 10) Close finishes (margin <= 5 runs or 2 wickets)
SELECT *
FROM v_match_summary
WHERE (win_by_runs > 0 AND win_by_runs <= 5)
   OR (win_by_wickets > 0 AND win_by_wickets <= 2)
ORDER BY match_date DESC
LIMIT 50;
