"""Central configuration for the IPL Analytics Engine."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
MODELS_DIR = DATA_DIR / "models"
DB_DIR = PROJECT_ROOT / "db"

DB_PATH = DB_DIR / "ipl_analytics.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Cricsheet IPL JSON dump (fallback: synthetic generator)
CRICSHEET_IPL_URL = "https://cricsheet.org/downloads/ipl_json.zip"
CRICSHEET_ZIP = RAW_DIR / "ipl_json.zip"
CRICSHEET_EXTRACT_DIR = RAW_DIR / "ipl_json"

# Synthetic generation targets when Cricsheet is unavailable
SYNTHETIC_SEASONS = list(range(2008, 2025))
SYNTHETIC_MATCHES_PER_SEASON = 60
TARGET_MIN_BALLS = 250_000

RANDOM_SEED = 42

# Canonical franchise names used across ETL / analytics / ML
FRANCHISES = [
    "Chennai Super Kings",
    "Mumbai Indians",
    "Royal Challengers Bangalore",
    "Kolkata Knight Riders",
    "Rajasthan Royals",
    "Delhi Capitals",
    "Punjab Kings",
    "Sunrisers Hyderabad",
    "Gujarat Titans",
    "Lucknow Super Giants",
]

VENUES = [
    ("Wankhede Stadium", "Mumbai"),
    ("M. A. Chidambaram Stadium", "Chennai"),
    ("M. Chinnaswamy Stadium", "Bengaluru"),
    ("Eden Gardens", "Kolkata"),
    ("Sawai Mansingh Stadium", "Jaipur"),
    ("Arun Jaitley Stadium", "Delhi"),
    ("IS Bindra Stadium", "Mohali"),
    ("Rajiv Gandhi Intl. Stadium", "Hyderabad"),
    ("Narendra Modi Stadium", "Ahmedabad"),
    ("BRSABV Ekana Stadium", "Lucknow"),
    ("DY Patil Stadium", "Navi Mumbai"),
    ("Brabourne Stadium", "Mumbai"),
]

TEAM_ALIASES = {
    "delhi daredevils": "Delhi Capitals",
    "delhi capitals": "Delhi Capitals",
    "kings xi punjab": "Punjab Kings",
    "punjab kings": "Punjab Kings",
    "rising pune supergiant": "Rising Pune Supergiant",
    "rising pune supergiants": "Rising Pune Supergiant",
    "royal challengers bengaluru": "Royal Challengers Bangalore",
    "royal challengers bangalore": "Royal Challengers Bangalore",
    "deccan chargers": "Deccan Chargers",
    "gujarat lions": "Gujarat Lions",
    "pune warriors": "Pune Warriors",
    "kochi tuskers kerala": "Kochi Tuskers Kerala",
}

for directory in (RAW_DIR, PROCESSED_DIR, EXPORTS_DIR, MODELS_DIR, DB_DIR):
    directory.mkdir(parents=True, exist_ok=True)
