from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Pattern


# JOBHUNT_KEYWORDS_PATH points at the file directly; otherwise fall back to the
# JOBHUNT_ROOT convention used across the repo.
_JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT") or (Path.home() / "JobHunt"))
DEFAULT_KEYWORDS_PATH = Path(
    os.environ.get("JOBHUNT_KEYWORDS_PATH") or (_JOBHUNT_ROOT / "docs" / "keywords.md")
)


@dataclass(frozen=True)
class KeywordConfig:
    tier1: list[str]
    tier2: list[str]
    exclude_regex: str
    location_regex: str
    experience_filters: list[str]

    @property
    def tier1_pattern(self) -> Pattern[str]:
        return _compile_phrase_pattern(self.tier1)

    @property
    def tier2_pattern(self) -> Pattern[str]:
        return _compile_phrase_pattern(self.tier2)

    @property
    def exclude_pattern(self) -> Pattern[str] | None:
        return re.compile(self.exclude_regex, re.IGNORECASE) if self.exclude_regex else None

    @property
    def location_pattern(self) -> Pattern[str] | None:
        return re.compile(self.location_regex, re.IGNORECASE) if self.location_regex else None

    def matches_tier1(self, text: str) -> bool:
        return bool(self.tier1_pattern.search(text or ""))

    def matches_tier2(self, text: str) -> bool:
        return bool(self.tier2_pattern.search(text or ""))

    def is_excluded(self, text: str) -> bool:
        pattern = self.exclude_pattern
        return bool(pattern and pattern.search(text or ""))

    def matches_location(self, text: str) -> bool:
        pattern = self.location_pattern
        return bool(pattern and pattern.search(text or ""))


def _compile_phrase_pattern(phrases: Iterable[str]) -> Pattern[str]:
    escaped: list[str] = []
    for phrase in phrases:
        cleaned = phrase.strip()
        if not cleaned:
            continue
        escaped_phrase = re.escape(cleaned)
        escaped_phrase = re.sub(r"\\\s+", r"\\s+", escaped_phrase)
        escaped.append(rf"(?<!\w){escaped_phrase}(?!\w)")
    if not escaped:
        return re.compile(r"a^")
    return re.compile("|".join(escaped), re.IGNORECASE)


def _heading_to_key(line: str) -> str | None:
    lowered = line.lower()
    if "tier 1" in lowered:
        return "tier1"
    if "tier 2" in lowered:
        return "tier2"
    if "exclude" in lowered:
        return "exclude"
    if "location filter" in lowered:
        return "location"
    if "experience filter" in lowered:
        return "experience"
    return None


def _parse_code_sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "tier1": [],
        "tier2": [],
        "exclude": [],
        "location": [],
        "experience": [],
    }
    active_key: str | None = None
    in_code_block = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading_key = _heading_to_key(line) if line.startswith("##") else None
        if heading_key:
            active_key = heading_key
            in_code_block = False
            continue

        if line.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block and active_key and line:
            sections[active_key].append(line)

    return sections


def _join_regex_lines(lines: list[str]) -> str:
    alternatives = []
    for line in lines:
        for part in line.split("|"):
            stripped = part.strip()
            if stripped:
                alternatives.append(stripped)
    return "|".join(alternatives)


def load_keywords(path: str | Path = DEFAULT_KEYWORDS_PATH) -> KeywordConfig:
    keyword_path = Path(path).expanduser()
    markdown = keyword_path.read_text(encoding="utf-8")
    sections = _parse_code_sections(markdown)
    return KeywordConfig(
        tier1=sections["tier1"],
        tier2=sections["tier2"],
        exclude_regex=_join_regex_lines(sections["exclude"]),
        location_regex=_join_regex_lines(sections["location"]),
        experience_filters=sections["experience"],
    )


def job_text(job: dict) -> str:
    return " ".join(
        str(job.get(key) or "")
        for key in ("title", "company", "location", "jd_text", "description", "summary")
    )


def passes_keyword_filters(
    job: dict,
    config: KeywordConfig | None = None,
    *,
    require_tier1: bool = True,
    require_location: bool = True,
) -> bool:
    config = config or load_keywords()
    text = job_text(job)
    if config.is_excluded(text):
        return False
    if require_tier1 and not config.matches_tier1(text):
        return False
    if require_location:
        location_text = str(job.get("location") or "")
        if not config.matches_location(location_text):
            return False
    return True


def keyword_lists(path: str | Path = DEFAULT_KEYWORDS_PATH) -> tuple[list[str], list[str]]:
    config = load_keywords(path)
    return config.tier1, config.tier2

