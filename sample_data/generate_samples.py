#!/usr/bin/env python3
"""Regenerate sample_data/ by running the REAL pipeline against a stub model.

The sample files used to be hand-written to a schema the pipeline never emitted. This
script removes that possibility: it runs build_local_queue.main() unmodified, so every
field in the output is produced by the same code that runs in production. The only thing
replaced is the single external boundary, lib.sonnet.call_claude, which answers with the
canned JSON in STUB_REPLIES instead of calling the Claude CLI.

What is synthetic and what is real:
  synthetic  the job postings, the master resume, the profile answers, and the model
             replies (companies, people, metrics and scores are all invented)
  real       the scoring, tailoring, audit and gating control flow, the artifact writer,
             the card builder, and therefore the SHAPE and KEYS of every output file

Absolute paths are rewritten to the literal "$JOBHUNT_ROOT" so the committed samples do
not leak the generating machine's temp directory.

Usage:
  python3 sample_data/generate_samples.py            # rewrite sample_data/
  python3 sample_data/generate_samples.py --check    # fail if the committed files are stale
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "sample_data"
SCRIPTS_DIR = REPO_ROOT / "playwright_scripts"

ROOT_PLACEHOLDER = "$JOBHUNT_ROOT"

# Synthetic scraped postings: the input the scrapers would hand to the queue builder.
SCRAPED_JOBS = [
    {
        "external_id": "synth-001",
        "company": "Northstar Mutual",
        "title": "Senior Business Analyst, Claims Automation",
        "location": "Gurgaon, HR, IN",
        "jd_url": "https://example.com/jobs/synth-001",
        "source": "synthetic_ats",
        "posted_at": "2026-01-06T09:00:00+05:30",
        "scraped_at": "2026-01-06T09:30:00+05:30",
        "salary": "22-28 LPA",
        "jd_text": (
            "Synthetic posting for demo use. Own claims-workflow discovery with operations "
            "and underwriting, map current-state processes, write BRDs and user stories, "
            "build SQL-backed analysis of claim cycle times, and specify dashboards for "
            "leadership. Partner with engineering through UAT and implementation handoff. "
            "No real employer or candidate data is represented."
        ),
    },
    {
        "external_id": "synth-002",
        "company": "Meridian Data Trust",
        "title": "Regulatory Reporting Analyst",
        "location": "Remote, India",
        "jd_url": "https://example.com/jobs/synth-002",
        "source": "synthetic_ats",
        "posted_at": "2026-01-06T10:15:00+05:30",
        "scraped_at": "2026-01-06T10:40:00+05:30",
        "salary": None,
        "jd_text": (
            "Synthetic posting for demo use. Produce periodic regulatory submissions, "
            "reconcile source systems against reported figures, document data lineage, "
            "and maintain the controls catalogue. SQL and advanced Excel required. "
            "No real employer or candidate data is represented."
        ),
    },
    {
        "external_id": "synth-003",
        "company": "Halcyon Product Labs",
        "title": "Product Operations Associate",
        "location": "Bangalore, KA, IN",
        "jd_url": "https://example.com/jobs/synth-003",
        "source": "synthetic_ats",
        "posted_at": "2026-01-06T11:00:00+05:30",
        "scraped_at": "2026-01-06T11:20:00+05:30",
        "salary": "14-18 LPA",
        "jd_text": (
            "Synthetic posting for demo use. Coordinate release readiness across product "
            "squads, maintain the launch checklist, and keep support enablement current. "
            "No real employer or candidate data is represented."
        ),
    },
    {
        "external_id": "synth-004",
        "company": "Calder & Roe Consulting",
        "title": "Business Analyst, Insurance Practice",
        "location": "Noida, UP, IN",
        "jd_url": "https://example.com/jobs/synth-004",
        "source": "synthetic_ats",
        "posted_at": "2026-01-06T12:00:00+05:30",
        "scraped_at": "2026-01-06T12:25:00+05:30",
        "salary": "18-24 LPA",
        "jd_text": (
            "Synthetic posting for demo use. Client-facing analysis for insurance "
            "transformation programmes: requirement workshops, process re-design, and "
            "benefits tracking. Please submit a cover letter with your application. "
            "No real employer or candidate data is represented."
        ),
    },
]

# Synthetic private inputs. In production these live outside the repo under $JOBHUNT_ROOT.
MASTER_RESUME = """# {{candidate_name}}
Example City, IN · +91 00000 00000 · candidate@example.com · linkedin.com/in/candidate-example

## Professional Summary
Business analyst with synthetic experience across insurance operations and reporting.

