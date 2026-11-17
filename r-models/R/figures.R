# figures.R: 300 dpi PNGs in outputs/figures/r_models. Royals blue for KC,
# gray for league (CLAUDE.md project rules). Every figure reads only the
# tables written to outputs/tables/r_models, so each number traces to a file.

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
})

theme_bullpen <- function() {
  theme_minimal(base_size = 11) +
    theme(panel.grid.minor = element_blank(),
          plot.title = element_text(face = "bold"),
          plot.title.position = "plot",
          plot.caption = element_text(color = "gray40", hjust = 0))
}

save_fig <- function(p, path, width = 8, height = 5) {
  ggsave(path, p, width = width, height = height, dpi = 300, bg = "white")
  invisible(path)
}

# Raw vs. model F-Strike% for KC relievers, with the Bayesian 90% interval.
fig_fstrike_shrinkage <- function(kc, league_avg, path) {
  # Label the interval by the model that made it: brms (90%) or the lme4 fallback (95%).
  bayes <- all(kc$interval_source == "brms (90%)")
  est_label <- if (bayes) "Bayesian (brms) estimate with 90% interval" else "mixed-model (lme4) estimate with 95% interval"
  cap_model <- if (bayes) "brms binomial, pitcher + catcher random effects" else
    "lme4 logistic, pitcher + batter + catcher random effects"
  kc <- kc |> arrange(brms_pct) |> mutate(name = factor(name, levels = name))
  p <- ggplot(kc, aes(y = name)) +
    geom_vline(xintercept = league_avg, linetype = "dashed", color = LEAGUE_GRAY) +
    geom_linerange(aes(xmin = brms_lo, xmax = brms_hi), color = KC_BLUE, alpha = 0.35,
                   linewidth = 2.2) +
    geom_segment(aes(x = f_strike_pct, xend = brms_pct, yend = name), color = "gray60",
                 arrow = arrow(length = unit(0.12, "cm"))) +
    geom_point(aes(x = f_strike_pct), shape = 21, fill = "white", color = "gray30", size = 2.4) +
    geom_point(aes(x = brms_pct), color = KC_BLUE, size = 2.8) +
    geom_text(aes(x = pmax(brms_hi, f_strike_pct) + 0.6, label = paste0(pa, " PA")),
              hjust = 0, size = 3, color = "gray35") +
    labs(title = "Which Royals first-pitch strike problems are real?",
         subtitle = paste0("Hollow = raw 2026 F-Strike%. Blue = ", est_label, ". Dashed = league-average reliever."),
         x = "First-pitch strike %", y = NULL,
         caption = paste0("Model: ", cap_model, ", platoon / runners / late-inning context. Source: Statcast 2026 relief PAs.")) +
    theme_bullpen()
  save_fig(p, path, width = 8.5, height = 5.5)
}

fig_split_half <- function(sh, path) {
  sh$predictor <- factor(sh$predictor, levels = rev(sh$predictor))
  p <- ggplot(sh, aes(x = rmse_pts, y = predictor,
                      fill = predictor == "Mixed model (first half)")) +
    geom_col(width = 0.6) +
    geom_text(aes(label = sprintf("%.2f", rmse_pts)), hjust = -0.15, size = 3.5) +
    scale_fill_manual(values = c(`TRUE` = KC_BLUE, `FALSE` = LEAGUE_GRAY), guide = "none") +
    scale_x_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(title = "Shrinkage predicts the second half better than the raw rate",
         subtitle = sprintf("Error predicting each reliever's second-half F-Strike%% (%d relievers, 20+ PA each half)",
                            sh$relievers[1]),
         x = "RMSE, percentage points (weighted by second-half PA)", y = NULL,
         caption = "Part of the error is coin-flip noise in the second half itself, which no predictor can remove.") +
    theme_bullpen()
  save_fig(p, path, width = 8, height = 3.6)
}

zone_box <- function() {
  annotate("rect", xmin = -0.83, xmax = 0.83, ymin = 0, ymax = 1, fill = NA, color = "black",
           linewidth = 0.4)
}

# League called-strike probability by handedness, with the 50% line.
fig_zone <- function(grid, path) {
  p <- ggplot(grid, aes(plate_x, plate_z_norm)) +
    geom_raster(aes(fill = p_strike), interpolate = TRUE) +
    geom_contour(aes(z = p_strike), breaks = 0.5, color = "white", linewidth = 0.7) +
    zone_box() +
    scale_fill_gradient(low = "gray95", high = KC_BLUE, name = "P(called\nstrike)") +
    coord_fixed(ratio = 1.8) +
    facet_wrap(~hand, nrow = 1) +
    labs(title = "The called strike zone the umpires actually call, 2026",
         subtitle = "League GAM, even counts, average pitcher and catcher. White = 50% line. Box = rulebook zone.",
         x = "Horizontal location (ft, catcher's view)", y = "Height (0 = bottom of zone, 1 = top)") +
    theme_bullpen()
  save_fig(p, path, width = 11, height = 4.2)
}

# KC relievers x edge region, called strikes above expected per 100 takes.
fig_kc_edges <- function(reg, path, min_n = 25) {
  reg <- reg |>
    mutate(label = sprintf("%+.1f\n(n=%d)", csae_per100, taken),
           value = ifelse(taken >= min_n, csae_per100, NA),
           edge_region = factor(edge_region, levels = c("top", "arm side", "glove side", "bottom")))
  p <- ggplot(reg, aes(edge_region, name, fill = value)) +
    geom_tile(color = "white") +
    geom_text(aes(label = label, color = taken >= min_n), size = 2.8, lineheight = 0.9) +
    scale_color_manual(values = c(`TRUE` = "black", `FALSE` = "gray55"), guide = "none") +
    scale_fill_gradient2(low = "#B03A2E", mid = "white", high = KC_BLUE, midpoint = 0,
                         na.value = "gray94", name = "CSAE\nper 100") +
    labs(title = "Where Royals relievers gain and lose borderline calls",
         subtitle = "Called strikes above expected per 100 taken pitches within 3 inches of the zone edge",
         x = NULL, y = NULL,
         caption = sprintf("Expected = league GAM with an average pitcher and catcher. Gray text = fewer than %d takes: directional only.", min_n)) +
    theme_bullpen()
  save_fig(p, path, width = 7.5, height = 5.8)
}

# Execution score before vs. after swapping in the model F-Strike%.
fig_rescore <- function(kc_rescore, path) {
  d <- kc_rescore |> filter(!is.na(execution_score_model))
  p <- ggplot(d, aes(y = reorder(name, execution_score_model))) +
    geom_vline(xintercept = CUT, linetype = "dashed", color = LEAGUE_GRAY) +
    geom_segment(aes(x = execution_score_raw, xend = execution_score_model, yend = name),
                 color = "gray60", arrow = arrow(length = unit(0.12, "cm"))) +
    geom_point(aes(x = execution_score_raw), shape = 21, fill = "white", color = "gray30", size = 2.4) +
    geom_point(aes(x = execution_score_model, color = quadrant_raw != quadrant_model), size = 2.8) +
    scale_color_manual(values = c(`FALSE` = KC_BLUE, `TRUE` = "#B03A2E"),
                       labels = c(`FALSE` = "Same quadrant", `TRUE` = "Quadrant changes"), name = NULL) +
    labs(title = "Does the leak map change once F-Strike% is shrunk?",
         subtitle = "Execution score (league percentile) with raw vs. model F-Strike%. Dashed = the 50 cut line.",
         x = "Execution score", y = NULL) +
    theme_bullpen() + theme(legend.position = "bottom")
  save_fig(p, path, width = 8, height = 5.5)
}
