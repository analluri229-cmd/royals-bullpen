# Run from the repo root:  Rscript r-models/tests/testthat.R
library(testthat)
here <- local({
  f <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  if (length(f)) dirname(normalizePath(f)) else file.path(getwd(), "r-models", "tests")
})
test_dir(file.path(here, "testthat"), stop_on_failure = TRUE)
