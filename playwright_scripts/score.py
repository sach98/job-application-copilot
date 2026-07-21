#!/usr/bin/env python3
"""Score one job for fit via Claude Haiku, grounded in candidate's skills + tier-A list.

Input: --input-b64 <base64 of role JSON> (one row from the applications sheet).
Output (stdout, single JSON object): the row merged with fit_score,
score_components (JSON string), reasoning_caveman, status='scored'.

Mirrors scoring.md's input/output contract. The previous n8n node piped role
JSON through `echo` (broke on quotes) and never parsed the CLI's JSON envelope,
so fit_score was always blank and nothing got queued.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.sonnet import call_claude
from lib.profile import load_profile
from lib.paths import PROFILE_DIR, PROMPTS_DIR
SCORING_PROMPT = PROMPTS_DIR / "scoring.md"
MASTER_RESUME = PROFILE_DIR / "master_resume.md"
TIER_A = PROFILE_DIR / "tier_a_companies.md"
SCORING_MODEL = "claude-haiku-4-5"

CANDIDATE_SENIORITY = "Senior Business Analyst, 6+ years"
CANDIDATE_DOMAINS = ["BFSI", "insurance", "consulting", "data & analytics", "digital transformation"]


def log(msg: str) -> None:
    print(f"[score] {msg}", file=sys.stderr, flush=True)


def _profile_skills() -> list[str]:
    try:
        prof = load_profile()
    except Exception:
        return []
    skills = list(prof.get("key_skills") or [])
    for it in prof.get("it_skills") or []:
        name = it.get("name") if isinstance(it, dict) else it
        if name:
            skills.append(name)
    return skills


def _candidate_summary() -> str:
    """Pull the Professional Summary paragraph from master_resume.md for holistic judging."""
    if not MASTER_RESUME.exists():
        return ""
    lines = MASTER_RESUME.read_text(encoding="utf-8").splitlines()
    out, capture = [], False
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("## ") and "summary" in s.lower():
            capture = True
            continue
        if capture:
            if s.startswith("## "):  # next section → stop
                break
            if s:
                out.append(s)
            if len(" ".join(out)) > 600:  # one solid paragraph is enough
                break
    return " ".join(out)[:800]


def _candidate() -> dict:
    return {
        "summary": _candidate_summary(),
        "seniority": CANDIDATE_SENIORITY,
        "domains": CANDIDATE_DOMAINS,
        "skills": _profile_skills(),
    }


def build_input(role: dict) -> dict:
    # Fit inputs only: timing/salary/company-prestige are deliberately excluded so
    # fit_score measures true candidate↔role match, not luck. (Recency/salary are
    # used downstream as separate sort hints, not part of fit.)
    return {
        "candidate": _candidate(),
        "jd": role.get("jd_text") or role.get("jd") or role.get("description") or "",
        "company": role.get("company") or "",
        "role": role.get("role") or role.get("title") or "",
        "location": role.get("location") or "",
    }


def run(role: dict) -> dict:
    scored = call_claude(SCORING_PROMPT, build_input(role), model=SCORING_MODEL)
    merged = dict(role)
    merged["fit_score"] = float(scored.get("fit_score") or 0.0)
    merged["score_components"] = json.dumps(scored.get("subscores") or {})
    merged["fit_verdict"] = scored.get("verdict", "")
    merged["fit_red_flags"] = scored.get("red_flags") or []
    merged["reasoning_caveman"] = scored.get("reasoning_caveman", "")
    merged["status"] = "scored"
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a job for fit via Haiku.")
    parser.add_argument("--input-b64", help="Base64-encoded role JSON.")
    args = parser.parse_args()

    try:
        if args.input_b64:
            role = json.loads(base64.b64decode(args.input_b64).decode("utf-8"))
        else:
            role = json.loads(sys.stdin.read())
    except Exception as exc:
        print(json.dumps({"status": "score_error", "error": f"bad input: {exc}"}))
        log(f"fatal: bad input {exc}")
        return 1

    try:
        merged = run(role)
    except Exception as exc:
        err = dict(role) if isinstance(role, dict) else {}
        err["status"] = "score_failed"
        err["fit_score"] = 0.0
        err["error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(err, ensure_ascii=False))
        log(f"transient error {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(merged, ensure_ascii=False))
    log(f"scored {merged.get('company')} / {merged.get('role')} = {merged.get('fit_score')}. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
