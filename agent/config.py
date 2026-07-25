"""Configuration and secrets.

Deliberately dependency-free: a hackathon venue is exactly where `uv add
python-dotenv` fails because the wifi is saturated. Twelve lines of parsing beat
a dependency here.

Secrets live in `.env`, which is gitignored. `.env.example` documents the keys.
Real environment variables always win over the file, so CI or a shell export can
override without editing anything.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@lru_cache(maxsize=1)
def _file_values() -> dict[str, str]:
    """Parse .env. Missing file is not an error: the agent must run without it."""
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get(name: str, default: str = "") -> str:
    """Environment variable, falling back to .env, then to `default`.

    A variable that is *present but empty* in the environment wins over .env and
    means "explicitly unset". Without this, `SERPAPI_KEY= uv run ...` would
    silently fall through to the file and quietly re-enable the key -- which
    would make the degraded-mode demo untestable, and that demo is the one the
    track actually grades.
    """
    if name in os.environ:
        return os.environ[name] or default
    return _file_values().get(name) or default


def serpapi_key() -> str:
    """SerpAPI key, empty string when unset.

    An empty key is a normal, expected state: the agent must degrade cleanly
    rather than crash, and the degraded path is the one the track grades.
    """
    return get("SERPAPI_KEY")


def ollama_host() -> str:
    return get("OLLAMA_HOST", "http://localhost:11434")


def gemma_model() -> str:
    return get("GEMMA_MODEL", "gemma4:12b")


def redacted(secret: str) -> str:
    """Render a secret safe to print in a log or a demo recording."""
    if not secret:
        return "(absente)"
    return f"{secret[:4]}...{secret[-4:]} ({len(secret)} caractères)"
