# AI Job-Application Co-pilot

> **All data in this repository is synthetic.** Everything in `sample_data/` is generated
> by `sample_data/generate_samples.py`, which runs the real pipeline against a stub model.
> The companies, roles, postings, resume, profile answers, contacts and every score are
> invented. No real employer, candidate, application history or hiring contact appears
> anywhere in this repo.

A human-in-the-loop job-application pipeline that scrapes roles, scores fit, tailors
materials, audits every tailored claim against a master resume, and queues only
review-ready applications for manual submission.

```text
scrape -> pre-filter -> tailor -> ANTI-FABRICATION AUDIT -> TAILORED-FIT GATE -> review -> manual-apply
```

## Why the anti-fabrication audit gate matters

Resume tailoring is useful only if it stays truthful. This project separates the writer
from the verifier: one pass tailors the resume and outreach drafts, then a second
adversarial pass checks every claim against the master resume. Unsupported claims are
dropped or sent back for re-tailoring before a human sees the application.

That gate is the differentiator. It treats hallucinated credentials, inflated metrics,
renamed roles, and untraceable projects as application blockers, not wording issues.

## The two gates, precisely

The pipeline applies two independent bars. They are easy to conflate, so this section
states exactly what each one does and where it lives in the code.

| Gate | Scored by | Threshold | Flag | Code |
|------|-----------|-----------|------|------|
| Pre-tailor floor | `prompts/scoring.md` (Haiku) on the raw JD | 0.60 | `--min-fit` | `build_local_queue._keep` |
| Tailored-fit gate | `prompts/verify_resume.md` (Sonnet) on the finished tailored resume | 0.80 | `--tailored-gate` | `build_local_queue.tailor_and_gate` |

The **pre-tailor floor** decides only which roles are worth spending a tailoring pass on.
It is a cost control, not a quality bar. A role in Delhi NCR or remote needs 0.60; a role
elsewhere needs 0.78 to surface at all (`--standout-fit`).

The **tailored-fit gate** is the bar a card must clear to reach a human. It uses the
auditor's own `fit_score` for the finished tailored resume, produced by a different model
with a different prompt from the one that wrote it. The writer's opinion of its own work
never becomes the card's score. A result between 0.55 and 0.80 earns exactly one honest
re-tailor aimed at the auditor's `missing_for_fit` list, then a re-audit. Still short means
the role is dropped, not rounded up.

Correctness outranks fit throughout: a re-tailor that scores higher but reintroduces a
fabrication is refused.

Cards already sitting in the queue are re-gated on every build
(`build_local_queue._at_or_above_gate`). Carried cards are never re-tailored, so this is
the only thing that can evict a card that was queued when the gate was lower. It compares
the audited tailored score against `--tailored-gate` and nothing else: the `--standout-fit`
concession is a pre-tailor allowance that sits below the gate, so applying it here would
readmit exactly the stale cards the re-gate exists to remove. Location is not re-litigated
either, having been settled before the card was tailored.

Both gates are visible in the committed sample run. Of four synthetic postings, one is
dropped by the pre-tailor floor, one is dropped by the tailored-fit gate after its retry
reaches only 0.71, and two are queued at 0.88 and 0.83. Regenerate and confirm with:

```bash
python3 sample_data/generate_samples.py --check
```

## What is included

- Python scrapers for public boards, RSS feeds, ATS endpoints, and selected
  Playwright-backed sources.
- Playwright form helpers for human-supervised application flows.
- n8n workflow exports for discovery, scoring, tailoring, follow-up, and review queue
  operations.
- Prompt contracts for scoring, tailoring, essays, follow-up, and resume audit.
- A lightweight review UI for deciding whether to skip, save, edit, or manually apply.
- Synthetic sample data, regenerated from the pipeline itself, so the flow can be
  inspected without private cookies, profiles, or API keys.

## Quickstart

1. Create a virtual environment and install dependencies.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

2. Copy the environment template and set only the integrations you plan to use.

```bash
cp .env.example .env
```

3. Choose where the pipeline keeps its data. Every script resolves its paths from
   `JOBHUNT_ROOT`, which defaults to `~/JobHunt`. Point it anywhere:

```bash
export JOBHUNT_ROOT="$PWD/.jobhunt-data"
```

   `$JOBHUNT_ROOT` is expected to contain `profile/` (your master resume and answers),
   `prompts/`, and a writable `applications/`. None of that private content ships here.
   Copy this repo's `prompts/` directory across to get started.

4. Model calls shell out to the Claude CLI. It is discovered on `PATH`; set `CLAUDE_BIN`
   to override.

5. Inspect the synthetic examples.

```bash
ls sample_data
python3 -m json.tool sample_data/local_queue.json
```

6. Run individual pipeline stages with sample input, or import the JSON workflows into
   n8n and replace placeholder credentials with your own.

The repository intentionally does not include a real resume, browser profile, application
history, cookies, logs, screenshots, or database files.

## Tests

Standard library `unittest`, no pytest:

```bash
cd playwright_scripts && ../.venv/bin/python -m unittest discover -s tests -t .
```

The suite covers the decision layer (the location policy, the fit-and-location keep rule,
and the tailor-audit-gate loop), the no-auto-submit guards, `JOBHUNT_ROOT` portability,
Claude CLI discovery, JD parsing, and sample-data freshness. It needs no model calls and
runs whether or not `playwright` is installed.

## Safety and compliance

- **Nothing auto-submits.** The dispatcher in `playwright_scripts/apply.py` runs
  draft-only unless a human has exported `JOBHUNT_ALLOW_AUTOSUBMIT=1` in that shell. The
  `--submit` flag alone is not enough. No shipped n8n workflow passes `--submit` or sets
  that variable, and a test asserts both. The intended final step is human review and
  manual application.
- Referral workflows use ToS-respecting deep links for the user to open in their own
  browser session. LinkedIn auto-apply is a deliberate stub.
- Scrapers are rate-limit disciplined and should be scoped to sources you are allowed to
  access.
- Keep a kill switch: stop cron/n8n jobs and pause browser automation if CAPTCHA,
  auth-wall, or quota warnings appear.
- Never commit `.env`, browser profiles, logs, generated applications, screenshots, or
  real profile data.

## Synthetic data note

Everything in `sample_data/` is fabricated for demonstration. Company names, roles,
hiring contacts, resume bullets, audit findings, and scores are examples only. The files
are not hand-written: `sample_data/generate_samples.py` runs `build_local_queue.main()`
unmodified and replaces only the single external boundary (`lib.sonnet.call_claude`) with
canned replies, so the samples always match the schema the pipeline really emits.
`--check` mode fails if they drift, and the test suite runs that check.

## License

MIT. See `LICENSE`.
