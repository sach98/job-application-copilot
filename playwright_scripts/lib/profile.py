import json

from lib.paths import PROFILE_DIR

PROFILE_PATH = PROFILE_DIR / "candidate_profile_data.json"
ANSWERS_PATH = PROFILE_DIR / "answers.md"

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
