#!/usr/bin/env python3
"""Draft a follow-up InMail/email via Sonnet for one due task.

Input: --input-b64 <base64 of task JSON> (built by followup.json's
Filter Due Followups node — carries stage, company, role, hiring_mgr, etc.).
Output (stdout): the task merged with subject, body, tone, char_count.

The previous n8n node piped the task through `echo` (broke on quotes) and then
JSON.parse'd the CLI's JSON envelope instead of the inner draft, so body/subject
were always empty.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.sonnet import call_claude

PROMPTS_DIR = Path.home() / "JobHunt" / "prompts"
FOLLOWUP_PROMPT = PROMPTS_DIR / "followup.md"


def log(msg: str) -> None:
    print(f"[followup] {msg}", file=sys.stderr, flush=True)


def build_input(task: dict) -> dict:
    return {
        "stage": task.get("stage") or "inmail_1",
        "company": task.get("company") or "",
        "role": task.get("role") or "",
        "jd_summary": task.get("jd_summary") or "",
        "applied_at": task.get("applied_at") or "",
        "hiring_mgr": task.get("hiring_mgr") or {},
        "referral_candidate": task.get("referral_candidate"),
        "previous_message_sent": task.get("previous_message_sent") or "",
    }


def run(task: dict) -> dict:
    draft = call_claude(FOLLOWUP_PROMPT, build_input(task))
    body = draft.get("body") or ""
    merged = dict(task)
    merged["subject"] = draft.get("subject") or ""
    merged["body"] = body
    merged["tone"] = draft.get("tone") or ""
    merged["char_count"] = draft.get("char_count") or len(body)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft a follow-up message via Sonnet.")
    parser.add_argument("--input-b64", help="Base64-encoded task JSON.")
    args = parser.parse_args()

    try:
        if args.input_b64:
            task = json.loads(base64.b64decode(args.input_b64).decode("utf-8"))
        else:
            task = json.loads(sys.stdin.read())
    except Exception as exc:
        print(json.dumps({"body": "", "subject": "", "error": f"bad input: {exc}"}))
        log(f"fatal: bad input {exc}")
        return 1

    try:
        merged = run(task)
    except Exception as exc:
        err = dict(task) if isinstance(task, dict) else {}
        err["body"] = ""
        err["subject"] = ""
        err["error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(err, ensure_ascii=False))
        log(f"transient error {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(merged, ensure_ascii=False))
    log(f"drafted {merged.get('stage')} for {merged.get('company')}. chars={merged.get('char_count')}. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
