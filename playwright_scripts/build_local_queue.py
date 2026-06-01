#!/usr/bin/env python3
"""Local pipeline: score scraped jobs, tailor the top N, emit the app's queue JSON.

Bypasses n8n + Google Sheets so the Tinder review app has real, scored, tailored
cards to show. serve_tinder.py serves the written file for the queue endpoint.

Usage:
  build_local_queue.py --jobs applications/_scraped_jobs.json --top 5
Output: applications/local_queue.json  (shape matches apply.json Format Queue Response)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
import score as score_mod
import tailor as tailor_mod
import make_crib
import verify as verify_mod

APPLICATIONS_DIR = Path.home() / "JobHunt" / "applications"
PRE_FILTER_FLOOR = 0.55   # raw floor; strong-adjacent roles still get a tailoring attempt
                          # (the honest 0.80 gate on the TAILORED result is the real bar)
RETRY_LOW = 0.55          # tailored-fit band [RETRY_LOW, gate) eligible for one honest re-tailor

HOME = Path.home()
OUT = HOME / "JobHunt" / "applications" / "local_queue.json"
SWIPE_STATE = HOME / "JobHunt" / "applications" / "_swipe_state.json"
SCORE_CACHE = HOME / "JobHunt" / "applications" / "_score_cache.json"
SEEN_FILE = HOME / "JobHunt" / "applications" / "_seen_jobs.json"  # postings already processed (poll dedup)

# Delhi NCR + remote gate. Matches NCR city names AND the "DL" state code jobspy returns,
# plus remote/WFH/hybrid. (Bare "HR, IN"/"UP, IN" without a city are NOT matched — too broad;
# real Gurgaon/Noida postings carry the city name.) Use --all-locations to bypass.
import re as _re
NCR_RE = _re.compile(
    r"\b(delhi|new delhi|ncr|gurgaon|gurugram|noida|greater noida|faridabad|ghaziabad|"
    r"dl|remote|work from home|wfh|hybrid)\b",
    _re.IGNORECASE,
)


def _loc_ok(job: dict) -> bool:
    return bool(NCR_RE.search(str(job.get("location") or "")))


def _keep(card: dict, min_fit: float, standout: float, all_locations: bool) -> bool:
    """NCR/remote at min_fit, OR a genuine standout (>=standout) anywhere.

    Honors the Delhi-NCR preference by default while never burying an exceptional
    out-of-NCR match (you decide per-role if it's worth relocating)."""
    fit = float(card.get("fit_score") or 0)
    if all_locations:
        return fit >= min_fit
    return (fit >= min_fit and _loc_ok(card)) or (fit >= standout)

# Swipes in these states mean the user is done with the job -> drop it.
# 'save'/'edit' (or no swipe) keep the card in the queue.
ACTED_ACTIONS = {"apply", "skip"}


def log(msg: str) -> None:
    print(f"[build_queue] {msg}", file=sys.stderr, flush=True)


def normalize(job: dict) -> dict:
    jd = job.get("jd_text") or job.get("jd") or ""
    if jd == "nan":
        jd = ""
    return {
        "id": job.get("external_id") or job.get("id") or job.get("jd_url"),
        "company": job.get("company") or "",
        "role": job.get("title") or job.get("role") or "",
        "title": job.get("title") or job.get("role") or "",
        "jd_text": jd,
        "jd_url": job.get("jd_url") or "",
        "location": job.get("location") or "",
        "salary": job.get("salary"),
        "source": job.get("source") or "",
        "posted_at": job.get("posted_at"),
        "scraped_at": job.get("scraped_at"),
    }


def _li_people_search(keywords: str, first_degree: bool = False) -> str:
    """Build a LinkedIn people-search deep-link. The user clicks it in their own
    browser session — zero automation against the account, so zero ban risk."""
    from urllib.parse import quote
    url = f"https://www.linkedin.com/search/results/people/?keywords={quote(keywords)}"
    if first_degree:
        url += '&network=%5B%22F%22%5D'  # ["F"] = 1st-degree connections
    return url


def referral_links(company: str, role: str) -> dict:
    """Deep-links the user clicks to find referrals / hiring managers themselves."""
    company = (company or "").strip()
    role = (role or "Business Analyst").strip()
    return {
        "referral_search_url": _li_people_search(company, first_degree=True),
        "hiring_search_url": _li_people_search(f"{company} {role}"),
    }


def to_card(tailored: dict, contacts: dict | None = None) -> dict:
    fs = tailored.get("fit_summary_3_bullets") or []
    contacts = contacts or {}
    hm = contacts.get("hiring_manager") or {}
    team = contacts.get("team_members") or []
    referrals = contacts.get("referrals") or []
    hiring_mgr = {
        "name": hm.get("name", ""),
        "title": hm.get("title", ""),
        "linkedin_url": hm.get("linkedin_url", ""),
    }

    role_id = tailored.get("id")
    apps_dir = Path.home() / "JobHunt" / "applications"

    def get_artifact_url(filename: str) -> str:
        if role_id:
            file_path = apps_dir / str(role_id) / filename
            if file_path.exists():
                return f"artifact/{role_id}/{filename}"
        return ""

    resume_pdf_url = get_artifact_url("resume.pdf")
    cover_letter_pdf_url = get_artifact_url("cover_letter.pdf")
    crib_url = f"artifact/{role_id}/crib.json" if role_id else ""

    return {
        "id": role_id,
        "company": tailored.get("company"),
        "role": tailored.get("role"),
        "salary": tailored.get("salary"),
        "fit_score": float(tailored.get("fit_score") or 0),
        "source": tailored.get("source"),
        "location": tailored.get("location"),
        "posted_at": tailored.get("posted_at"),
        "jd_url": tailored.get("jd_url"),
        "fit_summary_3_bullets": fs,
        "hiring_mgr": hiring_mgr,
        "jd_excerpt": (tailored.get("jd_text") or "")[:1000],
        "cl_preview": tailored.get("cl_preview") or "",
        "cl_url": tailored.get("cl_url") or "",
        "tailored_resume_diff_preview": tailored.get("tailored_resume_diff_preview") or "",
        "resume_url": tailored.get("resume_url") or "",
        "team_members": json.dumps(team, ensure_ascii=False),
        "referrals": referrals,
        "referral_available": bool(referrals),
        "status": "queued",
        "apply_url": tailored.get("jd_url") or "",
        "resume_pdf_url": resume_pdf_url,
        "cover_letter_pdf_url": cover_letter_pdf_url,
        "crib_url": crib_url,
        **referral_links(tailored.get("company"), tailored.get("role")),
    }


def _swipe_state() -> dict:
    if not SWIPE_STATE.exists():
        return {}
    try:
        return json.loads(SWIPE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_acted_ids() -> set:
    return {rid for rid, v in _swipe_state().items() if (v or {}).get("action") in ACTED_ACTIONS}


def today_applied_count() -> int:
    """Count 'apply' swipes recorded today (UTC) -> real top-bar counter."""
    today = datetime.now(timezone.utc).date().isoformat()
    n = 0
    for v in _swipe_state().values():
        v = v or {}
        if v.get("action") == "apply" and str(v.get("at", "")).startswith(today):
            n += 1
    return n


# Bump when the scoring rubric changes so stale cached scores are recomputed.
SCORER_VERSION = "v5-final-master"


def _cache_key(job: dict) -> str:
    jd = job.get("jd_text") or ""
    h = hashlib.sha1(jd.encode("utf-8")).hexdigest()[:12]
    return f"{SCORER_VERSION}:{job.get('id')}:{h}"


def load_score_cache() -> dict:
    if not SCORE_CACHE.exists():
        return {}
    try:
        return json.loads(SCORE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _atomic_write(path: Path, text: str) -> None:
    """Write via temp + os.replace so a concurrent reader never sees a partial file."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def enrich_contacts(jobs: list[dict]) -> dict:
    """Batch-find hiring manager / team / referral contacts for fresh jobs.

    Shells out to enrich_linkedin.py --batch (one Comet launch for all). Best-effort:
    any failure (Comet running, logged out, timeout) returns {} so the build still
    completes with 'unknown' contacts rather than aborting.
    """
    if not jobs:
        return {}
    payload = [
        {"id": str(j.get("id")), "company": j.get("company") or "",
         "role": j.get("role") or "Business Analyst", "location": j.get("location") or ""}
        for j in jobs
    ]
    enrich_py = Path(__file__).parent / "enrich_linkedin.py"
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        log(f"enriching {len(payload)} companies via LinkedIn (Comet)...")
        proc = subprocess.run(
            [sys.executable, str(enrich_py), "--batch", tmp],
            capture_output=True, text=True, timeout=900,
        )
        if proc.returncode != 0:
            log(f"enrich failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}")
            return {}
        return json.loads(proc.stdout)
    except Exception as exc:
        log(f"enrich error: {exc}")
        return {}
    finally:
        Path(tmp).unlink(missing_ok=True)


def _job_fp(job: dict) -> str:
    """Stable fingerprint for a posting (id, else normalized URL)."""
    return str(job.get("id") or (job.get("jd_url") or "").strip().rstrip("/"))


def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen(seen: set) -> None:
    # Cap so the ledger can't grow unbounded over months of polling.
    trimmed = list(seen)[-5000:]
    _atomic_write(SEEN_FILE, json.dumps(trimmed, ensure_ascii=False))


def load_existing_cards() -> list[dict]:
    if not OUT.exists():
        return []
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("roles", [])
    except Exception:
        return []


def merge_cards(existing: list[dict], fresh: list[dict], acted: set) -> list[dict]:
    """Carry un-acted existing cards forward, append fresh, drop acted, dedupe by id + jd_url."""
    merged: list[dict] = []
    seen_ids: set = set()
    seen_urls: set = set()
    for card in (*existing, *fresh):
        cid = str(card.get("id"))
        url = (card.get("jd_url") or "").strip().rstrip("/")
        if cid in acted or cid in seen_ids or (url and url in seen_urls):
            continue
        merged.append(card)
        seen_ids.add(cid)
        if url:
            seen_urls.add(url)
    return merged


def _read_tailored_resume(role_id) -> str:
    p = APPLICATIONS_DIR / str(role_id) / "resume.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def tailor_and_gate(role: dict):
    """Tailor → correctness audit (grader ≠ author) → one strip-retry on fabrication.

    Fit is gated UPSTREAM on the raw holistic score; this pass exists only to guarantee
    the tailored resume is fabrication-free. Returns (tailored_dict, verdict) with
    fit_score = the role's raw fit, or (None, reason) if a fabrication can't be removed.
    """
    raw_fit = float(role.get("fit_score") or 0)
    try:
        tailored = tailor_mod.run(role)
    except Exception as exc:
        log(f"tailor failed {role.get('company')}: {exc}")
        return None, "tailor_error"

    try:
        v = verify_mod.run(role, _read_tailored_resume(tailored.get("id")))
    except Exception as exc:
        log(f"verify failed {role.get('company')}: {exc}")
        return None, "verify_error"

    # Correctness-fix loop: hand flagged claims back to the tailorer to strip, re-audit.
    # Up to 2 strip passes — a strong-fit job is worth extra tries to land a CLEAN resume.
    strip = 0
    while not v["clean"] and strip < 2:
        strip += 1
        log(f"fix {role.get('company')} (pass {strip}): stripping {len(v['fabrications'])} claim(s)")
        try:
            tailored = tailor_mod.run(role, remove_claims=v["fabrications"])
            v = verify_mod.run(role, _read_tailored_resume(tailored.get("id")))
        except Exception as exc:
            log(f"correctness-fix failed {role.get('company')}: {exc}")
            return None, "fix_error"
    if not v["clean"]:
        log(f"DROP {role.get('company')}: fabrication persists after {strip} fixes {v['fabrications'][:2]}")
        return None, "fabrication"

    tailored["fit_score"] = raw_fit
    return tailored, f"clean (raw fit {raw_fit:.2f})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--top", type=int, default=25,
                    help="Max jobs to run through the tailor→gate gauntlet (cost bound).")
    ap.add_argument("--min-fit", type=float, default=0.60,
                    help="Raw holistic fit gate (0-1): queue jobs at/above this. The resume is "
                         "then tailored + audited fabrication-free. Default 0.60.")
    ap.add_argument("--all-locations", action="store_true",
                    help="Bypass the location policy (queue any location at --min-fit).")
    ap.add_argument("--standout-fit", type=float, default=0.78,
                    help="Out-of-NCR roles still surface if fit >= this (default 0.78).")
    ap.add_argument("--poll", action="store_true",
                    help="Continuous-poll mode: skip postings already in the seen-ledger "
                         "(only NEW jobs are scored/tailored) + record this run's jobs as seen.")
    ap.add_argument("--enrich", action="store_true",
                    help="Find hiring manager / team / referral contacts via LinkedIn "
                         "(launches Comet — quit Comet first, slow). Deep-link referrals are "
                         "always added regardless; this is the optional automated path.")
    args = ap.parse_args()

    acted = load_acted_ids()
    existing = load_existing_cards()
    carried = [c for c in existing if str(c.get("id")) not in acted]
    carried_ids = {str(c.get("id")) for c in carried}
    log(f"carry-over {len(carried)} un-acted, dropped {len(acted)} acted")

    jobs = [normalize(j) for j in json.loads(Path(args.jobs).read_text(encoding="utf-8"))]
    log(f"{len(jobs)} jobs loaded")

    # NOTE: no pre-score location filter — we score all so an out-of-NCR STANDOUT can
    # still surface. The NCR/remote-or-standout decision is applied at the keep gate below.
    seen = load_seen() if args.poll else set()
    if args.poll:
        all_fps = {_job_fp(j) for j in jobs}
        jobs = [j for j in jobs if _job_fp(j) not in seen]
        log(f"poll mode: {len(jobs)} NEW (skipped {len(all_fps) - len(jobs)} already-seen)")

    cache = load_score_cache()
    scored = []
    hits = 0
    for j in jobs:
        key = _cache_key(j)
        cached = cache.get(key)
        if cached:
            hits += 1
            scored.append({**j, **cached})
            continue
        try:
            result = score_mod.run(j)
        except Exception as exc:
            log(f"score failed {j.get('company')}: {exc}")
            j["fit_score"] = 0.0
            scored.append(j)
            continue
        cache[key] = {"fit_score": result.get("fit_score", 0.0)}
        scored.append(result)
    if hits:
        log(f"score cache: {hits}/{len(jobs)} reused")
    _atomic_write(SCORE_CACHE, json.dumps(cache, ensure_ascii=False, indent=2))

    # Fit gate on the RAW holistic score (#6): apply only to genuinely-fitting roles.
    # Tailoring then makes the strongest HONEST resume; the audit guarantees no fabrication.
    qualified = [r for r in scored if _keep(r, args.min_fit, args.standout_fit, args.all_locations)]
    qualified.sort(key=lambda r: (-float(r.get("fit_score") or 0), str(r.get("id") or "")))
    top = qualified[: args.top]
    loc_note = "any-location" if args.all_locations else f"NCR/remote ≥{args.min_fit:.0%} or anywhere ≥{args.standout_fit:.0%}"
    log(f"{len(qualified)}/{len(scored)} qualify ({loc_note}); tailoring top {len(top)}")
    if not top and scored:
        best = max(scored, key=lambda r: float(r.get("fit_score") or 0))
        log(f"none cleared {args.min_fit:.0%}; best {best.get('company')}={float(best.get('fit_score') or 0):.2f}")

    fresh_top = [r for r in top if str(r.get("id")) not in carried_ids]
    contacts_by_id = enrich_contacts(fresh_top) if args.enrich else {}

    cards = []
    for r in fresh_top:
        tailored, verdict = tailor_and_gate(r)
        if tailored is None:
            continue  # dropped: a fabrication couldn't be removed
        log(f"KEEP {r.get('company')} ({verdict})")
        try:
            make_crib.write_crib(tailored, APPLICATIONS_DIR / str(tailored.get("id")))
        except Exception as exc:
            log(f"Warning: failed to write crib for {tailored.get('id')}: {exc}")
        cards.append(to_card(tailored, contacts_by_id.get(str(r.get("id")))))

    merged = merge_cards(carried, cards, acted)
    # Apply the same quality gate to carried-over cards (drops stale sub-threshold ones).
    before = len(merged)
    merged = [c for c in merged if _keep(c, args.min_fit, args.standout_fit, args.all_locations)]
    if before != len(merged):
        log(f"dropped {before - len(merged)} card(s) failing fit/location policy")
    payload = {
        "roles": merged,
        "today_applied": today_applied_count(),
        "pending_review_count": len(merged),
    }
    _atomic_write(OUT, json.dumps(payload, ensure_ascii=False, indent=2))
    log(f"wrote {len(merged)} cards ({len(carried)} carried + {len(cards)} fresh) -> {OUT}")

    if args.poll:
        save_seen(seen | all_fps)
        log(f"seen-ledger now {len(seen | all_fps)} postings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
