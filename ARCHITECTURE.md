# Architecture

## Goal

The system turns a stream of job postings into a small review queue of applications that are plausibly relevant, tailored, and checked for truthfulness before any human action.

## Pipeline

```text
sources -> normalized jobs -> fit scoring -> tailored artifacts -> audit gate -> review queue -> manual apply
```

## Components

- `scrapers/`: source adapters that emit normalized job JSON. Public-board and ATS sources are preferred because they reduce account and ToS risk.
- `playwright_scripts/`: local orchestration, form helpers, queue building, artifact generation, and browser-assisted flows.
- `prompts/`: strict prompt contracts for scoring, tailoring, custom essays, follow-up drafts, and the adversarial resume audit.
- `n8n_workflows/`: workflow exports for teams that want n8n as the scheduler and integration layer.
- `tinder_app/`: a small review UI that presents queued roles and captures human decisions.
- `sample_data/`: synthetic examples for demos and tests without private credentials.

## Data Contracts

Scrapers should return arrays of jobs with stable IDs, company, role/title, job URL, location, source, posting time, and job-description text when available.

Scoring returns a fit score, subscore JSON, concise reasoning, and red flags. Tailoring returns a complete tailored resume, optional cover letter, outreach snippets, and interview questions.

The audit pass receives the master resume, tailored resume, and JD. It returns `clean`, `fabrications`, `fit_score`, and `missing_for_fit`. Downstream queueing should require `clean == true` and a fit score above the configured threshold.

## Trust Boundary

Private inputs stay outside the repository: `.env`, browser profiles, master resume, profile answers, generated applications, screenshots, logs, databases, and cookies. This open-source copy contains code, workflow structure, prompt contracts, docs, and synthetic examples only.

## Operating Mode

The safest default is review-first and manual-apply. Browser automation can prepare or navigate forms, but submission should require explicit human approval. If a site presents CAPTCHA, auth-wall, selector drift, or rate-limit signals, the system should pause and fall back to manual handling.
