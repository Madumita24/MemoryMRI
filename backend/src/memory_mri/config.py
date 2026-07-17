from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    dotenv_path = Path(__file__).resolve().parents[3] / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    model: str
    timeout_seconds: float
    max_retries: int
    cache_enabled: bool
    prompt_version: str
    reasoning_effort: str | None
    verbosity: str | None
    cache_dir: Path

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None) -> "OpenAISettings":
        _load_dotenv()
        resolved_cache_dir = cache_dir or Path("../artifacts/openai_cache").resolve()
        return cls(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
            timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
            cache_enabled=_read_bool("OPENAI_CACHE_ENABLED", False),
            prompt_version=os.getenv("OPENAI_PROMPT_VERSION", "v1"),
            reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT"),
            verbosity=os.getenv("OPENAI_VERBOSITY", "low"),
            cache_dir=resolved_cache_dir,
        )
