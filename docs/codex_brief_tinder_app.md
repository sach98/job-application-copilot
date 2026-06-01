# Codex brief — Tinder-style review web app

Build `~/JobHunt/tinder_app/` — single-page review UI hosted by n8n.

## URL + auth

- URL: `https://review.example.com` (Cloudflare Tunnel from Oracle VM).
- Auth: candidate signs in with Google (configured account). n8n issues a signed session JWT (HS256, 24h expiry). Stored in httpOnly cookie. No public access.

## Backend (in n8n)

n8n Webhook nodes expose REST endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/queue` | returns today's queued roles + their fit scores + tailored summaries |
| POST | `/api/swipe` | `{role_id, action: apply|skip|save|edit}` |
| GET | `/api/role/:id` | full role detail (JD, tailored resume diff, full CL, hiring mgr, screenshots if applied) |
| GET | `/api/status` | `{today_applied: 2, cap: 5, posting_window: "optimal", time_now: "12:18 IST"}` |
| POST | `/api/approve/:role_id` | one-click APPROVE for pending-review form submissions |

## Frontend (`index.html` + `app.js` + `style.css`)

Vanilla JS or lightweight (Alpine.js). No build step. Mobile-first.

### Layout

- **Top bar**: `JobHunt` logo · today count `2/5 applied` · posting-window badge (green if 11-14 IST, amber else) · settings cog.
- **Card stack** (centre): topmost card is fully visible, next 2 peek underneath for depth. Swipeable on touch + keyboard arrows + button bar.
- **Action buttons** (bottom): `← Skip` / `↓ Edit` / `↑ Save` / `→ Apply`. Big tap targets.
- **Side panel** (right, slides in on click): role full detail — JD, tailored resume preview (diff vs master), CL preview, hiring mgr LinkedIn link.

### Card content

- Company logo (favicon via favicongrabber.com).
- Company name + role title.
- Fit score chip (colour: green ≥0.75, amber 0.5-0.75, grey <0.5).
- Salary band.
- Posted-at relative time ("18 min ago" → bold if <90 min).
- Hiring manager name + title (linked to LinkedIn).
- 3-bullet "why this role" from `fit_summary_3_bullets` in tailor output.
- Tags: source (linkedin/naukri/...), tier-A badge if applicable, referral-available badge.

### Interactions

- Swipe right or `→` key or APPLY button → POST `/api/swipe` action=apply → loading state → success toast "Applying to <Company>…" → card flies off right.
- Swipe left → skip → card flies off left.
- Swipe up → save → card flies off up.
- Swipe down → edit → opens side panel with Google Docs embed for resume + CL edit; on save, regenerates PDF.

### Push notifications

- Web Push API. On page load, prompts permission once.
- Each new role hitting queue → push notification "New role: <Company> · <Role> · fit 0.82" → tap opens app on that card.

### Approval mode

When a portal form-fill paused for approval (Stage 4B step 4): app shows a banner "1 application pending your review". Tapping shows the screenshot + drafted essay answer + APPROVE/EDIT buttons.

## Style

Use design skill (`design:design-system`, `design:ux-copy`) to polish. Keep BFSI-professional but with the swipe-app feel — calm colours (slate, white, accent teal for primary actions, no red-green binary).

## Test plan

- Render with 5 mock roles in `test_fixtures/queue.json`.
- Manually swipe each direction, confirm `/api/swipe` called with right action.
- Resize to mobile (390px) — all buttons reachable thumb-only.
- Push notification permission flow.
- Auth bounce: hit `/review` while signed out → Google sign-in → back to app.
