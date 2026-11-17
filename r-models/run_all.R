# run_all.R: builds the DuckDB database, fits the models, writes the tables
# and figures. Run from the repo root (or anywhere inside it):
#
#   Rscript r-models/run_all.R            # uses cached database and fits
#   Rscript r-models/run_all.R --rebuild  # rebuilds the database and refits
#
# Needs data/processed/pitches_2026.parquet (python -m src.relievers) and the
# Step 1/5/6 tables in outputs/tables. Set BULLPEN_SKIP_BRMS=1 to skip the
# Stan fit; lme4 intervals are used in its place.

args <- commandArgs(trailingOnly = TRUE)
rebuild <- "--rebuild" %in% args
skip_brms <- identical(Sys.getenv("BULLPEN_SKIP_BRMS"), "1")
SPLIT_DATE <- "2026-07-01"

script_dir <- local({
  f <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  if (length(f)) dirname(normalizePath(f)) else file.path(getwd(), "r-models")
})
for (f in c("utils.R", "db.R", "fstrike_model.R", "called_strike_gam.R", "figures.R")) {
  source(file.path(script_dir, "R", f))
}

paths <- rm_paths(find_repo_root(script_dir))
for (d in c(paths$tables, paths$figures, paths$models)) dir.create(d, recursive = TRUE, showWarnings = FALSE)
out_t <- function(x) file.path(paths$tables, x)
out_f <- function(x) file.path(paths$figures, x)
cached_fit <- function(name, fit_fun) {
  f <- file.path(paths$models, paste0(name, ".rds"))
  if (!rebuild && file.exists(f)) return(readRDS(f))
  fit <- fit_fun()
  saveRDS(fit, f)
  fit
}

# 1. Database -------------------------------------------------------------------
con <- connect_bullpen_db(paths, split_date = SPLIT_DATE, rebuild = rebuild)
on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)
counts <- db_counts(con)
print(counts)
write.csv(counts, out_t("db_counts.csv"), row.names = FALSE)
write.csv(DBI::dbGetQuery(con, "SELECT * FROM fstrike_by_context"), out_t("fstrike_by_context.csv"), row.names = FALSE)

groups <- DBI::dbGetQuery(con, "SELECT * FROM reliever_groups")
qualified_ids <- groups$pitcher[groups$qualified]
kc_ids <- groups$pitcher[groups$kc_qualified]
raw <- DBI::dbGetQuery(con, "SELECT * FROM fstrike_raw")

# 2. First-pitch strike mixed model ------------------------------------------------
message("Fitting the first-pitch strike mixed model (lme4)")
pa <- prep_pa(load_relief_pa(con))
fit_lme4 <- cached_fit("fstrike_lme4", function() fit_fstrike_lme4(pa))
est <- pitcher_estimates_lme4(fit_lme4)
vs <- variance_summary(fit_lme4, pa)
print(vs)
write.csv(vs, out_t("fstrike_variance.csv"), row.names = FALSE)

message("Split-half check")
sh <- cached_fit("fstrike_split_half", function() split_half_check(pa, raw, SPLIT_DATE))
print(sh$summary)
write.csv(sh$summary, out_t("fstrike_split_half.csv"), row.names = FALSE)

# Normal approximation of P(below average) from lme4, used when brms is skipped.
b0 <- unname(lme4::fixef(fit_lme4)["(Intercept)"])
ref_lme4 <- mean(est$lme4_pct[est$pitcher %in% qualified_ids])
est$prob_below_lme4 <- round(pnorm((qlogis(ref_lme4 / 100) - b0 - est$u) / est$u_se), 3)

post <- NULL
if (!skip_brms) {
  message("Fitting the Bayesian model (brms / Stan); cached after the first run")
  agg <- aggregate_pa(pa)
  brms_file <- file.path(paths$models, "fstrike_brms")
  if (rebuild && file.exists(paste0(brms_file, ".rds"))) file.remove(paste0(brms_file, ".rds"))
  fit_brms <- fit_fstrike_brms(agg, file = brms_file)
  print(summary(fit_brms))
  post <- pitcher_posteriors_brms(fit_brms, unique(c(qualified_ids, kc_ids)), qualified_ids)
}

fs <- raw |>
  dplyr::left_join(groups[, c("pitcher", "grp", "qualified", "kc_qualified")], by = "pitcher") |>
  dplyr::left_join(est, by = "pitcher")
