# AI Job-Application Co-pilot

A human-in-the-loop job-application pipeline that scrapes roles, scores fit, tailors materials, audits every tailored claim against a master resume, and queues only review-ready applications for manual submission.

```text
scrape -> score -> tailor -> ANTI-FABRICATION AUDIT -> review -> manual-apply
```

## Why the anti-fabrication audit gate matters

Resume tailoring is useful only if it stays truthful. This project separates the writer from the verifier: one pass tailors the resume and outreach drafts, then a second adversarial pass checks every claim against the master resume. Unsupported claims are dropped or sent back for re-tailoring before a human sees the application.

That gate is the differentiator. It treats hallucinated credentials, inflated metrics, renamed roles, and untraceable projects as application blockers, not wording issues.

## What is included

- Python scrapers for public boards, RSS feeds, ATS endpoints, and selected Playwright-backed sources.
- Playwright form helpers for human-supervised application flows.
- n8n workflow exports for discovery, scoring, tailoring, follow-up, and review queue operations.
- Prompt contracts for scoring, tailoring, essays, follow-up, and resume audit.
- A lightweight review UI for deciding whether to skip, save, edit, or manually apply.
- Synthetic sample data so the flow can be inspected without private cookies, profiles, or API keys.

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
export JOBHUNT_ROOT="$PWD"
```

3. Inspect the synthetic examples.

```bash
ls sample_data
python -m json.tool sample_data/example_1_fintech_ba.json
```

4. Run individual pipeline stages with sample input, or import the JSON workflows into n8n and replace placeholder credentials with your own.

The repository intentionally does not include a real resume, browser profile, application history, cookies, logs, screenshots, or database files.

## Safety and compliance

- No auto-submit by default: the intended final step is human review and manual application.
- Referral workflows use ToS-respecting deep links for the user to open in their own browser session.
- Scrapers are rate-limit disciplined and should be scoped to sources you are allowed to access.
- Keep a kill switch: stop cron/n8n jobs and pause browser automation if CAPTCHA, auth-wall, or quota warnings appear.
- Never commit `.env`, browser profiles, logs, generated applications, screenshots, or real profile data.

## Synthetic data note

Everything in `sample_data/` is fabricated for demonstration. Company names, roles, hiring contacts, resume bullets, audit findings, and outputs are examples only.
