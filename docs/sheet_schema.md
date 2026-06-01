# Google Sheet tracker schema

Spreadsheet: **JobHunt Tracker** in candidate@example.com Drive.

## Tab 1: `applications`

| Col | Name | Type | Notes |
|-----|------|------|-------|
| A | `date` | date | when scraped |
| B | `company` | text | |
| C | `role` | text | |
| D | `source` | enum | linkedin / naukri / indeed / glassdoor / google_jobs / wellfound / hirist / instahyre / cutshort / iimjobs / yc / foundit / ambitionbox |
| E | `jd_url` | url | |
| F | `posted_at` | datetime | when posting went live |
| G | `salary` | text | parsed range, e.g. "₹22-28 LPA" |
| H | `fit_score` | number 0-1 | from scoring fn |
| I | `score_components` | json | breakdown |
| J | `hiring_mgr_name` | text | |
| K | `hiring_mgr_title` | text | |
| L | `hiring_mgr_linkedin` | url | |
| M | `hiring_mgr_email` | email | from Hunter/Apollo |
| N | `team_members` | json | array of {name,title,linkedin} |
| O | `referrals` | json | candidate's 1st-degree at company |
| P | `dossier_url` | url | Drive link to dossier (Phase 2 B1) |
| Q | `resume_url` | url | Drive link to tailored PDF |
| R | `cl_url` | url | Drive link to cover letter PDF |
| S | `essay_answers_url` | url | Drive link to essay_answers.md |
| T | `screenshots_url` | url | Drive folder of submission screenshots |
| U | `status` | enum | new / queued / pending_review / applied / followup_1_sent / followup_2_sent / responded / interview / offer / rejected / closed_no_response / skipped |
| V | `queued_at` | datetime | when entered apply queue |
| W | `applied_at` | datetime | |
| X | `followup_1_due` | date | applied_at + 7d |
| Y | `followup_1_sent_at` | datetime | |
| Z | `followup_2_due` | date | applied_at + 14d |
| AA | `followup_2_sent_at` | datetime | |
| AB | `response_at` | datetime | |
| AC | `response_summary` | text | |
| AD | `interview_date` | datetime | |
| AE | `offer_details` | json | base, variable, ESOPs, joining bonus |
| AF | `notes` | text | candidate's free-text |

## Tab 2: `daily_cap_tracker`

| Col | Name | Type |
|-----|------|------|
| A | `date` | date |
| B | `cap` | number (default 5) |
| C | `applied_count` | number |
| D | `pending_review_count` | number |
| E | `skipped_count` | number |

## Tab 3: `weekly_review`

Auto-populated Sunday 18:00 IST. Pivot of Tab 1.

| Col | Name |
|-----|------|
| A | `week_ending` |
| B | `applications_sent` |
| C | `responses_received` |
| D | `response_rate` |
| E | `interviews_scheduled` |
| F | `top_source` |
| G | `avg_fit_score_applied` |
| H | `avg_fit_score_responded` |

## Tab 4: `enrichment_cache`

Avoid burning Hunter.io quota. Cached per-company.

| Col | Name |
|-----|------|
| A | `company` |
| B | `domain` |
| C | `email_pattern` (e.g. `{first}.{last}@hdfclife.com`) |
| D | `linkedin_company_url` |
| E | `last_refreshed` |
