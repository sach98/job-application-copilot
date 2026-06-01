from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "JOBHUNT_CREDENTIALS_PATH",
        str(Path.home() / ".config/jobhunt/credentials.json"),
    )
)


def _read_credentials_file(path: str | Path = DEFAULT_CREDENTIALS_PATH) -> dict[str, Any]:
    credentials_path = Path(path).expanduser()
    if not credentials_path.exists():
        return {}
    with credentials_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def load_credentials(path: str | Path = DEFAULT_CREDENTIALS_PATH) -> dict[str, Any]:
    credentials: dict[str, Any] = {}
    env_json = os.environ.get("JOBHUNT_CREDENTIALS_JSON")
    if env_json:
        try:
            parsed = json.loads(env_json)
            if isinstance(parsed, dict):
                credentials.update(parsed)
        except json.JSONDecodeError:
            pass
    credentials.update(_read_credentials_file(path))
    return credentials


def get_source_credentials(source: str) -> dict[str, Any]:
    source_key = source.lower()
    credentials = load_credentials()
    from_file = credentials.get(source_key) or credentials.get(source_key.replace("_", "-")) or {}
    result = from_file.copy() if isinstance(from_file, dict) else {}

    prefix = source_key.upper().replace("-", "_")
    for name in ("USERNAME", "EMAIL", "PASSWORD", "TOKEN", "COOKIE", "COOKIES"):
        value = os.environ.get(f"JOBHUNT_{prefix}_{name}") or os.environ.get(f"{prefix}_{name}")
        if value:
            result[name.lower()] = value
    return result


def get_cookie_header(source: str) -> str | None:
    credentials = get_source_credentials(source)
    cookies = credentials.get("cookies") or credentials.get("cookie")
    if isinstance(cookies, str):
        return cookies
    if isinstance(cookies, list):
        return "; ".join(
            f"{cookie.get('name')}={cookie.get('value')}"
            for cookie in cookies
            if isinstance(cookie, dict) and cookie.get("name") and cookie.get("value")
        )
    return None


def cookies_for_playwright(source: str, domain: str) -> list[dict[str, Any]]:
    credentials = get_source_credentials(source)
    cookies = credentials.get("cookies")
    if isinstance(cookies, list):
        return [cookie for cookie in cookies if isinstance(cookie, dict)]
    header = get_cookie_header(source)
    if not header:
        return []
    parsed: list[dict[str, Any]] = []
    for pair in header.split(";"):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        parsed.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )
    return parsed

