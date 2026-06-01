from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Iterable


SCHEMA_KEYS = [
    "source",
    "external_id",
    "title",
    "company",
    "location",
    "jd_text",
    "jd_url",
    "posted_at",
    "scraped_at",
    "salary",
    "hiring_mgr_hint",
    "experience_required",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first(raw: dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return default


def parse_datetime(value: Any, *, now: datetime | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        lowered = text.lower()
        now = now or datetime.now(UTC)

        relative_match = re.search(
            r"(\d+)\s*(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months)\s+ago",
            lowered,
        )
        if lowered in {"today", "just posted", "new"}:
            parsed = now
        elif lowered == "yesterday":
            parsed = now - timedelta(days=1)
        elif relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2)
            if unit.startswith(("minute", "min")):
                parsed = now - timedelta(minutes=amount)
            elif unit.startswith(("hour", "hr")):
                parsed = now - timedelta(hours=amount)
            elif unit.startswith("day"):
                parsed = now - timedelta(days=amount)
            elif unit.startswith("week"):
                parsed = now - timedelta(weeks=amount)
            else:
                parsed = now - timedelta(days=amount * 30)
        else:
            normalized = text.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(text)
                except (TypeError, ValueError):
                    for fmt in ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%d/%m/%Y"):
                        try:
                            parsed = datetime.strptime(text, fmt)
                            break
                        except ValueError:
                            parsed = None
                    if parsed is None:
                        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def datetime_to_iso(value: Any) -> str | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_newer_than(posted_at: Any, since: Any, *, include_unknown: bool = False) -> bool:
    if not since:
        return True
    posted = parse_datetime(posted_at)
    if not posted:
        return include_unknown
    since_dt = parse_datetime(since)
    if not since_dt:
        return True
    return posted >= since_dt


def _stable_external_id(source: str, title: str, company: str, url: str) -> str:
    basis = "|".join([source or "", title or "", company or "", url or ""])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def extract_experience(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"\b\d{1,2}\s*(?:-|–|to)\s*\d{1,2}\s*\+?\s*(?:years?|yrs?|yr)\b",
        r"\b\d{1,2}\s*\+?\s*(?:years?|yrs?|yr)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return None


def extract_hiring_manager_hint(text: str) -> str | None:
    if not text:
        return None
    for line in re.split(r"[\r\n]+", text):
        if re.search(r"\b(hiring manager|recruiter|talent partner|contact)\b", line, re.I):
            return re.sub(r"\s+", " ", line).strip()[:240]
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    return email_match.group(0) if email_match else None


def normalize_job(raw: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    normalized_source = str(source or raw.get("source") or "").strip().lower()
    title = str(_first(raw, ("title", "job_title", "position")) or "").strip()
    company = str(_first(raw, ("company", "company_name", "employer")) or "").strip()
    location = str(_first(raw, ("location", "job_location", "city")) or "").strip()
    jd_text = str(
        _first(raw, ("jd_text", "description", "job_description", "content", "summary")) or ""
    ).strip()
    jd_url = str(_first(raw, ("jd_url", "job_url", "url", "link")) or "").strip()
    posted_at = datetime_to_iso(_first(raw, ("posted_at", "date_posted", "posted_date", "published")))
    external_id = str(
        _first(raw, ("external_id", "id", "job_id", "jobid", "listing_id", "guid")) or ""
    ).strip()
    if not external_id:
        external_id = _stable_external_id(normalized_source, title, company, jd_url)

    salary = _first(raw, ("salary", "salary_range", "compensation", "pay"))
    salary = str(salary).strip() if salary not in (None, "") else None
    hiring_mgr_hint = _first(raw, ("hiring_mgr_hint", "hiring_manager", "recruiter"))
    if hiring_mgr_hint not in (None, ""):
        hiring_mgr_hint = str(hiring_mgr_hint).strip()
    else:
        hiring_mgr_hint = extract_hiring_manager_hint(jd_text)
    experience_required = _first(raw, ("experience_required", "experience", "years_experience"))
    if experience_required not in (None, ""):
        experience_required = str(experience_required).strip()
    else:
        experience_required = extract_experience(" ".join([title, jd_text]))

    item = {
        "source": normalized_source,
        "external_id": external_id,
        "title": title,
        "company": company,
        "location": location,
        "jd_text": jd_text,
        "jd_url": jd_url,
        "posted_at": posted_at,
        "scraped_at": utc_now_iso(),
        "salary": salary,
        "hiring_mgr_hint": hiring_mgr_hint,
        "experience_required": experience_required,
    }
    return {key: item.get(key) for key in SCHEMA_KEYS}


def normalize_jobs(raw_jobs: Iterable[dict[str, Any]], source: str | None = None) -> list[dict[str, Any]]:
    return [normalize_job(raw, source=source) for raw in raw_jobs]


def filter_since(
    jobs: Iterable[dict[str, Any]], since: str | None, *, include_unknown: bool = False
) -> list[dict[str, Any]]:
    return [
        job
        for job in jobs
        if is_newer_than(job.get("posted_at"), since, include_unknown=include_unknown)
    ]


def dump_json_array(jobs: Iterable[dict[str, Any]]) -> None:
    json.dump(list(jobs), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def assert_normalized_schema(job: dict[str, Any]) -> None:
    missing = [key for key in SCHEMA_KEYS if key not in job]
    extra = [key for key in job if key not in SCHEMA_KEYS]
    if missing or extra:
        raise ValueError(f"normalized schema mismatch missing={missing} extra={extra}")

