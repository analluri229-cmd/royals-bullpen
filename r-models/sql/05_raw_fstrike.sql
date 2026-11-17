-- 05_raw_fstrike.sql
-- Raw first-pitch strike rate per reliever, overall and by half season.
-- {{split_date}} is the first day of the "second half" (default 2026-07-01).

CREATE OR REPLACE TABLE fstrike_raw AS
SELECT
    pa.pitcher,
    ANY_VALUE(pa.name)                                                    AS name,
    ANY_VALUE(pa.p_throws)                                                AS throws,
    CAST(COUNT(*) AS INTEGER)                                             AS pa,
    CAST(SUM(pa.first_strike) AS INTEGER)                                 AS f_strikes,
    ROUND(100.0 * AVG(pa.first_strike), 1)                                AS f_strike_pct,
    CAST(COUNT(*) FILTER (WHERE pa.game_date <  DATE '{{split_date}}') AS INTEGER) AS pa_h1,
    CAST(COALESCE(SUM(first_strike) FILTER (WHERE pa.game_date <  DATE '{{split_date}}'), 0) AS INTEGER) AS f_strikes_h1,
    CAST(COUNT(*) FILTER (WHERE pa.game_date >= DATE '{{split_date}}') AS INTEGER) AS pa_h2,
    CAST(COALESCE(SUM(first_strike) FILTER (WHERE pa.game_date >= DATE '{{split_date}}'), 0) AS INTEGER) AS f_strikes_h2
FROM relief_pa AS pa
GROUP BY pa.pitcher;

-- League first-pitch strike rate by context, for the write-up.
CREATE OR REPLACE VIEW fstrike_by_context AS
SELECT
    same_hand,
    runners_on,
    late_inning,
    CAST(COUNT(*) AS INTEGER)               AS pa,
    ROUND(100.0 * AVG(first_strike), 1)     AS f_strike_pct
FROM relief_pa
GROUP BY ALL
ORDER BY ALL;