## Experience
### Business Analyst, Example Insurance (2021 - present)
- Mapped claims intake and settlement processes with operations stakeholders.
- Wrote BRDs and user stories for workflow automation releases.
- Built SQL analyses of cycle times and specified leadership dashboards.

### Analyst, Example Services (2019 - 2021)
- Reconciled source-system extracts against periodic regulatory submissions.
- Documented data lineage and maintained the controls catalogue.

## Skills
SQL, Excel, requirements analysis, process mapping, UAT, stakeholder workshops
"""

ANSWERS = """# Profile Q&A (synthetic)

## 9. Salary expectation + flexibility
Targeting the posted budget for the role, quoted in LPA.

## 10. Notice period (literal weeks)
Immediate to 2 weeks.

## 11. Why this company? - template hooks
Synthetic hook about the company's stated problem space.

## 17. Open to relocation? Y/N + caveats
Primary preference: Delhi NCR.

## 18. Hybrid / remote / onsite preference
Hybrid NCR preference.
"""

TIER_A = "# Tier A companies (synthetic)\n\nNorthstar Mutual\nCalder & Roe Consulting\n"

# Canned model replies, keyed by the prompt file the pipeline is calling with.
# Scores are chosen to exercise every branch of the gate, not to flatter the pipeline:
#   synth-001  raw 0.84 -> audited 0.88            queued
#   synth-002  raw 0.71 -> audited 0.83            queued
#   synth-003  raw 0.42                            dropped before tailoring (pre-filter)
#   synth-004  raw 0.76 -> audited 0.66, retry 0.71 -> dropped by the 0.80 tailored gate
STUB_REPLIES = {
    "scoring.md": {
        "synth-001": {"fit_score": 0.84, "verdict": "strong",
                      "subscores": {"responsibilities_match": 0.88, "skills_match": 0.85,
                                    "seniority_match": 0.82, "domain_match": 0.86},
                      "reasoning_caveman": "claims work match. same domain.", "red_flags": []},
        "synth-002": {"fit_score": 0.71, "verdict": "moderate",
                      "subscores": {"responsibilities_match": 0.74, "skills_match": 0.78,
                                    "seniority_match": 0.70, "domain_match": 0.62},
                      "reasoning_caveman": "reporting overlap. domain thinner.", "red_flags": []},
        "synth-003": {"fit_score": 0.42, "verdict": "weak",
                      "subscores": {"responsibilities_match": 0.40, "skills_match": 0.45,
                                    "seniority_match": 0.38, "domain_match": 0.35},
                      "reasoning_caveman": "product ops not analyst work.", "red_flags": []},
        "synth-004": {"fit_score": 0.76, "verdict": "moderate",
                      "subscores": {"responsibilities_match": 0.78, "skills_match": 0.74,
                                    "seniority_match": 0.76, "domain_match": 0.80},
                      "reasoning_caveman": "insurance yes. consulting new.", "red_flags": []},
    },
    "verify_resume.md": {
        "synth-001": [{"clean": True, "fabrications": [], "fit_score": 0.88,
                       "missing_for_fit": [],
                       "reasoning_caveman": "every claim traced to master."}],
        "synth-002": [{"clean": True, "fabrications": [], "fit_score": 0.83,
                       "missing_for_fit": [],
                       "reasoning_caveman": "reporting evidence real."}],
        "synth-004": [{"clean": True, "fabrications": [], "fit_score": 0.66,
                       "missing_for_fit": ["benefits tracking", "client-facing delivery"],
                       "reasoning_caveman": "no consulting delivery in master."},
                      {"clean": True, "fabrications": [], "fit_score": 0.71,
                       "missing_for_fit": ["benefits tracking"],
                       "reasoning_caveman": "still no consulting delivery."}],
    },
}


def _tailored_reply(company: str, role: str) -> dict:
    return {
        "tailored_resume_markdown": MASTER_RESUME.replace(
            "Business analyst with synthetic experience across insurance operations and reporting.",
            f"Business analyst with synthetic experience aligned to the {role} role at {company}. "
            "Reweighted from verified master-resume evidence only.",
        ),
        "cover_letter": (
            f"Dear Hiring Team at {company}, this synthetic draft demonstrates tone and "
            f"structure for the {role} role without using private candidate history."
        ),
        "fit_summary_3_bullets": [
            "Process mapping and BRD work matches the posting's core duties.",
            "SQL and dashboard specification are on the verified master resume.",
            "Domain terminology needs a human check before submitting.",
        ],
        "tailored_resume_bullets": [
            "Mapped claims intake and settlement processes with operations stakeholders.",
            "Wrote BRDs and user stories for workflow automation releases.",
            "Built SQL analyses of cycle times and specified leadership dashboards.",
        ],
        "essay_answer_drafts": {
            "Why this role?": "Synthetic answer grounded in the master resume only."
        },
        "linkedin_inmail_1": "Synthetic outreach note.",
        "linkedin_inmail_2_followup": "Synthetic follow-up note.",
        "warm_intro_msg": "Synthetic warm-intro request.",
        "interviewer_questions": [
            "How is success measured for this role?",
            "Which workflows need the most discovery?",
            "What data sources are available to analysts?",
        ],
    }


class StubModel:
    """Stands in for lib.sonnet.call_claude. Deterministic, offline, no CLI needed."""

    def __init__(self):
        self.verify_calls: dict[str, int] = {}
        self.call_log: list[str] = []

    def __call__(self, prompt_path, payload, timeout=600, model=None, effort=None):
        name = Path(prompt_path).name
        self.call_log.append(name)
        company = payload.get("company", "")
        job_id = self._job_id(company)

        if name == "scoring.md":
            return dict(STUB_REPLIES["scoring.md"][job_id])
        if name == "tailor.md":
            return _tailored_reply(company, payload.get("role", ""))
        if name == "verify_resume.md":
            seq = STUB_REPLIES["verify_resume.md"][job_id]
            i = self.verify_calls.get(job_id, 0)
            self.verify_calls[job_id] = i + 1
            return dict(seq[min(i, len(seq) - 1)])
        raise AssertionError(f"stub model has no reply for prompt {name}")

    @staticmethod
    def _job_id(company: str) -> str:
        for job in SCRAPED_JOBS:
            if job["company"] == company:
                return job["external_id"]
        raise AssertionError(f"unknown company in stub payload: {company!r}")


def _seed_root(root: Path) -> Path:
    (root / "profile").mkdir(parents=True, exist_ok=True)
    (root / "applications").mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "prompts", root / "prompts")
    (root / "profile" / "master_resume.md").write_text(MASTER_RESUME, encoding="utf-8")
    (root / "profile" / "answers.md").write_text(ANSWERS, encoding="utf-8")
    (root / "profile" / "tier_a_companies.md").write_text(TIER_A, encoding="utf-8")
    jobs_file = root / "scraped_jobs.json"
    jobs_file.write_text(json.dumps(SCRAPED_JOBS, indent=2, ensure_ascii=False), encoding="utf-8")
    return jobs_file


def _redact(text: str, root: Path) -> str:
    return text.replace(str(root), ROOT_PLACEHOLDER)


def build(root: Path) -> dict[str, str]:
    """Run the real pipeline under `root` and return {filename: file text}."""
    jobs_file = _seed_root(root)

    sys.path.insert(0, str(SCRIPTS_DIR))
    from lib import sonnet
    stub = StubModel()
    sonnet.call_claude = stub

    import build_local_queue, make_crib, score, tailor, verify
    for module in (score, tailor, verify):
        module.call_claude = stub
    # make_crib and tailor read profile files through module constants captured at import.
    make_crib.DEFAULT_ANSWERS_PATH = root / "profile" / "answers.md"
    make_crib.DEFAULT_MASTER_RESUME_PATH = root / "profile" / "master_resume.md"

    argv = sys.argv
    sys.argv = ["build_local_queue.py", "--jobs", str(jobs_file), "--top", "10"]
    try:
        rc = build_local_queue.main()
    finally:
        sys.argv = argv
    if rc != 0:
        raise SystemExit(f"pipeline returned {rc}")

    queue_text = (root / "applications" / "local_queue.json").read_text(encoding="utf-8")
    queue = json.loads(queue_text)
    if not queue["roles"]:
        raise SystemExit("pipeline produced an empty queue; samples would be useless")

    first_id = queue["roles"][0]["id"]
    crib_text = (root / "applications" / str(first_id) / "crib.json").read_text(encoding="utf-8")
    resume_text = (root / "applications" / str(first_id) / "resume.md").read_text(encoding="utf-8")

    return {
        "scraped_jobs.json": _redact(jobs_file.read_text(encoding="utf-8"), root),
        "local_queue.json": _redact(queue_text, root),
        "crib.json": _redact(crib_text, root),
        "tailored_resume.md": _redact(resume_text, root),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="Exit non-zero if the committed samples differ from a fresh run.")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "jobhunt"
        os.environ["JOBHUNT_ROOT"] = str(root)
        files = build(root)

    stale = []
    for name, text in files.items():
        target = SAMPLE_DIR / name
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != text:
                stale.append(name)
        else:
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target.relative_to(REPO_ROOT)}")

    if args.check:
        if stale:
            print(f"stale sample files: {', '.join(stale)}", file=sys.stderr)
            return 1
        print("sample_data is up to date with the pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
