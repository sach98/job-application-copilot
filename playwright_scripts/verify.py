#!/usr/bin/env python3
"""Skeptical audit + fit pass on a TAILORED resume (grader ≠ author).

Given the master resume, the tailored resume, and the JD, returns:
  {clean: bool, fabrications: [...], fit_score: float, missing_for_fit: [...], reasoning_caveman: str}

`clean` is the correctness gate (no fabrication vs master); `fit_score` is the honest
tailored fit. The caller keeps a job only when clean AND fit_score >= threshold.
Uses Sonnet (correctness-critical), separate from the tailoring call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.sonnet import call_claude

HOME = Path.home()
PROFILE_DIR = HOME / "JobHunt" / "profile"
PROMPTS_DIR = HOME / "JobHunt" / "prompts"
VERIFY_PROMPT = PROMPTS_DIR / "verify_resume.md"
MASTER_RESUME = PROFILE_DIR / "master_resume.md"
VERIFY_MODEL = "claude-sonnet-4-6"


def log(msg: str) -> None:
    print(f"[verify] {msg}", file=sys.stderr, flush=True)


def _master_text() -> str:
    return MASTER_RESUME.read_text(encoding="utf-8") if MASTER_RESUME.exists() else ""


def run(role: dict, tailored_resume: str) -> dict:
    """Audit + score a tailored resume. Returns the verifier dict (see module docstring)."""
    payload = {
        "master_resume": _master_text(),
        "tailored_resume": tailored_resume or "",
        "jd": role.get("jd_text") or role.get("jd") or "",
        "company": role.get("company") or "",
        "role": role.get("role") or role.get("title") or "",
    }
    out = call_claude(VERIFY_PROMPT, payload, model=VERIFY_MODEL)
    return {
        "clean": bool(out.get("clean", False)),
        "fabrications": out.get("fabrications") or [],
        "fit_score": float(out.get("fit_score") or 0.0),
        "missing_for_fit": out.get("missing_for_fit") or [],
        "reasoning_caveman": out.get("reasoning_caveman", ""),
    }


if __name__ == "__main__":
    # Manual test: verify.py <role_json_path> <tailored_resume_path>
    role = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tailored = Path(sys.argv[2]).read_text(encoding="utf-8")
    print(json.dumps(run(role, tailored), indent=2, ensure_ascii=False))
