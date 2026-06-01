# Codex brief — Playwright form-fill library

Build `~/JobHunt/playwright_scripts/` — per-portal form-fill bots, run by Antigravity, invoked by n8n `apply.json`.

## Browser — Comet (default everywhere)

All Playwright scripts must launch **Comet** (Perplexity's Chromium-based AI browser at `/Applications/Comet.app/Contents/MacOS/Comet`), not stock Chromium. Reasons: candidate's logged-in cookies, password manager, LinkedIn session, and Naukri session all live in Comet. Reusing the same browser = no separate auth headaches + Comet's AI features can assist form-fill where useful.

Launch pattern in every script:

```ts
import { chromium } from 'playwright';
const browser = await chromium.launch({
  executablePath: '/Applications/Comet.app/Contents/MacOS/Comet',
  channel: undefined,
  headless: false,  // visible while in dry-run; flip to true after Stage 4 stable
  args: ['--user-data-dir=${JOBHUNT_ROOT}/.browser-profile/comet']
});
```

A dedicated profile (`~/JobHunt/.browser-profile/comet/`) keeps job-hunt cookies + sessions isolated from candidate's personal Comet windows but still imports passwords on first run if candidate opts in.

## Shared scaffolding (`playwright_scripts/lib/`)

- `base.ts` — abstract `FormFillBot` class. Methods: `login()`, `navigate(jd_url)`, `clickApply()`, `uploadResume(path)`, `fillStandardFields(profile)`, `fillEssay(question, draftedAnswer)`, `pauseForApproval(stage)`, `submit()`, `screenshot(label)`.
- `profile.ts` — loads candidate's standard fields (name, email, phone, location, exp years, current company, current ctc, expected ctc, notice period, etc.) from `~/JobHunt/profile/answers.md`.
- `essay_lookup.ts` — given portal question text + JD context, queries n8n webhook → returns cached or freshly-drafted answer.
- `approval.ts` — pause → notify n8n via webhook → wait for resume signal (long-poll up to 6 hours).
- `screenshots.ts` — auto-screenshot every step, upload to Drive `/JobHunt/<Company>_<Role>/screenshots/`.

## Per-portal scripts (each extends `FormFillBot`)

### `workday.ts`

Workday tenants: detect at runtime by URL pattern `*.myworkdayjobs.com`. Standard flow:
1. Click `Apply`.
2. Sign up if first time at this tenant (use a configured placeholder such as `candidate+<tenant>@example.com`).
3. Email-verify by polling Gmail (label `JobHunt/verification`).
4. Multi-page form. Standard sections: My Information / My Experience / Application Questions / Voluntary Disclosures / Self Identify / Review.
5. Upload resume PDF in My Experience.
6. Application Questions: free-text → essay_lookup.
7. Pause for candidate approval on Review page.
8. Click Submit on resume.

### `greenhouse.ts`

URL pattern `*.greenhouse.io`. Single long form. Drag-drop or file-picker resume upload. Custom questions vary per company → essay_lookup.

### `lever.ts`

`*.lever.co/jobs/*`. Modal-based. Resume upload + small Q&A. Often async file processing → wait for spinner.

### `taleo.ts`

`*.taleo.net`. Legacy. Multi-step wizard. Email signup required.

### `smartrecruiters.ts`

`jobs.smartrecruiters.com/*`. Modal-based, OAuth signup option (use Gmail).

### `icims.ts`

`*.icims.com`. Legacy. Tab-based UI. Pre-fill from LinkedIn often offered — use it.

### `linkedin_easy_apply.ts`

In-LinkedIn. Use candidate's logged-in session. Single-modal flow. ⚠️ Risky for ToS — only run with candidate's explicit toggle.

### `naukri_1click.ts`

Naukri.com 1-click apply. Quick. No essays usually.

## Convention

```ts
const bot = new WorkdayBot({ jdUrl, profile, n8nWebhook });
await bot.run({ draftOnly: true });  // pause at Review, don't submit
// or
await bot.run({ draftOnly: false }); // submit after candidate's APPROVE
```

## Validation by Antigravity

Before any portal goes live, Antigravity:
1. Runs script on Workday/Greenhouse/Lever **public demo sandboxes** (each has one).
2. Confirms screenshot at every step matches expected.
3. Confirms approval pause works (n8n webhook receives + waits + resumes).
4. Confirms `submit` would have clicked the right button (in `--dry-run` mode, replaces submit with screenshot+log).

Only after Antigravity signs off → portal listed in `apply.json` dispatch table.

## Recovery

- Selector drift: Antigravity opens browser visually, takes screenshots, identifies the new selector, opens PR with patch. Until patched, that portal falls back to **manual-only mode** in apply.json (candidate gets Drive link to tailored docs + JD URL, applies by hand).
- Captcha hit: notify candidate via Gmail + WhatsApp; pause that portal.
- Login expired: re-prompt candidate for fresh cookie via secure form.
