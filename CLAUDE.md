# CLAUDE.md: Royals Bullpen Revitalization

Claude Code reads this file every session. The full project spec (Parts 1-5 from the Word doc) is below the project rules.

## Project rules (decided 2026-10-31)
- Project root: `C:\Users\themi\source\royals-bullpen` (kept outside OneDrive on purpose). Open this folder in VS Code.
- Allowed folders: this project, `C:\Users\themi\source\repos`, and `C:\Users\themi\OneDrive\Documents\Code stuff`. Never touch music, FL Studio, audio or video files.
- Use real data only. Never use synthetic class data.
- Language: Python 3.11+ in `.venv` (Windows: `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`).
- Caching: every raw pull is saved to `data/raw`. Scripts check for an existing file before re-downloading.
- No baseball skill exists. All baseball metrics (VAA, LiVAA, tunneling, 3PS%, Kill%, the sequencing patterns) are coded from Part 3 and Part 4 below, and each one gets a unit test in `tests/`.
- Sequencing scope: build the Core patterns first. The Stretch patterns (show-me pitch, cold-zone funnel, umpire sequencing) get cut or labeled "directional" if time is short.
- Deck: build a Claude Slides artifact first, then a PowerPoint (.pptx) version. Both are needed.
- Royals blue `#004687` for KC, gray for league. Figures are 300 dpi PNGs in `outputs/figures`.
- Record deadline: 2026-11-01.

---

Purpose: an actionable spec for building this project with Claude Code in VS Code. Part 1 is the project brief. Part 2 is the analysis framework. Part 3 is the step-by-step build. Part 4 defines every metric. Part 5 lists open items to verify.

# Part 1 — Project Brief

## Q1 — Role

***What role / job are you building this project for?***

*Baseball Analyst / Pitching Development.*

## Q2 — Audience

***Who is the audience you're presenting to (e.g., Hiring Team, Player, Co-worker...)?***

*A hiring team / front office.*

## Q3 — Core Question

***What single, specific question are you trying to answer through this project? Start with Which, How, Why, or What.***

*How should the Royals revitalize their bullpen — which relievers are fixable, what exactly should be fixed, and who should be replaced?*

## Q4 — Situation

***Briefly define the situation or problem you are evaluating.***

*The Royals' position players are not the main problem in 2026; the bullpen is. The working hypothesis is an aging relief corps with velocity and command issues. This project tests that hypothesis by splitting each reliever's performance into Stuff and Execution, finding where each one leaks, and deciding whether the leak is fixable or the pitcher should be replaced.*

## Q5 — Evidence

***What data or evidence proves this problem or opportunity is real?***

*All team rankings use FanGraphs (2026 regular season) so every number comes from one source. Starting points to verify in Part 3, Step 2: offense 12th, fielding 8th, bullpen 28th. The full outcome table (reliever WAR, ERA, FIP, xFIP, SIERA, K-BB%, WHIP) will be pulled and ranked 1–30 by the pipeline.*

## Q6 — Benchmarks

***What benchmark, before-and-after view, or comparable case makes the problem or opportunity easy to see?***

*Two benchmark layers. (1) Outcome layer — where the bullpen ranks among 30 teams on FanGraphs reliever stats: WAR, ERA, FIP, xFIP, SIERA, K%, BB%, K-BB%, WHIP, HR/9. This proves the problem. (2) Diagnostic layer — each Royals reliever compared with the league-average reliever on Stuff (velocity, shape, arm angle, release, VAA/LiVAA, Stuff+) and Execution (Zone%, F-Strike%, 3PS%, Kill%, BB%, K%, count-based location, pitch mix, sequencing, Location+). This explains the problem. Historical context: since the 2015 World Series the Royals have one playoff appearance (2024, won the Wild Card Series). Verify the 2016–2026 combined record and yearly FanGraphs pitching ranks before using them — the earlier note of “no winning seasons” is incorrect (2024 was a winning season).*

## Q7 — Relevance

***How is this relevant to the hiring team(s) receiving this project?***

*It shows I can diagnose a pitching staff the way a pitching department does — separating stuff from execution, judging what is fixable through development versus acquisition, and backing roster decisions with public data. Many teams struggle to build effective bullpens, so this is a common front-office need.*

## Q8 — Visual Format

***In the video you will create, a visual needs to be included (after your 30 second introduction - face center of the camera). What type of visual will you be including (e.g., 1-page visual report, 5-slide deck, scouting report, dashboard concept)?***

*A 5-slide deck (Part 1, Q9) plus a scouting-report appendix covering free-agent targets, prospects, and development/training plans for fixable relievers.*

## Q9 — Deck Structure

***What are the 3–5 core parts of your visual deliverable (e.g., 1. Frame Problem, 2. Benchmark Visual, 3. Proposed Fix, 4. Recommendation)?***

