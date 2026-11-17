# called_strike_gam.R: which relievers get (or lose) borderline strike calls?
#
# Model: a binomial GAM (mgcv::bam) on every taken pitch in 2026, starters
# included, so the zone is learned from ~350k calls.
#   called_strike ~ hand + count group
#                   + te(plate_x, plate_z_norm, by = hand)        4 zone shapes
#                   + te(plate_x, plate_z_norm, by = count group) count tweaks
#                   + s(catcher, bs = "re") + s(pitcher, bs = "re")
# The two random effects make it a GAMM: catcher framing and the pitcher's own
# effect are estimated together, so a pitcher isn't credited for his catcher.
# Called strikes above expected (CSAE) = actual strikes minus the strikes a
# league-average pitcher and catcher would get on the same pitches.
# Umpire is left out: the umpire column in our Statcast pull is 0% filled
# (notes/decisions.md, 2026-10-31).

suppressPackageStartupMessages({
  library(DBI)
  library(dplyr)
  library(mgcv)
})

load_taken <- function(con) {
  DBI::dbGetQuery(con, "
    SELECT t.game_pk, t.at_bat_number, t.pitch_number,
           t.pitcher, t.name, t.p_throws, t.stand, t.catcher, t.pitching_team, t.is_relief,
           t.count_grp, t.plate_x, t.plate_z_norm, t.called_strike,
           t.border_dist, t.edge_region
    FROM taken AS t
    WHERE t.catcher IS NOT NULL
  ")
}

prep_taken <- function(taken) {
  taken$hand <- factor(paste0(taken$p_throws, "HP v ", taken$stand, "HB"))
  # ordered factor: the count smooth is a difference from "even" counts
  taken$count_grp <- factor(taken$count_grp, levels = c("even", "ahead", "behind"), ordered = TRUE)
  taken$pitcher_f <- factor(taken$pitcher)
  taken$catcher_f <- factor(taken$catcher)
  taken
}

fit_called_strike_gam <- function(taken, threads = max(1, parallel::detectCores() - 1)) {
  mgcv::bam(
    called_strike ~ hand + count_grp +
      te(plate_x, plate_z_norm, by = hand, k = c(10, 10)) +
      te(plate_x, plate_z_norm, by = count_grp, k = c(6, 6)) +
      s(catcher_f, bs = "re") + s(pitcher_f, bs = "re"),
    data = taken, family = binomial(), method = "fREML",
    discrete = TRUE, nthreads = threads
  )
}

RE_TERMS <- c("s(catcher_f)", "s(pitcher_f)")

# Adds p_league (league-average pitcher and catcher), p_pitcher (pitcher's own
# effect, average catcher) and p_catcher (catcher's effect, average pitcher).
add_expected <- function(fit, taken) {
  lp <- function(exclude) as.numeric(predict(fit, newdata = taken, type = "link", exclude = exclude))
  taken$p_league <- plogis(lp(RE_TERMS))
  taken$p_pitcher <- plogis(lp("s(catcher_f)"))
  taken$p_catcher <- plogis(lp("s(pitcher_f)"))
  taken
}

# CSAE per 100 taken pitches: raw (includes his catchers' framing) and the
# pitcher-only part from the model's pitcher term.
csae_by_pitcher <- function(taken, edge_only = TRUE) {
  d <- if (edge_only) taken[abs(taken$border_dist) <= 0.25, ] else taken
  d |>
    dplyr::group_by(pitcher) |>
    dplyr::summarise(
      name = dplyr::first(name), throws = dplyr::first(p_throws),
      taken = dplyr::n(),
      called_strikes = sum(called_strike),
      expected = round(sum(p_league), 1),
      csae = round(sum(called_strike - p_league), 1),
      csae_per100 = round(100 * mean(called_strike - p_league), 2),
      pitcher_csae_per100 = round(100 * mean(p_pitcher - p_league), 2),
      catcher_csae_per100 = round(100 * mean(p_catcher - p_league), 2),
      .groups = "drop"
    )
}

csae_by_region <- function(taken) {
  taken[abs(taken$border_dist) <= 0.25, ] |>
    dplyr::group_by(pitcher, edge_region) |>
    dplyr::summarise(
      name = dplyr::first(name), taken = dplyr::n(),
      csae_per100 = round(100 * mean(called_strike - p_league), 2),
      .groups = "drop"
    )
}

csae_by_catcher <- function(taken) {
  taken[abs(taken$border_dist) <= 0.25, ] |>
    dplyr::group_by(catcher) |>
    dplyr::summarise(taken = dplyr::n(),
                     framing_per100 = round(100 * mean(p_catcher - p_league), 2),
                     .groups = "drop")
}

# League zone on a grid, for the zone figure and the Shiny app.
zone_grid <- function(fit, taken, by = 0.05) {
  g <- expand.grid(
    plate_x = seq(-1.6, 1.6, by = by),
    plate_z_norm = seq(-0.5, 1.5, by = by),
    hand = levels(taken$hand),
    stringsAsFactors = FALSE
  )
  g$hand <- factor(g$hand, levels = levels(taken$hand))
  g$count_grp <- factor("even", levels = levels(taken$count_grp), ordered = TRUE)
  # any valid level works: the random effects are excluded below
  g$pitcher_f <- factor(levels(taken$pitcher_f)[1], levels = levels(taken$pitcher_f))
  g$catcher_f <- factor(levels(taken$catcher_f)[1], levels = levels(taken$catcher_f))
  g$p_strike <- round(plogis(as.numeric(predict(fit, newdata = g, type = "link", exclude = RE_TERMS))), 4)
  g[, c("hand", "plate_x", "plate_z_norm", "p_strike")]
}
