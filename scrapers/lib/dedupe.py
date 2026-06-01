from __future__ import annotations

import hashlib
import re
from typing import Iterable


def fingerprint(job: dict) -> str:
    basis = "|".join(
        _clean(str(job.get(key) or "")) for key in ("title", "company", "location")
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _clean(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def dedupe_jobs(jobs: Iterable[dict], *, use_fingerprint: bool = False) -> list[dict]:
    seen_primary: set[tuple[str, str]] = set()
    seen_fingerprint: set[str] = set()
    result: list[dict] = []

    for job in jobs:
        source = str(job.get("source") or "")
        external_id = str(job.get("external_id") or "")
        primary = (source, external_id)
        if external_id and primary in seen_primary:
            continue
        fp = fingerprint(job)
        if use_fingerprint and fp in seen_fingerprint:
            continue
        if external_id:
            seen_primary.add(primary)
        if use_fingerprint:
            seen_fingerprint.add(fp)
        result.append(job)

    return result

