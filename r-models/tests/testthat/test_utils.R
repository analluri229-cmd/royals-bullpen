test_that("render_sql fills placeholders and refuses leftovers", {
  expect_equal(render_sql("SELECT '{{a}}', {{b}}", list(a = "x", b = 2)), "SELECT 'x', 2")
  expect_equal(render_sql("read_parquet('{{p}}')", list(p = "C:\\data\\f.parquet")),
               "read_parquet('C:/data/f.parquet')")
  expect_error(render_sql("SELECT {{missing}}"), "Unfilled")
})

test_that("split_sql splits statements and drops comment lines", {
  s <- split_sql("-- a comment; with a semicolon\nCREATE TABLE a AS SELECT 1;\n\nSELECT 2;\n")
  expect_equal(s, c("CREATE TABLE a AS SELECT 1", "SELECT 2"))
})

test_that("midrank_pct matches src/leak_map.py rerank", {
  pool <- c(10, 20, 20, 30)
  # 5 is below all four, 10 ties one (0.5 of 4), 20 ties two (1 + 1 of 4), 40 is above all
  expect_equal(midrank_pct(c(5, 10, 20, 40), pool), c(0, 12.5, 50, 100))
  expect_true(is.na(midrank_pct(NA, pool)))
  expect_true(all(is.na(midrank_pct(c(1, 2), numeric(0)))))
})

test_that("quadrant uses the 50 cut line on both scores", {
  expect_equal(quadrant(c(60, 40, 60, 40, NA), c(60, 60, 40, 40, 50)),
               c("Keep", "Stuff fix", "Execution fix", "Replace candidate", "Insufficient sample"))
  expect_equal(quadrant(50, 50), "Keep")
})

test_that("center_cols gives mean-zero copies", {
  d <- center_cols(data.frame(x = c(0, 0, 1, 1), y = c(1, 1, 1, 0)), c("x", "y"))
  expect_equal(d$x_c, c(-0.5, -0.5, 0.5, 0.5))
  expect_equal(mean(d$y_c), 0)
})

test_that("effect_to_rate converts logit effects to percents", {
  r <- effect_to_rate(0, 0, se = 0)
  expect_equal(r$est, 50)
  r2 <- effect_to_rate(qlogis(0.6), 0, se = 0.1)
  expect_equal(r2$est, 60)
  expect_lt(r2$lo, 60)
  expect_gt(r2$hi, 60)
})

test_that("weighted_mse weights by sample size and skips NA", {
  expect_equal(weighted_mse(c(1, 3), c(0, 0), c(1, 3)), (1 * 1 + 3 * 9) / 4)
  expect_equal(weighted_mse(c(1, NA), c(0, 0), c(1, 1)), 1)
})

test_that("fstrike_takeaway picks the verdict from the posterior probability", {
  expect_match(fstrike_takeaway("Avila, Luinder", 55.1, 58.0, 0.95, 61), "real problem")
  expect_match(fstrike_takeaway("Avila, Luinder", 55.1, 58.0, 0.95, 61), "^Luinder Avila")
  expect_match(fstrike_takeaway("X", 60, 60.5, 0.5, 61), "noise")
  expect_match(fstrike_takeaway("X", 66, 64, 0.05, 61), "real strength")
})

test_that("edge_takeaway names the best and worst edge", {
  txt <- edge_takeaway(c("top", "bottom", "arm side"), c(3.2, -4.1, 0.5), c(80, 90, 70))
  expect_match(txt, "most on the top edge")
  expect_match(txt, "most on the bottom edge")
  expect_match(edge_takeaway("top", 5, 10), "Not enough")
  expect_match(edge_takeaway(c("top", "bottom"), c(0.4, -0.3), c(60, 60)), "about the calls")
})