if (!is.null(post)) {
  fs <- dplyr::left_join(fs, post, by = "pitcher")
  fs$interval_source <- ifelse(is.na(fs$brms_pct), "lme4 (95%)", "brms (90%)")
  fs$prob_below_avg <- ifelse(is.na(fs$prob_below_avg), fs$prob_below_lme4, fs$prob_below_avg)
  for (s in c("pct", "lo", "hi")) {
    b <- paste0("brms_", s); l <- paste0("lme4_", s)
    fs[[b]] <- ifelse(is.na(fs[[b]]), fs[[l]], fs[[b]])
  }
} else {
  fs$brms_pct <- fs$lme4_pct; fs$brms_lo <- fs$lme4_lo; fs$brms_hi <- fs$lme4_hi
  fs$prob_below_avg <- fs$prob_below_lme4
  fs$league_avg_pct <- round(ref_lme4, 1)
  fs$interval_source <- "lme4 (95%)"
}
league_avg <- if (is.null(post)) round(ref_lme4, 1) else post$league_avg_pct[1]
fs$takeaway <- mapply(fstrike_takeaway, fs$name, fs$f_strike_pct, fs$brms_pct, fs$prob_below_avg,
                      MoreArgs = list(league_pct = league_avg))
write.csv(fs, out_t("fstrike_estimates.csv"), row.names = FALSE)

# 3. Leak map re-score ------------------------------------------------------------
exe <- read.csv(paths$execution, check.names = FALSE)
scores_all <- read.csv(paths$scores_all)
rescore <- rescore_execution(exe, scores_all, est, qualified_ids)
check <- rescore |> dplyr::filter(!is.na(execution_score_python))
message(sprintf("R rebuild of the Python execution score: max abs difference %.2f over %d relievers",
                max(abs(check$execution_score_raw - check$execution_score_python)), nrow(check)))
keep_cols <- c("pitcher", "name", "group", "pa", "f_strike_pct", "f_strike_pct_pctile", "lme4_pct",
               "f_strike_model_pctile", "stuff_score", "execution_score_python", "execution_score_raw",
               "execution_score_model", "quadrant_raw", "quadrant_model")
write.csv(rescore[, keep_cols], out_t("execution_rescore.csv"), row.names = FALSE)
moved <- rescore |> dplyr::filter(pitcher %in% qualified_ids, group == "MLB reliever",
                                  quadrant_raw != quadrant_model)
message(sprintf("%d of %d qualified league relievers change quadrant", nrow(moved),
                sum(rescore$pitcher %in% qualified_ids & rescore$group == "MLB reliever")))

# 4. Called-strike GAM --------------------------------------------------------------
message("Fitting the called-strike GAM (mgcv::bam)")
taken <- prep_taken(load_taken(con))
fit_gam <- cached_fit("called_strike_gam", function() fit_called_strike_gam(taken))
capture.output(summary(fit_gam), file = out_t("called_strike_gam_summary.txt"))
taken <- add_expected(fit_gam, taken)
relief <- taken[taken$is_relief, ]
csae <- csae_by_pitcher(relief) |> dplyr::filter(pitcher %in% c(qualified_ids, kc_ids))
csae$group <- ifelse(csae$pitcher %in% kc_ids, "KC reliever", "MLB reliever")
write.csv(csae, out_t("csae_by_pitcher.csv"), row.names = FALSE)
reg <- csae_by_region(relief) |> dplyr::filter(pitcher %in% c(qualified_ids, kc_ids))
write.csv(reg[, c("pitcher", "name", "edge_region", "taken", "csae_per100")], out_t("csae_by_region.csv"),
          row.names = FALSE)
write.csv(csae_by_catcher(taken), out_t("catcher_framing.csv"), row.names = FALSE)
grid <- zone_grid(fit_gam, taken)
write.csv(grid, out_t("zone_grid.csv"), row.names = FALSE)
kc_edge <- relief[relief$pitcher %in% kc_ids & abs(relief$border_dist) <= 0.25,
                  c("pitcher", "name", "p_throws", "stand", "hand", "count_grp", "plate_x", "plate_z_norm",
                    "edge_region", "called_strike", "p_league")]
kc_edge$p_league <- round(kc_edge$p_league, 4)
write.csv(kc_edge, out_t("kc_taken_edge.csv"), row.names = FALSE)

# 5. Figures ------------------------------------------------------------------------
kc_fs <- fs |> dplyr::filter(kc_qualified)
fig_fstrike_shrinkage(kc_fs, league_avg, out_f("fstrike_shrinkage_kc.png"))
fig_split_half(sh$summary, out_f("fstrike_split_half.png"))
fig_zone(grid, out_f("called_strike_zone.png"))
fig_kc_edges(reg |> dplyr::filter(pitcher %in% kc_ids), out_f("kc_edge_csae.png"))
fig_rescore(rescore |> dplyr::filter(group == "KC reliever", pitcher %in% kc_ids), out_f("execution_rescore_kc.png"))

message("Done. Tables in ", paths$tables, "; figures in ", paths$figures)
