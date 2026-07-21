# Operations runbook

## Daily

| Time IST | Event | Owner |
|----------|-------|-------|
| 08:55 | Morning brief email (Phase 2 E1) | n8n cron |
| 09:00 | Scrape pass 1 (full crawl past 24h) | n8n discover.json |
| 09:15 | Filter + dedupe + enrich + score | n8n score.json |
| 09:30 | Top-5 enter apply queue → Sonnet tailors → Tinder app cards ready | n8n tailor.json |
| 09:31 | Gmail notification "5 new roles in queue" | n8n |
| 10:00 | Follow-up cron: send InMail/email to applicable prior rows | n8n followup.json |
| 12:30 | Scrape pass 2 (incremental: high-volume sources) | n8n discover.json |
| 12:45 | Score + tailor new arrivals; insert into Tinder app | n8n |
| 12:46 | Gmail notification per new high-fit role | n8n |
| 13:00-14:00 | **candidate's prime apply window**: review Tinder app, swipe | candidate |
| 16:00 | Scrape pass 3 (incremental) | n8n discover.json |
| 21:00 (Sunday only) | Naukri resume bump (Phase 2 D1) | n8n |
| 23:55 | Daily cap reset + tomorrow's pool refresh | n8n |

## On response received (Gmail inbox classifier flags `responded`)

1. n8n marks row `responded`, sets `response_at`, suspends follow-ups.
2. Immediate Gmail alert + WhatsApp ping to candidate.
3. If classifier detects "interview" keyword → status = `interview` → triggers Phase 2 group B (dossier + mock interview + thank-you note + warm-intro + references pre-warm).
4. If "offer" → status = `offer` → triggers group C.
5. If "regret" / "moved forward with other candidates" → status = `rejected`.

## Failure modes

| Symptom | Action |
|---------|--------|
| Apify quota >80% | Auto-pause Apify source; rely on JobSpy + RSS. Email candidate. |
| Playwright selector drift on a portal | Antigravity opens browser visually, screenshots, regenerates selectors, commits patch. Pauses that portal until verified. |
| Sonnet rate limit (Pro plan: ~45 msgs/5h) | Queue backs off; alert candidate if backlog >20. |
| LinkedIn flags InMail cadence | Halt all LinkedIn auto-DM, switch to drafts-only, alert candidate. |
| Tinder app unreachable | Cloudflare Tunnel reconnect; fallback Gmail one-click buttons keep working. |
| n8n VM down | candidate SSH to Oracle VM, restart docker. Pipeline resumes from last cron tick. |

## Weekly Sunday 18:00 review (candidate manual + Phase 2 E2)

1. Read auto-generated `weekly_review` tab.
2. Inspect any rows with `confidence < 0.7` on essay answers, add new Q&A pairs to `profile/answers.md`.
3. Tune `daily_cap` based on response rate (raise if >15%, lower if <5% to focus quality).
4. Adjust `tier_a_companies` list if new targets emerged.

## Quarterly

- Audit and clean stale portal accounts (Phase 2 D3).
- Refresh master resume with last quarter's wins.
- Re-run Profile Q&A on questions 3, 5, 6 (wins + projects evolve).
