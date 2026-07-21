#!/usr/bin/env python3
"""Patch the existing local queue with LinkedIn contacts (hiring mgr, team, referrals).

Unlike build_local_queue --enrich (which only enriches freshly tailored cards),
this enriches every card already in local_queue.json, use it to backfill contacts
on cards that are carried over. Launches Comet once for all companies, so Comet
must be CLOSED and LinkedIn logged in.

Usage: enrich_queue.py [--only-missing]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.paths import APPLICATIONS_DIR

HERE = Path(__file__).parent
QUEUE = APPLICATIONS_DIR / "local_queue.json"
ENRICH = HERE / "enrich_linkedin.py"


def log(msg: str) -> None:
    print(f"[enrich_queue] {msg}", file=sys.stderr, flush=True)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _has_contacts(card: dict) -> bool:
    hm = card.get("hiring_mgr") or {}
    team = card.get("team_members") or "[]"
    return bool(hm.get("name")) or (team not in ("[]", "", None)) or bool(card.get("referrals"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-missing", action="store_true",
                    help="Skip cards that already have any contact populated.")
    args = ap.parse_args()

    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    roles = data.get("roles", [])
    targets = [r for r in roles if not (args.only_missing and _has_contacts(r))]
    if not targets:
        log("nothing to enrich")
        return 0

    payload = [
        {"id": str(r.get("id")), "company": r.get("company") or "",
         "role": r.get("role") or "Business Analyst", "location": r.get("location") or ""}
        for r in targets
    ]
    fd, tmp = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    try:
        log(f"enriching {len(payload)} companies via LinkedIn (Comet)...")
        proc = subprocess.run(
            [sys.executable, str(ENRICH), "--batch", tmp],
            capture_output=True, text=True, timeout=1200,
        )
    finally:
        Path(tmp).unlink(missing_ok=True)

    if proc.returncode != 0:
        log(f"enrich failed (rc={proc.returncode}): {proc.stderr.strip()[-400:]}")
        return 1

    contacts = json.loads(proc.stdout)
    patched = 0
    ok_count = 0
    empty_count = 0
    blocked_count = 0
    for r in roles:
        c = contacts.get(str(r.get("id")))
        if not c:
            continue
        hm = c.get("hiring_manager") or {}
        team = c.get("team_members") or []
        referrals = c.get("referrals") or []
        r["hiring_mgr"] = {
            "name": hm.get("name", ""),
            "title": hm.get("title", ""),
            "linkedin_url": hm.get("linkedin_url", ""),
        }
        r["team_members"] = json.dumps(team, ensure_ascii=False)
        r["referrals"] = referrals
        r["referral_available"] = bool(referrals)
        
        status = c.get("_status", "ok")
        if status == "ok":
            ok_count += 1
        elif status == "empty":
            empty_count += 1
        elif status == "blocked":
            blocked_count += 1
            
        patched += 1

    _atomic_write(QUEUE, json.dumps(data, ensure_ascii=False, indent=2))
    log(f"patched {patched}/{len(roles)} cards ({ok_count} ok, {empty_count} empty, {blocked_count} blocked) -> {QUEUE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
