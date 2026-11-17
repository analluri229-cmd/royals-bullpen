# One-time setup: installs the R packages this folder uses.
#   Rscript r-models/install.R
# brms needs a C++ toolchain for Stan. On Windows that is Rtools
# (https://cran.r-project.org/bin/windows/Rtools/). cmdstanr is optional and
# faster; without it brms uses rstan.
pkgs <- c("DBI", "duckdb", "dplyr", "ggplot2", "lme4", "mgcv", "brms", "posterior",
          "shiny", "testthat")
missing <- setdiff(pkgs, rownames(installed.packages()))
if (length(missing)) install.packages(missing, repos = "https://cloud.r-project.org")
message("R ", getRversion(), "; packages ready: ", paste(pkgs, collapse = ", "))
if (!requireNamespace("cmdstanr", quietly = TRUE)) {
  message("Optional: install cmdstanr for faster Stan fits:\n",
          "  install.packages('cmdstanr', repos = c('https://stan-dev.r-universe.dev', getOption('repos')))\n",
          "  cmdstanr::install_cmdstan()")
}
