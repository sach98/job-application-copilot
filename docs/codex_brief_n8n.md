# Codex brief: build n8n workflows

When Oracle VM ready + n8n running, delegate this brief to Codex.

## Context

candidate's job-application autopilot. Full spec at `~/.claude/plans/what-is-the-apiphy-ethereal-quill.md`. Sheet schema at `~/JobHunt/docs/sheet_schema.md`. Keywords at `~/JobHunt/docs/keywords.md`. Daily ops at `~/JobHunt/docs/runbook.md`.

## Deliverables

Six core n8n workflow JSON exports (n8n's import format), each self-contained:

### 1. `discover.json`

Triggers: 3 schedule nodes at 09:00, 12:30, 16:00 IST.

For each trigger:
- Parallel branches: one per source (LinkedIn JobSpy, Naukri JobSpy, Indeed JobSpy, Glassdoor JobSpy, Google Jobs Apify, Wellfound custom, Hirist RSS, Instahyre custom, Cutshort custom, iimjobs Gmail-parse, YC RSS, Foundit custom, AmbitionBox custom).
- Each branch: `Execute Command` invoking the matching scraper (in `~/JobHunt/scrapers/`), stdout is JSON array.
- Merge all → normalise to common schema → dedupe by `(company, role, jd_url_hash)` against `applications` sheet → append new rows with `status=new`.
- Webhook output to `score.json`.

### 2. `score.json`

Trigger: webhook from discover.json.

For each new row:
- Build scoring input JSON (jd, company, role, location, salary, posted_at, scraped_at, profile_skills from `~/JobHunt/profile/answers.md`, tier_a_companies, referral_available from enrichment).
- Execute Command: `claude -p "$(cat ~/JobHunt/prompts/scoring.md)" --model claude-haiku-4-5 --input-format json --output-format json < input.json`
- Parse output, update sheet cols `fit_score`, `score_components`.
- Pick top 5 today (subtract already-applied count from `daily_cap_tracker`).
- Mark chosen rows `status=queued`, set `queued_at`.
- Webhook to `tailor.json`.

### 3. `tailor.json`

Trigger: webhook from score.json (one call per queued role).

For each:
- Pull master_resume, profile_answers, tier_a_companies (from Drive via Drive API).
- Enrich: LinkedIn hiring-mgr search, team search, referral check, Hunter.io email lookup. Cache in `enrichment_cache` tab.
- Execute Command: `claude -p "$(cat ~/JobHunt/prompts/tailor.md)" --model claude-sonnet-4-6 --input-format json --output-format json < input.json`
- Take output JSON, render to:
  - Google Doc clone of resume template → replace bullets → export PDF → upload to `/JobHunt/<Company>_<Role>/resume.pdf` in Drive
  - Google Doc clone of CL template → replace body → PDF → upload
  - `essay_answers.md` → upload
- Update sheet row with all `_url` columns.
- Push card to Tinder app via `apply.json` webhook.

### 4. `apply.json`

Two triggers:
- (a) New role from tailor.json → adds to Tinder app card stack.
- (b) Tinder app POSTs candidate's swipe action.

For (b) by action:
- `apply` → Execute Command runs the per-portal Playwright script (Codex's library in `~/JobHunt/playwright_scripts/`). Antigravity-supervised.
- `skip` → mark row `status=skipped`.
- `save` → leave in pool, decay recency next day.
- `edit` → open Google Doc for manual edit (returns URL).

During form-fill:
- On unknown free-text question, Playwright dumps to webhook → Execute Command runs essay.md prompt → Sonnet drafts → Gmail one-click APPROVE button → on click, Playwright resumes.

After submit: mark `status=applied`, set `applied_at`, `followup_1_due = +7d`, `followup_2_due = +14d`. Upload screenshots to Drive.

### 5. `followup.json`

Trigger: daily 10:00 IST cron.

Query sheet for `followup_1_due <= today AND response_at IS NULL AND status IN (applied, followup_1_sent)`.

For each:
- Stage = `inmail_1` if no follow-up sent yet, else `inmail_2`.
- Execute Command: `claude -p "$(cat ~/JobHunt/prompts/followup.md)" ...` with stage + context.
- LinkedIn node sends InMail (uses Premium credit if needed).
- If hiring_mgr_email present: also send email via Gmail node.
- If referral available + first follow-up: also DM warm-intro msg.
- Mark `followup_1_sent_at` or `followup_2_sent_at`.
- Throttle: max 15 InMails/day total across rows, 8-min randomised gaps.

### 6. `digest.json`

Two crons:
- 08:55 IST daily: morning brief (Phase 2 E1).
- 18:00 Sunday: weekly review (Phase 2 E2).

Gmail node sends to candidate@example.com.

## Conventions

- All sheet writes go through Google Sheets node with `id`-based update, never overwriting rows.
- All Drive uploads use candidate's `/JobHunt/` root.
- Every Execute Command captures stderr and surfaces to n8n error workflow.
- Error workflow: log to `~/JobHunt/logs/`, email candidate if 3 consecutive failures.
- Use n8n credentials store, never hardcode tokens.

## Test plan

Codex must include for each workflow:
- Test fixture input JSON in `~/JobHunt/n8n_workflows/test_fixtures/`.
- Expected output assertion.
- One-line bash to manually trigger the workflow with fixture.

Output: six JSONs in `~/JobHunt/n8n_workflows/`, plus a `setup.sh` that imports all into n8n.
