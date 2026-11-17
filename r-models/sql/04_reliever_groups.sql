-- 04_reliever_groups.sql
-- Who is who: qualified league relievers (Step 1, league_relievers_2026.csv) and
-- qualified KC relievers (Step 1, kc_relievers_2026.csv, KC appearances only).

CREATE OR REPLACE TABLE reliever_groups AS
WITH league AS (
    SELECT pitcher, name, throws, relief_ip, relief_bf, qualified
    FROM read_csv_auto('{{league_relievers}}')
),
kc AS (
    SELECT pitcher, qualified AS kc_qualified
    FROM read_csv_auto('{{kc_relievers}}')
)
SELECT
    l.pitcher,
    l.name,
    l.throws,
    l.relief_ip,
    l.relief_bf,
    l.qualified,
    COALESCE(k.kc_qualified, FALSE)                      AS kc_qualified,
    CASE WHEN k.pitcher IS NOT NULL THEN 'KC reliever' ELSE 'MLB reliever' END AS grp
FROM league AS l
LEFT JOIN kc AS k USING (pitcher);
