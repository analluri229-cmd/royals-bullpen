"""Shared paths, column lists and thresholds for the Royals bullpen project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_MANUAL = ROOT / "data" / "manual"
DATA_PROCESSED = ROOT / "data" / "processed"
OUT_TABLES = ROOT / "outputs" / "tables"
OUT_FIGURES = ROOT / "outputs" / "figures"

SEASON = 2026
KC = "KC"  # Statcast team abbreviation (FanGraphs uses "KCR")

STATCAST_CSV_GZ = DATA_RAW / "statcast_2026.csv.gz"
STATCAST_PARQUET = DATA_RAW / "statcast_2026.parquet"
PITCHES_PARQUET = DATA_PROCESSED / "pitches_2026.parquet"

# Step 3 keep list (CLAUDE.md, Part 3, Step 3).
KEEP_COLUMNS = [
    "game_pk", "game_date", "game_type", "home_team", "away_team", "inning",
    "inning_topbot", "at_bat_number", "pitch_number", "pitcher", "player_name",
    "p_throws", "stand", "pitch_type", "release_speed", "release_pos_x",
    "release_pos_z", "release_extension", "arm_angle", "pfx_x", "pfx_z",
    "plate_x", "plate_z", "vx0", "vy0", "vz0", "ax", "ay", "az", "sz_top",
    "sz_bot", "zone", "balls", "strikes", "description", "events", "type",
    "release_pos_y", "batter", "fielder_2", "estimated_woba_using_speedangle",
    "delta_run_exp", "launch_speed", "launch_angle", "launch_speed_angle",
    "bb_type", "bat_speed", "swing_length", "woba_value",
    "estimated_ba_using_speedangle", "bat_score", "post_bat_score", "on_1b",
    "on_2b", "on_3b", "outs_when_up", "hit_location",
]
# Kept when present: umpire (pattern 10), age_pit (Step 6 age flag).
# "inning" is not in the spec list but is needed for outs/IP by half-inning.
OPTIONAL_COLUMNS = ["umpire", "age_pit"]

# Step 1 thresholds.
MIN_RELIEF_IP = 20.0
MIN_RELIEF_PITCHES = 300
MIN_PITCHES_PER_TYPE = 50
