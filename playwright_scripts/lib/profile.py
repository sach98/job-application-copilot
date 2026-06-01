import json
from pathlib import Path

PROFILE_PATH = Path.home() / "JobHunt" / "profile" / "candidate_profile_data.json"
ANSWERS_PATH = Path.home() / "JobHunt" / "profile" / "answers.md"

def load_profile() -> dict:
    """Loads the parsed profile JSON."""
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(f"Profile JSON not found at {PROFILE_PATH}")
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_answers() -> str:
    """Loads the raw answers.md text."""
    if not ANSWERS_PATH.exists():
        return ""
    with open(ANSWERS_PATH, "r", encoding="utf-8") as f:
        return f.read()
