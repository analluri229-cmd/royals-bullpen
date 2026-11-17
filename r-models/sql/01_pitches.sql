-- 01_pitches.sql
-- One row per 2026 regular-season pitch, read straight from the Step 1 parquet
-- (data/processed/pitches_2026.parquet already carries pitching_team and is_relief).
-- {{pitches_path}} is filled in by R/db.R.

CREATE OR REPLACE TABLE pitches AS
SELECT
    game_pk,
    CAST(game_date AS DATE)                 AS game_date,
    at_bat_number,
    pitch_number,
    pitcher,
    player_name                             AS name,
    p_throws,
    stand,
    batter,
    fielder_2                               AS catcher,
    pitching_team,
    is_relief,
    inning,
    outs_when_up,
    balls,
    strikes,
    pitch_type,
    description,
    "type"                                  AS result_type,
    events,
    zone,
    plate_x,
    plate_z,
    sz_top,
    sz_bot,
    (on_1b IS NOT NULL OR on_2b IS NOT NULL OR on_3b IS NOT NULL) AS runners_on
FROM read_parquet('{{pitches_path}}')
WHERE game_type = 'R';
