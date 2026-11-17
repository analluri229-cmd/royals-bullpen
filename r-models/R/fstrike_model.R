# fstrike_model.R: how much of a reliever's first-pitch strike rate is real?
#
# Model 1 (lme4): logistic mixed model on every relief PA's first pitch.
#   first_strike ~ platoon + runners on + late inning
#                  + (1 | pitcher) + (1 | batter) + (1 | catcher)
#   The pitcher random intercept is his talent, shrunk toward league average in
#   proportion to how little data he has. Batter and catcher effects soak up
#   who he happened to face and who caught him.
# Model 2 (brms / Stan): the same idea, Bayesian, fit on PAs aggregated to
#   pitcher x catcher x context cells (binomial), so it runs in minutes. The
#   batter term is dropped there for speed. Its output is a full posterior
#   per reliever, so we can say "an 85% chance he is truly below average".
# Check: fit on the first half only and predict each reliever's second-half
#   rate. If shrinkage is doing its job, the model beats the raw first-half rate.

suppressPackageStartupMessages({
  library(DBI)
  library(dplyr)
  library(lme4)
})

CONTEXT <- c("same_hand", "runners_on", "late_inning")

load_relief_pa <- function(con) {
  DBI::dbGetQuery(con, "
    SELECT pa.pitcher, pa.batter, pa.catcher, pa.game_date,
           pa.same_hand, pa.runners_on, pa.late_inning, pa.first_strike
    FROM relief_pa AS pa
    WHERE pa.catcher IS NOT NULL
  ")
}

prep_pa <- function(pa) {
  pa <- center_cols(pa, CONTEXT)
  pa$pitcher_f <- factor(pa$pitcher)
  pa$batter_f <- factor(pa$batter)
  pa$catcher_f <- factor(pa$catcher)
  pa
}

# lme4 ----------------------------------------------------------------------

fit_fstrike_lme4 <- function(pa) {
  lme4::glmer(
    first_strike ~ same_hand_c + runners_on_c + late_inning_c +
      (1 | pitcher_f) + (1 | batter_f) + (1 | catcher_f),
    data = pa, family = binomial(),
    # nAGQ = 0 fits fixed effects inside the penalized step; on ~70k PAs it is
    # far faster than Laplace and gives the same pitcher estimates to 0.1 pt.
    nAGQ = 0,
    control = lme4::glmerControl(optimizer = "nloptwrap", calc.derivs = FALSE)
  )
}

pitcher_estimates_lme4 <- function(fit) {
  re <- as.data.frame(lme4::ranef(fit, condVar = TRUE))
  re <- re[re$grpvar == "pitcher_f", ]
  b0 <- unname(lme4::fixef(fit)["(Intercept)"])
  rates <- effect_to_rate(b0, re$condval, re$condsd)
  data.frame(
    pitcher = as.numeric(as.character(re$grp)),
    u = re$condval, u_se = re$condsd,
    lme4_pct = round(rates$est, 1), lme4_lo = round(rates$lo, 1), lme4_hi = round(rates$hi, 1)
  )
}

variance_summary <- function(fit, pa) {
  vc <- as.data.frame(lme4::VarCorr(fit))
  p <- mean(pa$first_strike)
  sd_p <- vc$sdcor[vc$grp == "pitcher_f"]
  # PAs at which a reliever's observed F-Strike% is half signal, half noise:
  # n = 1 / (sd_logit^2 * p * (1 - p)), the usual binomial stabilization point.
  data.frame(
    term = vc$grp,
    sd_logit = round(vc$sdcor, 3),
    sd_rate_pts = round(100 * vc$sdcor * p * (1 - p), 2),
    league_rate = round(100 * p, 1),
    half_signal_pa = ifelse(vc$grp == "pitcher_f", round(1 / (sd_p^2 * p * (1 - p))), NA)
  )
}

# Split-half check ------------------------------------------------------------

split_half_check <- function(pa, raw, split_date = "2026-07-01", min_pa = 20) {
  h1 <- prep_pa(pa[as.Date(pa$game_date) < as.Date(split_date), ])
  fit1 <- fit_fstrike_lme4(h1)
  est1 <- pitcher_estimates_lme4(fit1)
  league_h1 <- 100 * mean(h1$first_strike)
  d <- raw |>
    dplyr::filter(pa_h1 >= min_pa, pa_h2 >= min_pa) |>
    dplyr::mutate(raw_h1 = 100 * f_strikes_h1 / pa_h1, actual_h2 = 100 * f_strikes_h2 / pa_h2) |>
    dplyr::inner_join(est1[, c("pitcher", "lme4_pct")], by = "pitcher")
  res <- data.frame(
    predictor = c("League average (first half)", "Raw first-half F-Strike%", "Mixed model (first half)"),
    weighted_mse = c(
      weighted_mse(rep(league_h1, nrow(d)), d$actual_h2, d$pa_h2),
      weighted_mse(d$raw_h1, d$actual_h2, d$pa_h2),
      weighted_mse(d$lme4_pct, d$actual_h2, d$pa_h2)
    ),
    correlation = c(NA, cor(d$raw_h1, d$actual_h2), cor(d$lme4_pct, d$actual_h2)),
    relievers = nrow(d)
  )
  res$rmse_pts <- round(sqrt(res$weighted_mse), 2)
  res$weighted_mse <- round(res$weighted_mse, 2)
  res$correlation <- round(res$correlation, 3)
  list(summary = res, by_pitcher = d)
}

# brms ------------------------------------------------------------------------

aggregate_pa <- function(pa) {
  pa |>
    dplyr::group_by(pitcher_f, catcher_f, same_hand_c, runners_on_c, late_inning_c) |>
    dplyr::summarise(n = dplyr::n(), y = sum(first_strike), .groups = "drop")
}

fit_fstrike_brms <- function(agg, file, chains = 4, iter = 2000, seed = 2026) {
  backend <- if (requireNamespace("cmdstanr", quietly = TRUE)) "cmdstanr" else "rstan"
  priors <- c(
    # logit(0.61) = 0.45: league relievers throw about 61% first-pitch strikes
    brms::prior(normal(0.45, 0.5), class = "Intercept"),
    brms::prior(normal(0, 0.5), class = "b"),
    # half-normal on the logit scale: a 1 SD pitcher moving F-Strike% by more
    # than ~12 points would be surprising, so this is weak but not flat
    brms::prior(normal(0, 0.5), class = "sd")
  )
  brms::brm(
    y | trials(n) ~ same_hand_c + runners_on_c + late_inning_c + (1 | pitcher_f) + (1 | catcher_f),
    data = agg, family = binomial(), prior = priors,
    chains = chains, iter = iter, warmup = iter / 2, cores = min(chains, parallel::detectCores()),
    seed = seed, backend = backend,
    file = file   # caching: brms reloads the saved fit instead of refitting
  )
}

# Posterior rate per pitcher, plus P(true rate < league-average reliever).
# League average = the mean true rate across qualified relievers, per draw.
pitcher_posteriors_brms <- function(fit, pitcher_ids, qualified_ids) {
  draws <- as.data.frame(brms::as_draws_df(fit))
  b0 <- draws$b_Intercept
  col_for <- function(id) sprintf("r_pitcher_f[%s,Intercept]", id)
  have <- pitcher_ids[col_for(pitcher_ids) %in% names(draws)]
  rate <- sapply(have, function(id) plogis(b0 + draws[[col_for(id)]]))
  colnames(rate) <- as.character(have)
  q <- intersect(as.character(qualified_ids), colnames(rate))
  ref <- rowMeans(rate[, q, drop = FALSE])
  data.frame(
    pitcher = as.numeric(colnames(rate)),
    brms_pct = round(100 * apply(rate, 2, median), 1),
    brms_lo = round(100 * apply(rate, 2, quantile, 0.05), 1),
    brms_hi = round(100 * apply(rate, 2, quantile, 0.95), 1),
    prob_below_avg = round(colMeans(rate < ref), 3),
    league_avg_pct = round(100 * mean(ref), 1)
  )
}

# Leak map re-score -------------------------------------------------------------

# Rebuilds the Step 6 execution score with the model's F-Strike% in place of
# the raw one, using the same percentile rules as src/leak_map.py. The raw
# rebuild is returned too, so the R version can be checked against Python.
rescore_execution <- function(exe, scores_all, est, qualified_ids, est_col = "lme4_pct") {
  e <- exe[is.na(exe$sample_flag) | exe$sample_flag == "", ]
  good <- function(df) cbind(
    df$zone_pct_pctile, df$f_strike_pct_pctile, df$three_ps_pct_pctile,
    df$kill_pct_pctile, 100 - df$bb_pct_pctile, df$chase_pct_pctile
  )
  e <- dplyr::left_join(e, est[, c("pitcher", est_col)], by = "pitcher")
  pool_rows <- e$group == "MLB reliever" & e$pitcher %in% qualified_ids & e$pa >= 50
  e$f_strike_model_pctile <- midrank_pct(e[[est_col]], e[[est_col]][pool_rows])
  g_raw <- good(e)
  g_new <- g_raw
  g_new[, 2] <- e$f_strike_model_pctile
  e$exec_composite_raw <- np_round1(np_row_mean(g_raw))
  e$exec_composite_model <- np_round1(np_row_mean(g_new))
  ref <- e$pitcher %in% qualified_ids
  e$execution_score_raw <- midrank_pct(e$exec_composite_raw, e$exec_composite_raw[ref])
  e$execution_score_model <- midrank_pct(e$exec_composite_model, e$exec_composite_model[ref])
  s <- scores_all[, c("pitcher", "group", "stuff_score", "execution_score")]
  names(s)[names(s) == "execution_score"] <- "execution_score_python"
  e <- dplyr::left_join(e, s, by = c("pitcher", "group"))
  e$quadrant_raw <- quadrant(e$stuff_score, e$execution_score_raw)
  e$quadrant_model <- quadrant(e$stuff_score, e$execution_score_model)
  e
}
