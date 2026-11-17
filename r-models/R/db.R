# db.R: builds the DuckDB database from the Step 1 parquet by running the
# hand-written SQL files in r-models/sql in order.

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
})

run_sql_file <- function(con, path, params = list()) {
  sql <- render_sql(paste(readLines(path, warn = FALSE), collapse = "\n"), params)
  for (stmt in split_sql(sql)) DBI::dbExecute(con, stmt)
  invisible(TRUE)
}

# Runs every NN_*.sql file in `sql_dir` against `con`, in file-name order.
run_sql_dir <- function(con, sql_dir, params = list()) {
  files <- sort(list.files(sql_dir, pattern = "^[0-9]{2}_.*\\.sql$", full.names = TRUE))
  for (f in files) {
    message("  running ", basename(f))
    run_sql_file(con, f, params)
  }
  invisible(files)
}

# Opens (and, unless it already exists, builds) data/processed/bullpen.duckdb.
# Caching rule from CLAUDE.md: skip the rebuild when the file is already there.
connect_bullpen_db <- function(paths = rm_paths(), split_date = "2026-07-01", rebuild = FALSE) {
  if (!file.exists(paths$pitches)) {
    stop("Missing ", paths$pitches, ". Run `python -m src.relievers` first (Step 1).")
  }
  fresh <- rebuild || !file.exists(paths$db)
  if (rebuild && file.exists(paths$db)) file.remove(paths$db)
  con <- DBI::dbConnect(duckdb::duckdb(), dbdir = paths$db)
  if (fresh) {
    message("Building ", paths$db)
    run_sql_dir(con, paths$sql, params = list(
      pitches_path     = paths$pitches,
      league_relievers = paths$league_relievers,
      kc_relievers     = paths$kc_relievers,
      split_date       = split_date
    ))
  }
  con
}

db_counts <- function(con) {
  tabs <- c("pitches", "relief_pa", "taken", "reliever_groups", "fstrike_raw")
  data.frame(
    table = tabs,
    rows = vapply(tabs, function(t) {
      DBI::dbGetQuery(con, sprintf("SELECT COUNT(*) AS n FROM %s", t))$n
    }, numeric(1)),
    row.names = NULL
  )
}
