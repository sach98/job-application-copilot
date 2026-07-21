# Follow-up prompt: Claude Sonnet 4.6

Draft LinkedIn InMail / email follow-up to hiring manager or referral candidate.

## Inputs (JSON)

```json
{
  "stage": "inmail_1 | inmail_2 | email_1 | email_2 | warm_intro",
  "company": "...",
  "role": "...",
  "jd_summary": "<1 paragraph>",
  "applied_at": "<ISO>",
  "hiring_mgr": { "name": "...", "title": "...", "linkedin_url": "..." },
  "referral_candidate": { "name": "...", "title": "...", "mutual_with_candidate": "<how connected>" } | null,
  "previous_message_sent": "<text of inmail_1 if stage=inmail_2>"
}
```

## Output (JSON)

```json
{
  "subject": "<for email stages, else null>",
  "body": "<message body>",
  "tone": "warm | formal | curious",
  "char_count": 0
}
```

## Stage-specific rules

- **inmail_1** (sent immediately after application): 150-220 chars. NO ask. Pure value/curiosity. e.g. "Noticed your team is hiring a Senior BA and applied today. Your post on <topic> resonated; would love to know how the BA team partners with <function>."
- **inmail_2** (7 days later, no reply): different angle. Mention 1 thing you've done since (read their blog, used their product, etc.). Soft ask: "open to a 15-min chat?".
- **email_1** / **email_2**: longer (200-400 words), more formal, subject line included.
- **warm_intro**: to a mutual / referral candidate. Acknowledge their time. Specific ask: "would you be open to introducing me to <hiring_mgr.name>?". Mention you've already applied so it's not cold.

## Hard rules

- No "Dear Sir/Madam". Use name.
- No "I came across your profile" (LinkedIn standard cliché).
- No multi-paragraph rambles in InMail. Punchy.
- Mention the role you applied for explicitly.
- Sign off as "candidate" not "Best regards {{candidate_name}}".

JSON only.
