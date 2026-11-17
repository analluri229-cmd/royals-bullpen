# Bullpen strike-throwing app for coaches.
# Run from the repo root:  Rscript -e "shiny::runApp('r-models/app')"
# Reads only the tables written by r-models/run_all.R, so it opens instantly.

library(shiny)
library(ggplot2)
library(dplyr)

app_dir <- local({
  d <- getwd()
  if (file.exists(file.path(d, "app.R"))) d else file.path(d, "r-models", "app")
})
source(file.path(app_dir, "..", "R", "utils.R"))
paths <- rm_paths(find_repo_root(app_dir))
tab <- function(x) read.csv(file.path(paths$tables, x), stringsAsFactors = FALSE)

fs <- tab("fstrike_estimates.csv")
reg <- tab("csae_by_region.csv")
csae <- tab("csae_by_pitcher.csv")
grid <- tab("zone_grid.csv")
edge <- tab("kc_taken_edge.csv")
rescore <- tab("execution_rescore.csv")

kc <- fs |> filter(kc_qualified %in% c(TRUE, "TRUE")) |> arrange(name)
league_avg <- fs$league_avg_pct[!is.na(fs$league_avg_pct)][1]
choices <- setNames(kc$pitcher, kc$name)

ui <- fluidPage(
  tags$head(tags$style(HTML(sprintf("
    body { font-family: system-ui, sans-serif; }
    h2 { color: %s; font-weight: 700; }
    .takeaway { background: #EEF3F9; border-left: 4px solid %s; padding: 12px 16px;
                margin: 8px 0 16px; font-size: 15px; line-height: 1.45; }
    .note { color: #666; font-size: 12px; }", KC_BLUE, KC_BLUE)))),
  titlePanel("Royals bullpen: strike-throwing check"),
  sidebarLayout(
    sidebarPanel(
      width = 3,
      selectInput("pitcher", "Reliever", choices = choices),
      radioButtons("stand", "Batter side (zone map)", c("Both" = "B", "vs RHB" = "R", "vs LHB" = "L"),
                   inline = TRUE),
      hr(),
      p(class = "note", "F-Strike% = share of PAs that start with a strike or ball in play.",
        "The model estimate adjusts for sample size, platoon, runners, inning and catcher."),
      p(class = "note", "CSAE = called strikes above what a league-average pitcher and catcher get",
        "on the same pitches, per 100 taken pitches within 3 inches of the zone edge.")
    ),
    mainPanel(
      width = 9,
      tabsetPanel(
        tabPanel("First pitch",
                 h3("Is his first-pitch strike rate a real problem?"),
                 div(class = "takeaway", textOutput("fs_text")),
                 plotOutput("fs_plot", height = "360px"),
                 tableOutput("fs_table")),
        tabPanel("Borderline calls",
                 h3("Where does he gain or lose strike calls?"),
                 div(class = "takeaway", textOutput("edge_text")),
                 fluidRow(column(7, plotOutput("zone_plot", height = "440px")),
                          column(5, tableOutput("edge_table")))),
        tabPanel("Leak map check",
                 h3("Does shrinking F-Strike% change his leak-map quadrant?"),
                 tableOutput("rescore_table"),
                 p(class = "note", "Execution score = league percentile of Zone%, F-Strike%, 3PS%, Kill%,",
                   "Chase% and BB% (inverted), the same rule as the Step 6 leak map."))
      )
    )
  )
)

server <- function(input, output, session) {
  sel <- reactive(as.numeric(input$pitcher))
  me <- reactive(kc |> filter(pitcher == sel()))

  output$fs_text <- renderText(me()$takeaway)

  output$fs_plot <- renderPlot({
    d <- kc |> mutate(is_me = pitcher == sel()) |> arrange(brms_pct) |>
      mutate(name = factor(name, levels = name))
    ggplot(d, aes(y = name)) +
      geom_vline(xintercept = league_avg, linetype = "dashed", color = LEAGUE_GRAY) +
      geom_linerange(aes(xmin = brms_lo, xmax = brms_hi, alpha = is_me), color = KC_BLUE, linewidth = 2.2) +
      geom_point(aes(x = f_strike_pct), shape = 21, fill = "white", color = "gray30", size = 2.4) +
      geom_point(aes(x = brms_pct, alpha = is_me), color = KC_BLUE, size = 3) +
      scale_alpha_manual(values = c(`TRUE` = 1, `FALSE` = 0.3), guide = "none") +
      labs(x = "First-pitch strike %", y = NULL,
           caption = "Hollow = raw. Blue = model estimate with interval. Dashed = league-average reliever.") +
      theme_minimal(base_size = 13)
  })

  output$fs_table <- renderTable({
    m <- me()
    data.frame(
      `Relief PA` = m$pa, `Raw F-Strike%` = m$f_strike_pct, `Model F-Strike%` = m$brms_pct,
      Interval = sprintf("%.1f to %.1f (%s)", m$brms_lo, m$brms_hi, m$interval_source),
      `League avg` = league_avg, `Chance truly below avg` = sprintf("%.0f%%", 100 * m$prob_below_avg),
      check.names = FALSE
    )
  })

  my_reg <- reactive(reg |> filter(pitcher == sel()))
  output$edge_text <- renderText({
    r <- my_reg()
    edge_takeaway(r$edge_region, r$csae_per100, r$taken)
  })

  output$zone_plot <- renderPlot({
    m <- me()
    throws <- edge$p_throws[edge$pitcher == sel()][1]
    sides <- if (input$stand == "B") c("R", "L") else input$stand
    g <- grid |> filter(hand %in% paste0(throws, "HP v ", sides, "HB")) |>
      group_by(plate_x, plate_z_norm) |> summarise(p_strike = mean(p_strike), .groups = "drop")
    pts <- edge |> filter(pitcher == sel(), stand %in% sides) |>
      mutate(result = ifelse(called_strike == 1, "Called strike", "Ball"),
             surprise = called_strike - p_league)
    ggplot() +
      geom_contour(data = g, aes(plate_x, plate_z_norm, z = p_strike), breaks = 0.5,
                   color = "gray30", linewidth = 0.8) +
      annotate("rect", xmin = -0.83, xmax = 0.83, ymin = 0, ymax = 1, fill = NA, color = "gray60",
               linetype = "dotted") +
      geom_point(data = pts, aes(plate_x, plate_z_norm, color = surprise, shape = result),
                 size = 2.2, alpha = 0.85) +
      scale_color_gradient2(low = "#B03A2E", mid = "gray85", high = KC_BLUE, midpoint = 0,
                            limits = c(-1, 1), name = "Call vs.\nexpected") +
      scale_shape_manual(values = c(`Called strike` = 16, Ball = 1), name = NULL) +
      coord_fixed(ratio = 1.8, xlim = c(-1.3, 1.3), ylim = c(-0.4, 1.4)) +
      labs(x = "Horizontal (ft, catcher's view)", y = "Height (0 = bottom, 1 = top of zone)",
           caption = "Line = league 50% called-strike line for his hand. Blue = strike he wasn't expected to get.") +
      theme_minimal(base_size = 12)
  })

  output$edge_table <- renderTable({
    my_reg() |>
      transmute(Edge = edge_region, `Taken pitches` = taken, `CSAE per 100` = csae_per100) |>
      arrange(desc(`CSAE per 100`))
  })

  output$rescore_table <- renderTable({
    r <- rescore |> filter(pitcher == sel(), group == "KC reliever")
    if (nrow(r) == 0) return(data.frame(Note = "Not in the Step 6 leak map."))
    data.frame(
      `Raw F-Strike% pctile` = r$f_strike_pct_pctile, `Model F-Strike% pctile` = r$f_strike_model_pctile,
      `Execution score (raw)` = r$execution_score_raw, `Execution score (model)` = r$execution_score_model,
      `Stuff score` = r$stuff_score, `Quadrant (raw)` = r$quadrant_raw, `Quadrant (model)` = r$quadrant_model,
      check.names = FALSE
    )
  })
}

shinyApp(ui, server)
