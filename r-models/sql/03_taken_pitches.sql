-- 03_taken_pitches.sql
-- Every taken pitch (called strike or ball) by every pitcher, starters included,
-- for the called-strike GAM. Pitchouts, intentional balls and HBP are left out.
-- plate_z_norm rescales height to the batter's zone: 0 = bottom, 1 = top.
-- Edge band: within 3 inches (0.25 ft) of the zone border, inside or out.
-- The rulebook zone is plate_x +/- 0.83 ft (plate half-width plus a ball radius),
-- the same edge src/ uses for Step 5A.
-- Edge region is named from the pitcher's side: arm side is the third-base side
-- (negative plate_x) for a right-hander and the first-base side for a lefty.

CREATE OR REPLACE TABLE taken AS
WITH base AS (
    SELECT
        game_pk, game_date, at_bat_number, pitch_number,
        pitcher, name, p_throws, stand, batter, catcher, pitching_team, is_relief,
        inning, balls, strikes,
        CONCAT(CAST(balls AS VARCHAR), '-', CAST(strikes AS VARCHAR)) AS count_str,
        CASE WHEN strikes > balls THEN 'ahead'
             WHEN strikes = balls THEN 'even'
             ELSE 'behind' END                                        AS count_grp,
        plate_x,
        plate_z,
        sz_top,
        sz_bot,
        (plate_z - sz_bot) / (sz_top - sz_bot)                        AS plate_z_norm,
        CAST(description = 'called_strike' AS INTEGER)                AS called_strike,
        -- signed distance (ft) from each border; positive = outside the zone
        ABS(plate_x) - 0.83                                           AS d_side,
        plate_z - sz_top                                              AS d_top,
        sz_bot - plate_z                                              AS d_bot
    FROM pitches
    WHERE description IN ('called_strike', 'ball', 'blocked_ball')
      AND COALESCE(pitch_type, '') <> 'PO'
      AND plate_x IS NOT NULL AND plate_z IS NOT NULL
      AND sz_top IS NOT NULL AND sz_bot IS NOT NULL
      AND sz_top > sz_bot
)
SELECT
    b.*,
    -- distance to the nearest border (ft): >0 outside, <0 inside
    CASE WHEN GREATEST(d_side, d_top, d_bot) > 0
         THEN SQRT(POWER(GREATEST(d_side, 0), 2) + POWER(GREATEST(GREATEST(d_top, d_bot), 0), 2))
         ELSE GREATEST(d_side, d_top, d_bot)
    END                                                               AS border_dist,
    CASE
        WHEN d_top >= d_bot AND d_top >= d_side THEN 'top'
        WHEN d_bot >= d_top AND d_bot >= d_side THEN 'bottom'
        WHEN (p_throws = 'R' AND plate_x < 0) OR (p_throws = 'L' AND plate_x > 0) THEN 'arm side'
        ELSE 'glove side'
    END                                                               AS edge_region
FROM base AS b
WHERE ABS(plate_x) <= 2.0
  AND plate_z_norm BETWEEN -0.75 AND 1.75;

CREATE OR REPLACE VIEW taken_edge AS
SELECT *
FROM taken
WHERE ABS(border_dist) <= 0.25;
