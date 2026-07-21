#!/usr/bin/env python3
"""Draft a custom portal essay answer via Sonnet, grounded in candidate's profile.

Input: --input-b64 <base64 of JSON> with at least {question}. Optional keys:
company, role, jd / jd_url, job_id, max_chars. The script injects answers.md
(profile_answers) and, when job_id resolves to a tailored cover letter, that CL
for tone context, so Sonnet answers from real data instead of inventing.

Output (stdout, single JSON object): {answer, char_count, confidence,
needs_human_review_reason} per prompts/essay.md.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.sonnet import call_claude
from lib.paths import APPLICATIONS_DIR, PROFILE_DIR, PROMPTS_DIR

ANSWERS = PROFILE_DIR / "answers.md"
ESSAY_PROMPT = PROMPTS_DIR / "essay.md"


def log(msg: str) -> None:
    print(f"[essay] {msg}", file=sys.stderr, flush=True)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _tailored_cover_letter(job_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(job_id or "")).strip("_")
    if not safe_id:
        return ""
    return _read(APPLICATIONS_DIR / safe_id / "cover_letter.md")


def build_input(req: dict) -> dict:
    return {
        "question": req.get("question") or "",
        "max_chars": int(req.get("max_chars") or 2000),
        "company": req.get("company") or "",
        "role": req.get("role") or "",
        "jd": req.get("jd") or req.get("jd_url") or "",
        "profile_answers": _read(ANSWERS),
        "tailored_cover_letter": _tailored_cover_letter(req.get("job_id")),
    }


def run(req: dict) -> dict:
    if not req.get("question"):
        return {"answer": "", "char_count": 0, "confidence": 0.0,
                "needs_human_review_reason": "no question supplied"}
    payload = build_input(req)
    result = call_claude(ESSAY_PROMPT, payload)
    answer = result.get("answer") or ""
    result["answer"] = answer
    result.setdefault("char_count", len(answer))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft a custom essay answer via Sonnet.")
    parser.add_argument("--input-b64", help="Base64-encoded request JSON.")
    args = parser.parse_args()

    try:
        if args.input_b64:
            req = json.loads(base64.b64decode(args.input_b64).decode("utf-8"))
        else:
            req = json.loads(sys.stdin.read())
    except Exception as exc:
        print(json.dumps({"answer": "", "char_count": 0, "confidence": 0.0,
                          "needs_human_review_reason": f"bad input: {exc}"}))
        log(f"fatal: bad input {exc}")
        return 1

    try:
        result = run(req)
    except Exception as exc:
        print(json.dumps({"answer": "", "char_count": 0, "confidence": 0.0,
                          "needs_human_review_reason": f"{type(exc).__name__}: {exc}"}))
        log(f"transient error {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(result, ensure_ascii=False))
    log(f"answered '{(req.get('question') or '')[:50]}'. chars={result.get('char_count')}. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
