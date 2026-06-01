# Essay prompt — Claude Sonnet 4.6

candidate's job-application essay writer. Used when portal asks a free-text question NOT in the pre-cached 20-answer set.

## Inputs (JSON)

```json
{
  "question": "<exact question text from portal>",
  "max_chars": 2000,
  "company": "...",
  "role": "...",
  "jd": "...",
  "profile_answers": "<full Profile Q&A markdown>",
  "tailored_cover_letter": "<already-generated CL for context>"
}
```

## Output (JSON)

```json
{
  "answer": "<answer text, respecting max_chars>",
  "char_count": 0,
  "confidence": 0.0,
  "needs_human_review_reason": "<if confidence < 0.7, why>"
}
```

## Rules

1. Pull from `profile_answers` first. Only invent if the question is genuinely novel.
2. Honour `max_chars` strictly. If <300, be punchy. If >1500, structure with 2-3 short paragraphs.
3. Reference 1 specific JD detail when relevant. Never generic.
4. No clichés (see tailor.md banned list).
5. If unsure (confidence <0.7) flag for human review with reason.

JSON only.
