# utils.R: small helpers shared by the models, the figures and the Shiny app.
# Everything here is a pure function, so tests/testthat covers it without data.

KC_BLUE <- "#004687"
LEAGUE_GRAY <- "#9AA0A6"
CUT <- 50

# Folder layout -------------------------------------------------------------

rm_paths <- function(root = find_repo_root()) {
  list(
    root            = root,
    sql             = file.path(root, "r-models", "sql"),
    pitches         = file.path(root, "data", "processed", "pitches_2026.parquet"),
    db              = file.path(root, "data", "processed", "bullpen.duckdb"),
    league_relievers = file.path(root, "outputs", "tables", "league_relievers_2026.csv"),
    kc_relievers    = file.path(root, "outputs", "tables", "kc_relievers_2026.csv"),
    execution       = file.path(root, "outputs", "tables", "execution_by_reliever.csv"),
    leak_map        = file.path(root, "outputs", "tables", "leak_map.csv"),
    scores_all      = file.path(root, "outputs", "tables", "scores_all_relievers.csv"),
    tables          = file.path(root, "outputs", "tables", "r_models"),
    figures         = file.path(root, "outputs", "figures", "r_models"),
    models          = file.path(root, "data", "processed", "r_models")
  )
}

# Walks up from the working directory until it finds the repo's CLAUDE.md.
find_repo_root <- function(start = getwd()) {
  dir <- normalizePath(start, winslash = "/", mustWork = FALSE)
  repeat {
    if (file.exists(file.path(dir, "CLAUDE.md")) && dir.exists(file.path(dir, "r-models"))) {
      return(dir)
    }
    parent <- dirname(dir)
    if (identical(parent, dir)) stop("Could not find the royals-bullpen root from ", start)
    dir <- parent
  }
}

# SQL templates -------------------------------------------------------------

# Fills {{name}} placeholders. Every placeholder in the text must be supplied,
# so a typo fails loudly instead of sending a broken query.
render_sql <- function(sql, params = list()) {
  for (nm in names(params)) {
    value <- gsub("\\\\", "/", as.character(params[[nm]]))
    sql <- gsub(paste0("{{", nm, "}}"), value, sql, fixed = TRUE)
  }
  left <- regmatches(sql, gregexpr("\\{\\{[a-z_]+\\}\\}", sql))[[1]]
  if (length(left) > 0) stop("Unfilled SQL placeholder(s): ", paste(unique(left), collapse = ", "))
  sql
}

# DuckDB's R client runs one statement per call, so split on semicolons that
# end a line. Comment lines are dropped first (they may contain semicolons).
split_sql <- function(sql) {
  lines <- strsplit(sql, "\n", fixed = TRUE)[[1]]
  lines <- lines[!grepl("^\\s*--", lines)]
  stmts <- strsplit(paste(lines, collapse = "\n"), ";\\s*(\n|$)")[[1]]
  stmts <- trimws(stmts)
  stmts[nzchar(stmts)]
}

# Percentiles ---------------------------------------------------------------

# Mid-rank percentile (0-100) of each value within a reference pool. Same rule
# as src/leak_map.py::rerank, so R and Python percentiles line up exactly.
midrank_pct <- function(values, pool) {
  pool <- sort(pool[!is.na(pool)])
  n <- length(pool)
  out <- rep(NA_real_, length(values))
  if (n == 0) return(out)
  ok <- !is.na(values)
  lo <- findInterval(values[ok], pool, left.open = TRUE)   # count of pool < v
  hi <- findInterval(values[ok], pool)                      # count of pool <= v
  out[ok] <- round(100 * (lo + hi) / 2 / n, 1)
  out
}

quadrant <- function(stuff_score, execution_score, cut = CUT) {
  ifelse(is.na(stuff_score) | is.na(execution_score), "Insufficient sample",
    ifelse(stuff_score >= cut & execution_score >= cut, "Keep",
      ifelse(execution_score >= cut, "Stuff fix",
        ifelse(stuff_score >= cut, "Execution fix", "Replace candidate"))))
}

# Model helpers -------------------------------------------------------------

# Centers 0/1 context columns so a model's intercept is the league-average
# context (average mix of platoon, runners and late innings).
center_cols <- function(df, cols) {
  for (cc in cols) df[[paste0(cc, "_c")]] <- df[[cc]] - mean(df[[cc]], na.rm = TRUE)
  df
}

# Turns a logit-scale pitcher effect and its standard error into a rate with a
# 95% interval, all in percent.
effect_to_rate <- function(intercept, effect, se = 0, z = 1.96) {
  data.frame(
    est = 100 * plogis(intercept + effect),
    lo  = 100 * plogis(intercept + effect - z * se),
    hi  = 100 * plogis(intercept + effect + z * se)
  )
}

# Mean squared error weighted by sample size, used for the split-half check.
weighted_mse <- function(pred, actual, w) {
  ok <- !is.na(pred) & !is.na(actual) & !is.na(w)
  sum(w[ok] * (pred[ok] - actual[ok])^2) / sum(w[ok])
}

# Plain-language takeaways ----------------------------------------------------

# prob_below = posterior probability that his true first-pitch strike rate is
# below the league-average reliever's.
fstrike_takeaway <- function(name, raw_pct, model_pct, prob_below, league_pct) {
  first <- sub("^[^,]*,\\s*", "", name)
  last <- sub(",.*$", "", name)
  who <- if (nzchar(first) && first != name) paste(first, last) else name
  gap <- round(model_pct - league_pct, 1)
  verdict <- if (is.na(prob_below)) {
    "There isn't enough data to say."
  } else if (prob_below >= 0.90) {
    "This is a real problem, not bad luck. A first-pitch strike plan is worth coaching time."
  } else if (prob_below >= 0.70) {
    "This is probably real, but keep watching it before changing his plan."
  } else if (prob_below <= 0.10) {
    "This is a real strength. He gets ahead of hitters."
  } else if (prob_below <= 0.30) {
    "This is probably a strength."
  } else {
    "This looks like noise. He is about league average."
  }
  sprintf(
    "%s threw a first-pitch strike %.1f%% of the time. After adjusting for sample size, the model's best guess is %.1f%% (%s%.1f points vs. a league-average reliever). Chance he is truly below average: %.0f%%. %s",
    who, raw_pct, model_pct, if (gap >= 0) "+" else "", gap, 100 * prob_below, verdict
  )
}

# csae = called strikes above expected per 100 taken pitches in that region.
edge_takeaway <- function(regions, csae, n, min_n = 40) {
  ok <- !is.na(csae) & n >= min_n
  if (!any(ok)) return("Not enough taken pitches near the edge to judge.")
  r <- regions[ok]; v <- csae[ok]
  best <- r[which.max(v)]; worst <- r[which.min(v)]
  if (max(v) < 1 && min(v) > -1) {
    return("He gets about the calls you'd expect on every edge.")
  }
  sprintf(
    "He gains the most calls on the %s edge (%+.1f strikes per 100 takes) and loses the most on the %s edge (%+.1f). Work the %s edge early in counts; expand off the %s edge only when ahead.",
    best, max(v), worst, min(v), best, worst
  )
}
