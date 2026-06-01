#!/usr/bin/env python3
"""Tailor step: inject master resume + profile into Sonnet, parse output, write artifacts.

Input: --input-b64 <base64 of role JSON> (from n8n Code node, avoids shell quoting).
Role JSON keys: id, company, role, jd_text/jd, hiring_mgr_name, hiring_mgr_title,
hiring_mgr_linkedin, fit_score (any others passed through).

Output (stdout, single JSON object): merged role + tailored artifact urls + previews.
Artifacts written to ~/JobHunt/applications/<safe_id>/ as markdown + json (no PDF
converter installed; fillers keep uploading master_resume.pdf until one exists).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.sonnet import call_claude

HOME = Path.home()
PROFILE_DIR = HOME / "JobHunt" / "profile"
PROMPTS_DIR = HOME / "JobHunt" / "prompts"
APPLICATIONS_DIR = HOME / "JobHunt" / "applications"

TAILOR_MODEL = "claude-opus-4-8"   # resume/CL writer — highest quality
TAILOR_EFFORT = "high"

MASTER_RESUME = PROFILE_DIR / "master_resume.md"
ANSWERS = PROFILE_DIR / "answers.md"
TIER_A = PROFILE_DIR / "tier_a_companies.md"
TAILOR_PROMPT = PROMPTS_DIR / "tailor.md"


PDF_CSS = """
@page { size: A4; margin: 1.1cm 1.4cm; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9.7pt;
       line-height: 1.25; color: #1a1a1a; }
h1 { font-size: 16pt; margin: 0 0 1pt 0; }
h2 { font-size: 10.5pt; color: #333; font-weight: 700; text-transform: uppercase;
     letter-spacing: 0.03em; margin: 9pt 0 3pt 0; border-bottom: 0.6pt solid #bbb; padding-bottom: 1pt; }
h3 { font-size: 10pt; margin: 6pt 0 1pt 0; }
p  { margin: 1pt 0; }
ul { margin: 2pt 0 0 0; padding-left: 15pt; }
li { margin-bottom: 2pt; }
"""


def log(msg: str) -> None:
    print(f"[tailor] {msg}", file=sys.stderr, flush=True)


def _pdf_engine_available() -> bool:
    return bool(shutil.which("pandoc")) and bool(shutil.which("weasyprint"))


def md_to_pdf(md_path: Path) -> Path | None:
    """Render a markdown file to a sibling PDF via pandoc + weasyprint.

    Returns the PDF path on success, None if no engine is installed or the
    conversion fails (caller falls back to the markdown / master resume).
    """
    if not _pdf_engine_available():
        return None
    pdf_path = md_path.with_suffix(".pdf")
    css_path = md_path.parent / "_pdf.css"
    try:
        css_path.write_text(PDF_CSS, encoding="utf-8")
        proc = subprocess.run(
            [
                "pandoc",
                str(md_path),
                "-o",
                str(pdf_path),
                "--pdf-engine=weasyprint",
                "--css",
                str(css_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or not pdf_path.exists():
            log(f"pdf convert failed: {proc.stderr.strip()[:200]}")
            return None
        return pdf_path
    except Exception as exc:
        log(f"pdf convert error: {exc}")
        return None
    finally:
        css_path.unlink(missing_ok=True)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


_CL_REQUEST_RE = re.compile(
    r"""
    cover(?:ing)?\s+letter
  | letter\s+of\s+(?:motivation|interest|intent)
  | motivation(?:al)?\s+letter
  | statement\s+of\s+(?:interest|purpose|intent)
  | attach\s+(?:a\s+)?(?:brief\s+)?letter
  | (?:tell|let)\s+us\s+why
  | why\s+(?:do\s+)?you\s+(?:want|are\s+interested)
  | why\s+you(?:'?re|\s+are)?\s+(?:a\s+)?(?:good|great)\s+fit
    """,
    re.IGNORECASE | re.VERBOSE,
)


def jd_wants_cover_letter(jd: str) -> bool:
    return bool(_CL_REQUEST_RE.search(jd or ""))


def _safe_id(role: dict) -> str:
    raw = str(role.get("id") or role.get("external_id") or f"{role.get('company','')}_{role.get('role','')}")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_") or "role"


def build_sonnet_input(role: dict, focus: list | None = None, remove_claims: list | None = None) -> dict:
    return {
        "jd": role.get("jd_text") or role.get("jd") or role.get("description") or "",
        "company": role.get("company") or "",
        "role": role.get("role") or role.get("title") or "",
        "hiring_mgr": {
            "name": role.get("hiring_mgr_name") or "",
            "title": role.get("hiring_mgr_title") or "",
            "linkedin_url": role.get("hiring_mgr_linkedin") or "",
        },
        "master_resume": _read(MASTER_RESUME),
        "profile_answers": _read(ANSWERS),
        "tier_a_companies": _read(TIER_A),
        # Retry hint: JD requirements the first pass underplayed. Surface genuine
        # matching experience for these — NEVER invent to cover a gap.
        "focus_gaps": focus or [],
        # Correctness-fix hint: an auditor flagged these exact claims as unsupported by
        # the master. Remove or rewrite each to what the master actually supports.
        "remove_claims": remove_claims or [],
    }


def write_artifacts(role: dict, tailored: dict, wants_cl: bool) -> dict:
    safe = _safe_id(role)
    out_dir = APPLICATIONS_DIR / safe
    out_dir.mkdir(parents=True, exist_ok=True)

    company = role.get("company") or ""
    role_title = role.get("role") or role.get("title") or ""

    # Opus writes ONE complete, tight, 1-page tailored resume (full structure, no
    # duplication). Fall back to the master verbatim only if the model omitted it.
    resume_md = (tailored.get("tailored_resume_markdown") or "").strip()
    if len(resume_md) < 200:  # model didn't produce a real resume → safe fallback
        master = _read(MASTER_RESUME)
        if "\n# {{candidate_name}}" in master:
            master = master[master.index("\n# {{candidate_name}}") + 1:]
        resume_md = master
    resume_path = out_dir / "resume.md"
    resume_path.write_text(resume_md, encoding="utf-8")
    resume_pdf = md_to_pdf(resume_path)

    cl_url = ""
    if wants_cl:
        cover_letter = tailored.get("cover_letter") or ""
        cl_md = "# Cover Letter — {role}, {company}\n\n{body}\n".format(
            role=role_title, company=company, body=cover_letter
        )
        cl_path = out_dir / "cover_letter.md"
        cl_path.write_text(cl_md, encoding="utf-8")
        cl_pdf = md_to_pdf(cl_path)
        cl_url = str(cl_pdf or cl_path)

    essays_path = out_dir / "essays.json"
    essays_path.write_text(
        json.dumps(
            {
                "essay_answer_drafts": tailored.get("essay_answer_drafts") or {},
                "linkedin_inmail_1": tailored.get("linkedin_inmail_1") or "",
                "linkedin_inmail_2_followup": tailored.get("linkedin_inmail_2_followup") or "",
                "warm_intro_msg": tailored.get("warm_intro_msg") or "",
                "interviewer_questions": tailored.get("interviewer_questions") or [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "resume_url": str(resume_pdf or resume_path),
        "cl_url": cl_url,
        "essay_answers_url": str(essays_path),
    }


def run(role: dict, focus: list | None = None, remove_claims: list | None = None) -> dict:
    sonnet_input = build_sonnet_input(role, focus=focus, remove_claims=remove_claims)
    if not sonnet_input["jd"]:
        log("warning: empty jd; tailoring with no JD context")

    tailored = call_claude(TAILOR_PROMPT, sonnet_input, model=TAILOR_MODEL, effort=TAILOR_EFFORT)
    # Always generate a cover letter so it's ready to attach at apply time (company
    # forms often accept/expect one). You choose whether to use it per application.
    wants_cl = True
    urls = write_artifacts(role, tailored, wants_cl)

    merged = dict(role)
    merged.update(urls)
    merged["status"] = "tailored"
    merged["fit_summary_3_bullets"] = tailored.get("fit_summary_3_bullets") or []
    merged["cl_preview"] = (tailored.get("cover_letter") or "")[:280] if wants_cl else ""
    bullets = tailored.get("tailored_resume_bullets") or []
    merged["tailored_resume_diff_preview"] = "\n".join(f"• {b}" for b in bullets[:3])
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Tailor a queued role via Sonnet.")
    parser.add_argument("--input-b64", help="Base64-encoded role JSON.")
    parser.add_argument("--input-file", help="Path to role JSON file (alternative to b64).")
    args = parser.parse_args()

    try:
        if args.input_b64:
            role = json.loads(base64.b64decode(args.input_b64).decode("utf-8"))
        elif args.input_file:
            role = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        else:
            role = json.loads(sys.stdin.read())
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"bad input: {exc}"}))
        log(f"fatal: bad input {exc}")
        return 1

    try:
        merged = run(role)
    except Exception as exc:
        err = dict(role) if isinstance(role, dict) else {}
        err["status"] = "tailor_failed"
        err["error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(err, ensure_ascii=False))
        log(f"transient error {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(merged, ensure_ascii=False))
    log(f"tailored {merged.get('company')} / {merged.get('role')}. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
