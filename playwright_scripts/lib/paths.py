"""Single source of truth for the JobHunt data root.

Every script resolves its paths from JOBHUNT_ROOT so the repo can be checked out and run
anywhere. Set the JOBHUNT_ROOT environment variable to relocate the whole tree. The
default keeps the historical layout (~/JobHunt) so existing installs are unaffected.
"""

from __future__ import annotations

import os
from pathlib import Path

JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT") or (Path.home() / "JobHunt"))

APPLICATIONS_DIR = JOBHUNT_ROOT / "applications"
PROFILE_DIR = JOBHUNT_ROOT / "profile"
PROMPTS_DIR = JOBHUNT_ROOT / "prompts"
SCREENSHOTS_DIR = JOBHUNT_ROOT / "screenshots"
BROWSER_PROFILE_DIR = JOBHUNT_ROOT / ".browser-profile" / "comet"
