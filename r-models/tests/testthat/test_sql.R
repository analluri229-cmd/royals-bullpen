# Runs the real SQL files against a tiny hand-built table. These rows are a test
# fixture for the query logic only; no analysis uses them.

fixture_pitches <- function() {
  rows <- list()
  add <- function(game_pk, ab, n, pitcher, description, type, events = NA, plate_x = 0, plate_z = 2.5,
                  relief = TRUE, stand = "R", p_throws = "R", balls = 0, strikes = 0, pitch_type = "FF",
                  inning = 8, on_1b = NA, date = "2026-05-01") {
    rows[[length(rows) + 1]] <<- data.frame(
      game_pk = game_pk, game_date = as.Date(date), game_type = "R", at_bat_number = ab, pitch_number = n,
      pitcher = pitcher, player_name = paste0("P", pitcher), p_throws = p_throws, stand = stand, batter = 9,
      fielder_2 = 7, pitching_team = "KC", is_relief = relief, inning = inning, outs_when_up = 0,
      balls = balls, strikes = strikes, pitch_type = pitch_type, description = description, type = type,
      events = events, zone = 5, plate_x = plate_x, plate_z = plate_z, sz_top = 3.5, sz_bot = 1.5,
      on_1b = on_1b, on_2b = NA_real_, on_3b = NA_real_, stringsAsFactors = FALSE)
  }
  add(1, 1, 1, 100, "called_strike", "S")
  add(1, 1, 2, 100, "hit_into_play", "X", "single")
  add(1, 2, 1, 100, "ball", "B", plate_x = 1.0)
  add(1, 2, 2, 100, "ball", "B", "walk", plate_x = -1.0, balls = 1, on_1b = 555)
  add(1, 3, 1, 100, "ball", "B", "caught_stealing_2b")                  # not a PA
  add(1, 4, 1, 200, "foul", "S", relief = FALSE)                          # starter
  add(1, 4, 2, 200, "swinging_strike", "S", "strikeout", relief = FALSE)
  add(1, 5, 1, 100, "ball", "B", plate_z = 3.6, stand = "L")
  add(1, 5, 2, 100, "ball", "B", "field_out", plate_z = 1.4, stand = "L", date = "2026-08-01")
  add(1, 6, 1, 100, "pitchout", "B", "walk", plate_x = 1.9, pitch_type = "PO")
  do.call(rbind, rows)
}

with_fixture_db <- function(code) {
  con <- DBI::dbConnect(duckdb::duckdb())
  on.exit(DBI::dbDisconnect(con, shutdown = TRUE))
  pq <- tempfile(fileext = ".parquet")
  duckdb::duckdb_register(con, "fx", fixture_pitches())
  DBI::dbExecute(con, sprintf("COPY fx TO '%s' (FORMAT PARQUET)", gsub("\\\\", "/", pq)))
  sql_dir <- file.path(rm_root, "sql")
  params <- list(pitches_path = pq, split_date = "2026-07-01")
  for (f in c("01_pitches.sql", "02_relief_pa.sql", "03_taken_pitches.sql", "05_raw_fstrike.sql")) {
    run_sql_file(con, file.path(sql_dir, f), params)
  }
  code(con)
}

test_that("relief_pa keeps relief PAs only and drops runner-event endings", {
  with_fixture_db(function(con) {
    pa <- DBI::dbGetQuery(con, "SELECT * FROM relief_pa ORDER BY at_bat_number")
    expect_equal(pa$at_bat_number, c(1, 2, 5, 6))
    expect_equal(pa$first_strike, c(1, 0, 0, 0))
    expect_equal(pa$same_hand, c(1, 1, 0, 1))
    expect_equal(pa$runners_on, c(0, 0, 0, 0))   # runner reached on pitch 2, not before pitch 1
    expect_equal(pa$late_inning, rep(1, 4))
  })
})

test_that("taken keeps called strikes and balls, not pitchouts or swings", {
  with_fixture_db(function(con) {
    t <- DBI::dbGetQuery(con, "SELECT * FROM taken ORDER BY at_bat_number, pitch_number")
    expect_equal(nrow(t), 6)
    expect_false(any(t$pitcher == 200))
    expect_equal(sum(t$called_strike), 1)
    top <- t[t$at_bat_number == 5 & t$pitch_number == 1, ]
    expect_equal(top$edge_region, "top")
    expect_equal(round(top$border_dist, 3), 0.1)
    expect_equal(t$edge_region[t$at_bat_number == 2 & t$pitch_number == 2], "arm side")   # RHP, plate_x < 0
    expect_equal(t$edge_region[t$at_bat_number == 2 & t$pitch_number == 1], "glove side")
    expect_equal(t$count_grp[t$at_bat_number == 2 & t$pitch_number == 2], "behind")
    expect_equal(DBI::dbGetQuery(con, "SELECT COUNT(*) AS n FROM taken_edge")$n, 4)
  })
})

test_that("fstrike_raw splits the season at the split date", {
  with_fixture_db(function(con) {
    r <- DBI::dbGetQuery(con, "SELECT * FROM fstrike_raw")
    expect_equal(r$pa, 4)
    expect_equal(r$f_strikes, 1)
    expect_equal(r$pa_h1, 4)   # a PA is dated by its first pitch
    expect_equal(r$pa_h2, 0)
    expect_equal(r$f_strike_pct, 25)
  })
})