1.  The Problem — FanGraphs bullpen rankings vs. all 30 teams, set against a competitive offense and defense.

2.  Benchmark: Stuff vs. Execution — the bullpen vs. the league-average reliever, then a per-reliever leak map.

3.  Diagnosis & Proposed Fix — each reliever tagged as a fixable stuff leak (pitch add/shape change), a fixable execution leak (zone attack, 3PS, count plan, sequencing/tunneling plan), or replace.

4.  Tradeoffs — develop vs. acquire: cost, timeline, risk, and roster spots.

5.  Recommendations — keep / fix / replace list, specific free-agent and prospect targets matched to each leak, and development plans.

## Q10 — Timeline

***When are you sitting down to start building, and what is your deadline date to record the project?***

*Started 10/27; record by 11/1. Plan: 10/28–29 data pull and metrics (Steps 0–5), then Core sequencing metrics (Step 5A); 10/30 leak map and targets (Steps 6–7), plus Stretch sequencing metrics if time allows; 10/31 visuals and deck (Step 8–9); 11/1 record.*

# Part 2 — Analysis Framework: Stuff + Execution

Core principle (from mentor): Stuff + Execution = long-term performance. Outcome stats (ERA, FIP, WHIP) show that the bullpen is bad; Stuff and Execution explain why. Analyze the bullpen collectively first, then each reliever, to find who leaks where.

## Stuff — what the pitches physically do

- Velocity (average and max) by pitch type

- Pitch shape: induced vertical break (IVB) and horizontal break (HB)

- Arm angle

- Release metrics: release height, release side, extension

- Vertical approach angle (VAA) and location-independent VAA (LiVAA)

- FanGraphs Stuff+ (overall and by pitch)

## Execution — how well the pitches are used

- Attacking the zone early: Zone%, first-pitch strike % (F-Strike%), 3PS%

- Finishing hitters: Kill%, K%, Whiff%, CSW%

- Free passes: BB%

- Locations based on count (ahead / even / behind / two strikes)

- Pitch mix and mixing by count and batter handedness; sequencing

- FanGraphs Location+ as a summary execution check

## Sequencing & deception — how pitches work together

Sequencing and deception explain why the same stuff plays up or down. Definitions below follow the video “Every MLB Pitch Sequence Explained (How Pitchers Set Up the Hitter to Fail)” (SidelinePOV), numbered as in the video; two extra concepts not in the video are listed last. Part 3, Step 5A turns each one into two measurable readouts for every pitcher (Royals relievers, free-agent targets, prospects): How often he uses the pattern, and How well it works compared with his baseline.

- 1\. The ladder — a fastball followed by another fastball about 4 inches higher, with the same velocity and arm slot. The hitter's swing is calibrated to the last pitch's height, not its type, so he swings under the next one. Requires a pitcher who trusts an elevated fastball.

- 2\. Tunneling — two different pitches leave the same arm slot and release height on the same initial path and look identical for the first 20–25 feet. The hitter has to commit (about 150 ms) before they separate, so he's committed to a pitch that is no longer coming.

- 3\. The show-me pitch — early in an at-bat (often the first pitch), a pitch type he almost never throws in that count, or barely at all. It doesn't need to be good and may never be thrown again; its job is to give the hitter one more possibility to account for. Low success on the pitch itself; the value shows up in the pitches after it.

