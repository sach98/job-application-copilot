"""Shared helpers for calling the Claude CLI and parsing strict-JSON replies."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Fallbacks tried only when `claude` is not on PATH: Apple-Silicon Homebrew, Intel
# Homebrew, npm global prefix, and the official per-user installer location.
CLAUDE_BIN_FALLBACKS = (
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "/usr/bin/claude",
    str(Path.home() / ".local" / "bin" / "claude"),
    str(Path.home() / ".claude" / "local" / "claude"),
)
MODEL = "claude-sonnet-4-6"
MAX_ATTEMPTS = 3
AUTH_MARKERS = ("authenticate", "401", "invalid authentication", "oauth")


class ClaudeAuthError(RuntimeError):
    """Raised when the CLI fails auth (401). Retrying won't help. Re-login needed."""


def resolve_claude_bin(env: dict | None = None) -> str:
    """Locate the Claude CLI: CLAUDE_BIN override, then PATH, then known install dirs.

    Raises FileNotFoundError with the places searched rather than failing later with a
    confusing 'No such file or directory' from subprocess.
    """
    env = os.environ if env is None else env
    override = env.get("CLAUDE_BIN")
    if override:
        return override

    on_path = shutil.which("claude", path=env.get("PATH"))
    if on_path:
        return on_path

    for candidate in CLAUDE_BIN_FALLBACKS:
        if os.access(candidate, os.X_OK):
            return candidate

    raise FileNotFoundError(
        "claude CLI not found. Install it, put it on PATH, or set CLAUDE_BIN. "
        f"Searched PATH and: {', '.join(CLAUDE_BIN_FALLBACKS)}"
    )


def extract_json(text: str) -> dict:
    """Pull a strict JSON object out of a model reply.

    Tries: direct parse, then a ```json fenced block, then the first {..last }.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("no JSON object found in model output")


def call_claude(prompt_path: Path, payload: dict, timeout: int = 600, model: str = MODEL,
                effort: str | None = None) -> dict:
    """Run the Claude CLI with a system prompt file and a JSON payload on stdin.

    Returns the parsed inner strict-JSON object (unwrapping the CLI's
    `--output-format json` envelope, whose model text lives under "result").
    `effort` (e.g. "high") maps to the CLI --effort flag for higher-quality reasoning.
    """
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    if not prompt:
        raise FileNotFoundError(f"prompt missing at {prompt_path}")

    # Drop ANTHROPIC_API_KEY so the CLI falls back to OAuth (Claude Pro) creds.
    # The desktop session injects a key that headless -p rejects with 401.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = [resolve_claude_bin(), "-p", prompt, "--model", model, "--output-format", "json"]
    if effort:
        cmd += ["--effort", effort]
    stdin = json.dumps(payload)

    last_err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            proc = subprocess.run(
                cmd, input=stdin, capture_output=True, text=True, timeout=timeout, env=env
            )
        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"claude CLI {last_err} (after {MAX_ATTEMPTS} attempts)")

        combined = f"{proc.stdout}\n{proc.stderr}".lower()
        if proc.returncode != 0:
            last_err = proc.stderr.strip()[:500] or proc.stdout.strip()[:500]
            # Auth failures never recover via retry: surface immediately.
            if any(m in combined for m in AUTH_MARKERS):
                raise ClaudeAuthError(f"claude CLI auth failed (401). Re-login: claude /login. {last_err}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"claude CLI exit {proc.returncode} (after {MAX_ATTEMPTS} attempts): {last_err}")

        raw = proc.stdout.strip()
        try:
            envelope = json.loads(raw)
            inner = envelope.get("result", raw) if isinstance(envelope, dict) else raw
        except json.JSONDecodeError:
            inner = raw
        return extract_json(inner if isinstance(inner, str) else json.dumps(inner))
