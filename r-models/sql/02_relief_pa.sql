-- 02_relief_pa.sql
-- One row per relief plate appearance, described by its first pitch.
--   first_strike = 1 when the first pitch is a called strike, swinging strike,
--   foul or ball in play (Statcast type S or X), the same F-Strike% rule as
--   src/execution.py.
-- The PA goes to the pitcher who threw its FIRST pitch (src/execution.py credits
-- the last pitch's pitcher; the two differ only on mid-PA pitching changes).
-- Runner events that end an inning mid-PA are not plate appearances.

CREATE OR REPLACE TABLE relief_pa AS
WITH ordered AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY game_pk, at_bat_number ORDER BY pitch_number)      AS pitch_seq,
        ROW_NUMBER() OVER (PARTITION BY game_pk, at_bat_number ORDER BY pitch_number DESC) AS pitch_seq_desc
    FROM pitches AS p
),
first_pitch AS (
    SELECT * FROM ordered WHERE pitch_seq = 1
),
last_pitch AS (
    SELECT game_pk, at_bat_number, events AS pa_event, pitch_number AS n_pitches
    FROM ordered
    WHERE pitch_seq_desc = 1
)
SELECT
    f.game_pk,
    f.game_date,
    f.at_bat_number,
    f.pitcher,
    f.name,
    f.p_throws,
    f.stand,
    f.batter,
    f.catcher,
    f.pitching_team,
    f.inning,
    f.outs_when_up,
    CAST(f.runners_on AS INTEGER)              AS runners_on,
    CAST(f.p_throws = f.stand AS INTEGER)      AS same_hand,
    CAST(f.inning >= 7 AS INTEGER)             AS late_inning,
    CASE
        WHEN f.pitch_type IN ('FF', 'SI', 'FC')                   THEN 'FB'
        WHEN f.pitch_type IN ('SL', 'ST', 'CU', 'KC', 'SV', 'CS') THEN 'BRK'
        WHEN f.pitch_type IN ('CH', 'FS', 'FO', 'SC')             THEN 'OFF'
        ELSE 'OTHER'
    END                                        AS first_pitch_group,
    CAST(f.result_type IN ('S', 'X') AS INTEGER) AS first_strike,
    l.pa_event,
    l.n_pitches
FROM first_pitch AS f
JOIN last_pitch  AS l USING (game_pk, at_bat_number)
WHERE f.is_relief
  AND l.pa_event IS NOT NULL
  AND l.pa_event NOT IN (
        'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
        'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
        'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
        'pickoff_caught_stealing_home', 'other_out', 'stolen_base_2b',
        'wild_pitch', 'passed_ball', 'game_advisory');