- 4\. Backwards sequencing — offspeed or breaking balls in fastball (hitter's) counts, such as a 2-0 curveball for a strike or a 3-1 changeup, with the fastball coming late. Works because hitters sit on fastballs when they're ahead.

- 5\. The 0-2 waste pitch — a deliberately non-competitive pitch at 0-2 (fastball at the eyes, slider in the dirt, well off the plate). The hitter either chases, or takes it and still faces the full arsenal with two strikes.

- 6\. The double down — the same pitch in the same location twice in a row. A hitter who read the first one correctly but mistimed it expects something new and repeats the same mistake.

- 7\. Pitching backwards to the scouting report — every hitter has a cold zone where he does no damage. The pitcher builds the at-bat as a funnel toward that spot, using earlier pitches to get the hitter there off balance. This is about the hitter's weak spot, not about the pitcher breaking his own tendencies.

- 8\. The two-strike chase — with two strikes, each consecutive pitch is moved slightly farther off the zone than the last (the video's example: about 8 inches over four pitches). The hitter's protect-the-plate instinct keeps him expanding. Associated more with control pitchers than power arms.

- 9\. Setup fastball → put-away breaking ball — a competitive fastball early in the count, credible enough that the hitter must respect it, sets his timing; then the breaking ball takes the velocity away. The video calls this the foundation the other patterns build on.

- 10\. Sequencing the umpire — repeatedly throwing the same borderline pitch (e.g., about 2 inches off the outside corner) early, so the umpire anchors on calling it a strike and keeps calling it later. Targets the umpire, not the hitter.

- Not in the video — Delivery: the same release point, arm slot, and extension on every pitch, so nothing tips the pitch. This is the prerequisite for tunneling.

- Not in the video — Two-strike approach (“two-strike clause”): what changes in his pitch mix and locations once he reaches two strikes. The video's closest pattern is \#8.

## Diagnostic questions for each reliever

- Is the leak Stuff or Execution?

- If Stuff: is it the fastball or the offspeed/breaking ball? Can he fix it or add a shape to help?

- If Execution: too many walks? Not enough strikeouts? Not attacking the zone early? Poor count-based locations or predictable sequencing? Poor tunneling, no setup pitch, or no two-strike putaway plan?

- Is the leak fixable (development) — or should the Royals move on and acquire a replacement?

# Part 3 — Claude Code Build Instructions

Work through the steps in order. Each step lists its inputs, what to compute, and the output file. Do not move to the next step until the output file exists and has been sanity-checked.

## Step 0 — Project setup

- Create a project folder royals-bullpen/ with: data/raw, data/manual, data/processed, src, notebooks, outputs/figures, outputs/tables.

- Python 3.11+ virtual environment. Install: pandas, numpy, pybaseball, pyarrow, matplotlib, seaborn, scipy, statsmodels, jupyter.

- Caching rule: save every raw pull to data/raw (parquet or CSV); scripts check for an existing file before re-downloading.

- Save this spec as CLAUDE.md at the project root so Claude Code reads it every session.

## Step 1 — Scope and population

- Season: 2026 MLB regular season only (Statcast game_type == "R").

- Reliever: any pitcher appearance that is not the team's first pitcher of the game (find the first pitcher per team per game_pk in Statcast).

- Royals relievers: KC pitchers with at least 20 relief IP or 300 relief pitches. List lower-sample relievers separately and flag them as small samples.

- League comparison group: all MLB relievers meeting the same threshold.

- Per-pitch-type metrics require at least 50 pitches of that type; otherwise report "insufficient sample."

## Step 2 — Outcome layer: FanGraphs rankings

- Team reliever stats for all 30 teams: WAR, ERA, FIP, xFIP, SIERA, K%, BB%, K-BB%, WHIP, HR/9. Rank 1–30 (1 = best; lower-is-better stats ranked ascending).

- Source: FanGraphs team leaderboard → Pitching → split: Relievers → 2026. If pybaseball's FanGraphs functions fail (FanGraphs often blocks scraping), export the CSV manually to data/manual/fg_team_relievers_2026.csv.

- Player-level FanGraphs reliever stats, including Stuff+, Location+, and Pitching+: try pybaseball.pitching_stats(2026, qual=0); fall back to a manual export at data/manual/fg_relievers_2026.csv.

- Context ranks for Q5: team offense (wRC+) and defense (Def) from FanGraphs team leaderboards.

- Output: outputs/tables/team_bullpen_ranks_2026.csv. Print the Royals row.

## Step 3 — Pitch-level data: Statcast

- Pull with pybaseball.statcast(start_dt, end_dt) in 7-day chunks across the 2026 regular season; save each chunk, then combine into data/raw/statcast_2026.parquet.

- Keep: game_pk, game_date, game_type, home_team, away_team, inning_topbot, at_bat_number, pitch_number, pitcher, player_name, p_throws, stand, pitch_type, release_speed, release_pos_x, release_pos_z, release_extension, arm_angle, pfx_x, pfx_z, plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, sz_top, sz_bot, zone, balls, strikes, description, events, type, release_pos_y, batter, fielder_2, estimated_woba_using_speedangle, delta_run_exp, launch_speed, launch_angle, launch_speed_angle, bb_type, bat_speed, swing_length, woba_value, estimated_ba_using_speedangle, bat_score, post_bat_score, on_1b, on_2b, on_3b, outs_when_up, hit_location.

- Derive pitching team (home team pitches in the top of the inning) and the relief flag from Step 1.

- If time allows, also pull 2024 and 2025 for velocity-trend checks in Step 6.

## Step 4 — Stuff metrics

- Per reliever × pitch type: usage%, average and max velocity, IVB = pfx_z × 12 (inches), HB = pfx_x × 12, arm angle, release height, release side, extension, VAA, LiVAA, FanGraphs Stuff+.

- VAA (degrees, measured at the front of home plate, y = 17/12 ft): vy_f = −√(vy0² − 2·ay·(50 − 17/12)); t = (vy_f − vy0) / ay; vz_f = vz0 + az·t; VAA = −arctan(vz_f / vy_f) × 180/π.

- LiVAA: across league relievers, regress VAA on plate_z separately for fastballs, breaking balls, and offspeed. LiVAA = VAA − slope × (plate_z − league mean plate_z). This removes the effect of pitch height so pitchers can be compared on approach angle alone. Confirm the method with mentor.

- Convert each value to a percentile (0–100) against league relievers with the same pitch type and handedness. Fastball metrics are the priority.

- Output: outputs/tables/stuff_by_pitch.csv.

## Step 5 — Execution metrics

- Per reliever, each with a league percentile: Zone% (Statcast zones 1–9), F-Strike%, 3PS%, Kill%, K%, BB%, Whiff%, Chase%, CSW%, FanGraphs Location+ (definitions in Part 4).

- Count-based locations: Zone% and pitch usage by count state — ahead (strikes \> balls), even, behind, two strikes — and by batter handedness.

- Mixing: pitch-usage entropy by count state (higher = less predictable); share of the most-used pitch in two-strike counts.

- Sequencing: rate of back-to-back same pitch type, most common two-pitch sequences, and Whiff% on the second pitch of each sequence.

- Output: outputs/tables/execution_by_reliever.csv.

## Step 5A — Sequencing and deception metrics

Who: run this step for every MLB reliever (league baseline), every Royals reliever, every free-agent target, and every prospect with pitch-tracking data (Step 7).

Setup: sort pitches by game_pk, at_bat_number, pitch_number. Use groupby + shift to attach the previous pitch's type, location, velocity, and result to each pitch. Pitch groups: FB = FF/SI/FC; BRK = SL/ST/CU/KC/SV; OFF = CH/FS/FO. Zone edges: plate_x ±0.83 ft; sz_bot to sz_top. “Distance off the zone” = inches outside the nearest edge (0 if in the zone). Hitter's counts = 1-0, 2-0, 2-1, 3-0, 3-1.

Standard readout for every pattern — this is what gets displayed:

- How often: opportunities (situations where the pattern was possible), uses, usage rate = uses ÷ opportunities, and a league percentile.

- How well: outcomes on pattern pitches vs. the pitcher's own baseline (the same pitch type in similar counts without the pattern). Lift = pattern − baseline, with a league percentile. Report all three outcome tiers below, not just one.

- Sample: pitch count behind every number. Flag any cell with fewer than 25 pattern pitches as small sample; Stretch patterns are directional only.

Outcome tiers — compute every tier for every pattern, so a pattern can be judged by whether it gets a swing and miss, weak contact, or the out:

- Tier 1 — Pitch result: take vs. swing; called strike, whiff, foul, ball in play (description). Metrics: Whiff%, CSW%, Chase%, called-strike rate.

- Tier 2 — Contact quality (balls in play only): Statcast batted-ball class from launch_speed_angle (1 = weak, 2 = topped, 3 = under, 4 = flare/burner, 5 = solid, 6 = barrel); Barrel%; Hard-hit% (exit velocity ≥ 95 mph); average exit velocity and launch angle; GB%; xwOBAcon (estimated_woba_using_speedangle on contact).

- Tier 2b — Bat tracking (MLB 2024+, swings only): bat speed, swing length, Squared-up% (exit velocity ÷ the maximum possible exit velocity for that bat speed and pitch speed; ≥ 80% = squared up), and Blast% (squared-up percentage × 100 + bat speed ≥ 164). Also Squared-up% per swing, so whiffs count as not squared up. Confirm the formulas against Baseball Savant's glossary.

- Tier 3 — PA result (from events + bb_type), reported as counts and rates per PA for every pattern:

  Hits: single, double, triple, home run; plus total hits, AVG, SLG, ISO, and total bases allowed.

  Outs: strikeout (swinging vs. looking, from the last pitch's description), groundout, flyout, lineout, popout (field_out / force_out / fielders_choice_out split by bb_type), sacrifice fly/bunt, double play (grounded_into_double_play, double_play, strikeout_double_play).

  Free passes and other: walk, intentional walk, hit by pitch, reached on error, catcher's interference.

  Run damage: runs scored on the play = post_bat_score − bat_score, used as the RBI proxy (it can include runs on errors or wild pitches, so label it “runs on play”). Also record base-out state before the PA (on_1b, on_2b, on_3b, outs_when_up) so damage with runners on can be shown separately.

  Value: wOBA (woba_value), xwOBA, xBA, and run value (delta_run_exp summed over the PA).

  Attribution: credit the PA result to every pattern used in that PA, and separately report the result when the pattern pitch itself ended the PA, so a setup pitch is not judged only by its own outcome.

- For each tier, the readout shows the pattern value, the baseline value, the lift, and the league percentile of the lift. A pattern that rarely gets whiffs but sharply cuts Barrel% or Squared-up% still counts as effective.

### Delivery (Core) — not in the video

- Definition: the same release point, arm slot, and extension on every pitch, so nothing tips the pitch; the prerequisite for tunneling.

- Detect: per pitch type, SD of release_pos_x, release_pos_z, release_extension, and arm_angle; gap between each secondary pitch's mean release point and the fastball's.

- How often: share of all pitches released within 2 inches of his fastball's mean release point.

- How well: release gap and SD vs. league percentile (smaller = better). Statcast can't see tempo or mechanics, so note video review as a follow-up.

### 1. The ladder (Core)

- Definition: a fastball followed by another fastball about 4 inches higher, same velocity and arm slot; the hitter's swing stays calibrated to the previous height and goes under the pitch.

- Detect: consecutive FB → FB in the same PA where the second pitch's plate_z is at least 4 inches (0.33 ft) higher and velocity is within 1.5 mph. Tag a “top-rung” ladder when the second pitch finishes in the upper third of the zone or above it.

- How often: ladder pitches ÷ consecutive FB → FB pairs.

- How well: Whiff% and CSW% on the ladder pitch vs. his fastballs at the same height not preceded by a lower fastball.

### 2. Tunneling (Core)

- Definition: two different pitches leave the same slot on the same path and look identical for the first 20–25 feet; the hitter commits (about 150 ms) before they separate.

- Detect: consecutive pairs of different pitch types in the same PA. Rebuild each trajectory from the 9-parameter fit (vx0, vy0, vz0, ax, ay, az, release point). Measure the distance between the two pitches at the decision point (default 23.8 ft from home plate; test 20 and 25 ft) and at the plate.

- How often: share of his different-type pairs that tunnel, defined as a tunnel differential below the league median for that pitch pair (e.g., FF → SL).

- How well: tunnel differential, plate differential, and break-to-tunnel ratio (plate ÷ tunnel; higher = better), plus Whiff% and Chase% on the second pitch of tunneled vs. non-tunneled pairs.

### 3. The show-me pitch (Stretch)

- Definition: early in the PA (often the first pitch), a pitch type he almost never throws in that count; it isn't repeated, and its job is to occupy the hitter's mind, not to win that pitch.

- Detect: pitch 1 or 2 of a PA, where that pitch type is 5% or less of his season usage in that count, and the type is not thrown again in that PA.

- How often: show-me pitches per 100 PAs.

- How well: do not grade the show-me pitch itself (the video says its own success rate is poor). Compare Whiff%, CSW%, and xwOBA on the rest of that PA, and on later PAs against the same batter in that game, vs. his PAs without one.

### 4. Backwards sequencing (Core)

- Definition: offspeed or breaking balls in hitter's counts (e.g., 2-0 curveball for a strike, 3-1 changeup), fastball late; exploits hitters sitting on fastballs when ahead.

- Detect: BRK/OFF pitches in hitter's counts. Secondary: PAs that open with BRK/OFF and finish with a fastball.

- How often: non-fastball share in hitter's counts vs. league relievers and vs. his own overall non-fastball share.

- How well: strike rate (CSW% plus fouls and balls in play), xwOBA, and run value per 100 on backwards pitches vs. his fastballs in the same counts.

### 5. The 0-2 waste pitch (Core)

- Definition: a deliberately non-competitive pitch at 0-2 (fastball at the eyes, slider in the dirt, well off the plate); the hitter either chases or still faces the full arsenal with two strikes.

- Detect: 0-2 pitches at least 4 inches off the zone.

- How often: waste pitches ÷ 0-2 pitches.

- How well: Chase% and Whiff% on waste pitches; results of the next pitch after a waste vs. after a competitive 0-2 pitch; xwOBA allowed on 0-2 pitches in the zone (the cost of not wasting).

### 6. The double down (Core)

- Definition: the same pitch in the same location twice in a row; a hitter who read the first one but mistimed it repeats the mistake.

- Detect: consecutive pitches with the same pitch type, locations within 4 inches, where the first pitch was a strike (called, swinging, or foul), matching the video's example. Log all same-spot repeats as a secondary count.

- How often: double-downs ÷ pitches thrown right after a strike.

- How well: Whiff% and CSW% on the repeat vs. the first pitch, and vs. the same pitch type thrown after a different pitch.

### 7. Pitching backwards to the scouting report (Stretch)

- Definition: every hitter has a cold zone; the pitcher funnels the at-bat toward it, using earlier pitches to arrive there with the hitter off balance.

- Detect: build each batter's heat map from data before the PA (prior season plus season-to-date, so the map never uses future pitches): xwOBA and Whiff% by pitch group × location bucket (Statcast zones 1–14). Shrink small samples toward league average (minimum about 30 pitches per bucket). Cold zone = the batter's lowest-damage bucket(s).

- How often: share of his pitches in the batter's cold zone, and the funnel rate = PAs whose final pitch lands in the cold zone.

- How well: xwOBA and Whiff% on cold-zone pitches vs. his other pitches; outcomes of funneled PAs vs. non-funneled PAs.

### 8. The two-strike chase (Core)

- Definition: with two strikes, each consecutive pitch moves slightly farther off the zone than the last (about 8 inches over four pitches in the video); the hitter keeps expanding.

- Detect: an expanding sequence = 2+ consecutive two-strike pitches in a PA, each at least 1 inch farther off the zone than the previous, on the same side of the zone.

- How often: expanding sequences per 100 two-strike PAs, plus overall two-strike Chase%.

- How well: Chase% and Whiff% on pitches within an expanding sequence vs. his other two-strike out-of-zone pitches; K rate of PAs with an expanding sequence.

### Two-strike approach (Core) — not in the video

- Definition (“two-strike clause”): what changes in his mix and locations once he reaches two strikes.

- How often: change in pitch mix and Zone% from 0–1-strike counts to two-strike counts (usage of his best put-away pitch).

- How well: Kill% overall and by pitch type; Whiff% of the put-away pitch. Flags a pitcher with no put-away pitch or no change in approach.

### 9. Setup fastball → put-away breaking ball (Core)

- Definition: a competitive fastball early in the count, credible enough to be respected, sets the hitter's timing; then the breaking ball removes the velocity.

- Detect: a FB in the zone or within 2 inches of it, thrown before two strikes, followed later in the same PA by a BRK/OFF pitch with two strikes. Record the velocity gap between them.

- How often: share of his two-strike BRK/OFF pitches set up by a competitive fastball in that PA; plus fastball credibility (fastball usage and Zone% before two strikes).

- How well: Whiff%, Chase%, and K rate on the put-away pitch after a fastball setup vs. the same pitch without one; check whether results improve as the velocity gap grows.

### 10. Sequencing the umpire (Stretch)

- Definition: the same borderline pitch (e.g., about 2 inches off the outside corner) thrown repeatedly early, so the umpire anchors and keeps calling it a strike later.

- Detect: borderline band = 0–3 inches off the zone. Fit a league called-strike model on taken pitches (location, batter handedness, count) to get Called Strikes Above Expected (CSAE). A “campaign” = 2+ borderline pitches to the same edge earlier in the game.

- How often: share of his taken pitches in the borderline band, and the repeat-edge rate.

- How well: CSAE at that edge later in the game after earlier strike calls there vs. without. Control for catcher (fielder_2) and umpire (Statcast has no umpire ID; pull it from the MLB Stats API game feed). Relief outings are short, so also run this at team level (starter + bullpen, same umpire, same game).

### Output

- outputs/tables/sequencing_by_pitcher.csv in long format, one row per pitcher × pattern: pitcher_id, name, group (KC reliever / MLB reliever / free agent / prospect), pattern, opportunities, uses, usage_rate, usage_pctile, outcome_metric, pattern_value, baseline_value, lift, lift_pctile, n_pitches, sample_flag.

- outputs/tables/sequence_pairs.csv: pitch-pair level, for the tunnel, ladder, and sequencing plots.

## Step 6 — Leak map and fix-or-replace triage

- Stuff score = weighted average of Stuff percentiles (fastball 50%, best secondary 30%, other pitches 20%). Execution score = average percentile of Zone%, F-Strike%, 3PS%, Kill%, BB% (inverted), and Chase%.

- Classify with a 50th-percentile cut line: High Stuff / High Execution → Keep. Low Stuff / High Execution → Stuff fix (pitch design: new shape or new pitch). High Stuff / Low Execution → Execution fix (zone attack, count plan, mix, sequencing). Low / Low → Replace candidate. Use the Step 5A sequencing profile to make each Execution fix specific (e.g., “add an elevated-fastball setup before the sweeper,” “stop doubling down on 0-2”).

- For each reliever, name the specific leak: which pitch, which metric, and how far below league average.

- Sequencing triage, using How often vs. How well percentiles for each pattern: effective but underused → throw it more; used often but ineffective → cut back or fix the pitch it depends on; low on both for a Core pattern (e.g., no fastball setup, no put-away pattern) → coaching target. Name the top 1–2 patterns for each reliever's plan.

- Fixability flags: age 33+; fastball velocity down 1+ mph vs. 2024/2025; contract/control status (manual input: data/manual/royals_contracts.csv).

- Output: outputs/tables/leak_map.csv with columns: reliever, stuff_score, execution_score, quadrant, primary_leak, fixable (Y/N/?), recommended_action.

## Step 7 — Replacement targets

- Manual inputs: data/manual/fa_relievers_2026.csv (2026–27 free-agent relievers, e.g., from MLB Trade Rumors' free-agent list) and data/manual/royals_prospects.csv (from FanGraphs' The Board).

- Run Steps 4, 5, and 5A on each free agent. For prospects, use AAA Statcast pitch-tracking data where available (pybaseball's statcast() covers MLB only; export minor-league data from Baseball Savant's minors search to data/manual/aaa_statcast_2026.csv and verify which levels have tracking). Without tracking data, fall back to FanGraphs minor-league K%, BB%, and K-BB%, and mark sequencing as not available.

- Match targets to leaks: for each Replace candidate or hard-to-fix leak, list 2–3 targets who are strong in that exact area (e.g., a high-IVB / flat-VAA four-seamer, a left-hander with a sweeper, a high-Zone% strike-thrower).

- Sequencing match: when a reliever's leak is a sequencing pattern, prefer targets in the top third on both How often and How well for that pattern (e.g., a strong ladder fastball, an elite fastball-to-breaking-ball setup).

- Output: outputs/tables/targets.csv.

## Step 8 — Visuals

- Format: PNG, 300 dpi, saved to outputs/figures. Royals blue (#004687) for KC, gray for league.

- Slide 1: FanGraphs bullpen ranks across 30 teams (K-BB%, xFIP, WAR) with KC highlighted.

- Slide 2: Stuff score vs. Execution score scatter for all MLB relievers, KC relievers labeled, quadrant lines at 50.

- Slide 2: leak heatmap — Royals relievers (rows) × Stuff and Execution metrics (columns), colored by percentile.

- Slide 3: pitch movement plots (HB vs. IVB) for fix candidates over a league reference cloud.

- Slide 3: tunnel plot — catcher's-view trajectories for a fix candidate's best and worst pitch pairs, with the tunnel point marked.

- Slide 3: sequencing heatmap — previous pitch × next pitch with Whiff% in each cell; plus ladder and setup-FB → breaking-ball results vs. baseline.

- Slide 3: sequencing scorecard for each Royals reliever — one row per pattern, percentile bars for How often and How well (split into pitch result, contact quality, and PA result), pitch counts printed, small samples grayed out.

- Slide 3: frequency vs. effectiveness scatter for each Core pattern (x = How often percentile, y = How well percentile), KC relievers labeled; the top-left quadrant (effective but underused) is the coaching opportunity.

- Slide 5 and appendix: target and prospect sequencing cards using the same scorecard layout, so each target can be compared directly with the reliever he would replace.

- Appendix: CSAE edge map (called strikes above expected around the zone border) for umpire-sequencing candidates.

- Slide 4: develop-vs-acquire tradeoff table (cost, timeline, risk, roster spot).

- Slide 5 and appendix: fix-or-replace table and target comparison cards.

## Step 9 — Validation before presenting

- Royals reliever IP, K, and BB totals from Statcast match FanGraphs within about 2%.

- Every number on a slide traces to a file in outputs/tables.

- Small samples are flagged; no per-pitch metric is shown on fewer than 50 pitches.

- Every item in Part 5 is resolved or footnoted.

# Part 4 — Metric Definitions

| **Metric**                  | **Bucket**      | **Definition**                                                                                                                                                                                                           |
|-----------------------------|-----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Velocity                    | Stuff           | Release speed (mph), average and max, by pitch type.                                                                                                                                                                     |
| IVB / HB                    | Stuff           | Induced vertical break and horizontal break in inches (pfx_z × 12, pfx_x × 12).                                                                                                                                          |
| Arm angle                   | Stuff           | Statcast arm angle at release (degrees).                                                                                                                                                                                 |
| Extension                   | Stuff           | Distance in front of the rubber at release (ft).                                                                                                                                                                         |
| VAA                         | Stuff           | Vertical approach angle of the pitch entering the zone; flatter fastballs up in the zone generate more whiffs.                                                                                                           |
| LiVAA                       | Stuff           | VAA adjusted for pitch height, so approach angle can be compared independent of location.                                                                                                                                |
| Stuff+                      | Stuff           | FanGraphs model of pitch quality from physical characteristics; 100 = league average.                                                                                                                                    |
| Zone%                       | Execution       | Share of pitches in the strike zone (Statcast zones 1–9).                                                                                                                                                                |
| F-Strike%                   | Execution       | Share of PAs where the first pitch is a called strike, swinging strike, foul, or ball in play.                                                                                                                           |
| 3PS%                        | Execution       | 3-pitch strike rate: share of PAs where the pitcher reaches two strikes within the first three pitches, or the PA ends in an out within three pitches.                                                                   |
| Kill%                       | Execution       | Strikeouts ÷ PAs that reach a two-strike count (putaway rate).                                                                                                                                                           |
| K% / BB% / K-BB%            | Execution       | Strikeouts and walks per batter faced, and their difference.                                                                                                                                                             |
| Whiff% / Chase% / CSW%      | Execution       | Whiffs ÷ swings; swings at out-of-zone pitches ÷ out-of-zone pitches; called + swinging strikes ÷ pitches.                                                                                                               |
| Location+                   | Execution       | FanGraphs model of command/location quality; 100 = league average.                                                                                                                                                       |
| FIP / xFIP / SIERA          | Outcome         | ERA estimators based on strikeouts, walks, and home runs (xFIP normalizes HR/FB; SIERA adds batted-ball profile).                                                                                                        |
| Release consistency         | Deception       | SD of release point within a pitch type and release gap vs. the fastball; smaller = harder to read.                                                                                                                      |
| Tunnel / plate differential | Deception       | Distance between consecutive pitches at the tunnel point (≈23.8 ft) and at the plate; break-to-tunnel ratio = plate ÷ tunnel.                                                                                            |
| Ladder                      | Sequencing      | FB → FB in the same PA with the second pitch at least 4 inches higher at similar velocity; Whiff%/CSW% on the higher pitch vs. baseline.                                                                                 |
| Setup FB → BRK              | Sequencing      | Competitive fastball before two strikes, then a breaking/offspeed put-away pitch in the same PA; results vs. the same pitch without a setup.                                                                             |
| Backwards sequencing        | Sequencing      | Non-fastball share in hitter's counts (1-0, 2-0, 2-1, 3-0, 3-1) and its results vs. fastballs in those counts.                                                                                                           |
| Double down                 | Sequencing      | Same pitch type within 4 inches, right after a strike; results on the repeat vs. baseline.                                                                                                                               |
| 0-2 waste                   | Sequencing      | Share of 0-2 pitches at least 4 inches off the zone, their Chase%, and the next pitch's result.                                                                                                                          |
| Two-strike chase            | Sequencing      | Expanding sequences: consecutive two-strike pitches each 1+ inch farther off the zone; Chase%/Whiff% and K rate.                                                                                                         |
| Show-me pitch               | Sequencing      | Early-PA pitch type thrown 5% or less in that count and not repeated in the PA; graded by results of the pitches after it.                                                                                               |
| CSAE                        | Sequencing      | Called Strikes Above Expected from a league called-strike model; used to test sequencing the umpire.                                                                                                                     |
| Cold-zone funnel            | Sequencing      | Pitching backwards to the scouting report: share of pitches, and of PA-ending pitches, in the batter's cold zone; xwOBA on them vs. other pitches.                                                                       |
| Barrel% / Hard-hit%         | Contact quality | Barrel = Statcast launch_speed_angle 6 (ideal exit velocity + launch angle). Hard-hit = exit velocity ≥ 95 mph. Both per ball in play.                                                                                   |
| xwOBAcon                    | Contact quality | Expected wOBA on contact from exit velocity and launch angle.                                                                                                                                                            |
| Squared-up%                 | Contact quality | Exit velocity ÷ max possible exit velocity for the bat speed and pitch speed; ≥ 80% counts as squared up (bat tracking, MLB 2024+).                                                                                      |
| Blast%                      | Contact quality | Swing that is both fast and squared up: squared-up % × 100 + bat speed ≥ 164 (bat tracking).                                                                                                                             |
| PA result                   | Outcome         | Hit type (1B, 2B, 3B, HR), out type (K swinging/looking, groundout, flyout, lineout, popout, double play, sac), BB/HBP, runs on the play (RBI proxy), AVG/SLG, wOBA, xwOBA, and run value for the full plate appearance. |

# Part 5 — Open Items to Verify

- Confirm the 3PS definition with mentor (this spec uses 3-pitch strike rate, not "three-pitch sequencing").

- Confirm the LiVAA method with mentor.

- Verify FanGraphs 2026 ranks: offense 12th, fielding 8th, bullpen 28th (Step 2 output replaces these).

- Verify the 2016–2026 combined record and yearly pitching ranks; 2024 was a winning, playoff season.

- Build the free-agent, prospect, and contract input files (Step 7, Step 6).

- “Two-strike clause” is not one of the video's 10 patterns; this spec treats it as the pitcher's two-strike approach (the video's closest is \#8, the two-strike chase). Confirm.

- Thresholds in Step 5A: from the video — 4-inch ladder step, 20–25 ft tunnel window, about 2 inches off the corner for umpire sequencing; set by this spec — 4-inch double down, 4-inch waste pitch, 1-inch expansion step, 5% show-me usage, 25-pitch sample flag. Check sensitivity before presenting.

- Reliever samples are small for pair-level metrics; show Stretch metrics as directional, with pitch counts.

- Umpire IDs are not in Statcast; pull them from the MLB Stats API game feed before running pattern 10.

- Bat-tracking metrics (bat speed, Squared-up%, Blast%) exist for MLB only from 2024 on and likely not for minor-league prospects; confirm the Savant formulas, and fall back to Barrel%, Hard-hit%, and xwOBAcon where bat tracking is missing.
