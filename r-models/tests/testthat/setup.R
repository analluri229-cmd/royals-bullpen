# Loads the project helpers. testthat runs this before every test file.
rm_root <- normalizePath(file.path(testthat::test_path(), "..", ".."), winslash = "/")
source(file.path(rm_root, "R", "utils.R"))
source(file.path(rm_root, "R", "db.R"))
