from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


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


@dataclass(frozen=True)
class SuspicionScoringConfig:
    cited_by_original_agent: float = 1.0
    stale_status: float = 1.6
    expired_validity: float = 1.6
    superseded_status: float = 1.2
    entity_mismatch: float = 1.4
    missing_validity_dates: float = 0.5
    unusually_high_retrieval_priority: float = 0.9
    metadata_conflict_with_another_memory: float = 1.3
    potentially_wrong_decision_context: float = 1.1
    invalid_temporal_overlap: float = 0.8
    active_memory_explicitly_superseded_by_another: float = 1.5
    high_priority_threshold: int = 95
    prioritization_weight_deterministic: float = 0.5
    prioritization_weight_semantic: float = 0.5

    @classmethod
    def from_env(cls) -> "SuspicionScoringConfig":
        _load_dotenv()
        return cls(
            cited_by_original_agent=_read_float(
                "SUSPICION_WEIGHT_CITED_BY_ORIGINAL_AGENT",
                cls.cited_by_original_agent,
            ),
            stale_status=_read_float(
                "SUSPICION_WEIGHT_STALE_STATUS",
                cls.stale_status,
            ),
            expired_validity=_read_float(
                "SUSPICION_WEIGHT_EXPIRED_VALIDITY",
                cls.expired_validity,
            ),
            superseded_status=_read_float(
                "SUSPICION_WEIGHT_SUPERSEDED_STATUS",
                cls.superseded_status,
            ),
            entity_mismatch=_read_float(
                "SUSPICION_WEIGHT_ENTITY_MISMATCH",
                cls.entity_mismatch,
            ),
            missing_validity_dates=_read_float(
                "SUSPICION_WEIGHT_MISSING_VALIDITY_DATES",
                cls.missing_validity_dates,
            ),
            unusually_high_retrieval_priority=_read_float(
                "SUSPICION_WEIGHT_UNUSUALLY_HIGH_RETRIEVAL_PRIORITY",
                cls.unusually_high_retrieval_priority,
            ),
            metadata_conflict_with_another_memory=_read_float(
                "SUSPICION_WEIGHT_METADATA_CONFLICT",
                cls.metadata_conflict_with_another_memory,
            ),
            potentially_wrong_decision_context=_read_float(
                "SUSPICION_WEIGHT_WRONG_DECISION_CONTEXT",
                cls.potentially_wrong_decision_context,
            ),
            invalid_temporal_overlap=_read_float(
                "SUSPICION_WEIGHT_INVALID_TEMPORAL_OVERLAP",
                cls.invalid_temporal_overlap,
            ),
            active_memory_explicitly_superseded_by_another=_read_float(
                "SUSPICION_WEIGHT_ACTIVE_MEMORY_EXPLICITLY_SUPERSEDED",
                cls.active_memory_explicitly_superseded_by_another,
            ),
            high_priority_threshold=_read_int(
                "SUSPICION_HIGH_PRIORITY_THRESHOLD",
                cls.high_priority_threshold,
            ),
            prioritization_weight_deterministic=_read_float(
                "SUSPICION_PRIORITIZATION_WEIGHT_DETERMINISTIC",
                cls.prioritization_weight_deterministic,
            ),
            prioritization_weight_semantic=_read_float(
                "SUSPICION_PRIORITIZATION_WEIGHT_SEMANTIC",
                cls.prioritization_weight_semantic,
            ),
        )

    def signal_weights(self) -> dict[str, float]:
        return {
            "cited_by_original_agent": self.cited_by_original_agent,
            "stale_status": self.stale_status,
            "expired_validity": self.expired_validity,
            "superseded_status": self.superseded_status,
            "entity_mismatch": self.entity_mismatch,
            "missing_validity_dates": self.missing_validity_dates,
            "unusually_high_retrieval_priority": self.unusually_high_retrieval_priority,
            "metadata_conflict_with_another_memory": self.metadata_conflict_with_another_memory,
            "potentially_wrong_decision_context": self.potentially_wrong_decision_context,
            "invalid_temporal_overlap": self.invalid_temporal_overlap,
            "active_memory_explicitly_superseded_by_another": (
                self.active_memory_explicitly_superseded_by_another
            ),
        }

    def normalized_signal_weights(self) -> dict[str, float]:
        weights = self.signal_weights()
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("suspicion signal weights must sum to a positive value")
        return {name: (weight / total) for name, weight in weights.items()}

    def documented_weights(self) -> dict[str, Any]:
        return {
            "signal_weights": self.signal_weights(),
            "normalized_signal_weights": self.normalized_signal_weights(),
            "high_priority_threshold": self.high_priority_threshold,
            "prioritization_weights": {
                "deterministic": self.prioritization_weight_deterministic,
                "semantic": self.prioritization_weight_semantic,
            },
        }


@dataclass(frozen=True)
class SemanticAnalysisSettings:
    suspicion_prompt_version: str
    contradiction_prompt_version: str

    @classmethod
    def from_env(cls) -> "SemanticAnalysisSettings":
        _load_dotenv()
        return cls(
            suspicion_prompt_version=os.getenv(
                "OPENAI_SUSPICION_PROMPT_VERSION",
                "v1",
            ),
            contradiction_prompt_version=os.getenv(
                "OPENAI_CONTRADICTION_PROMPT_VERSION",
                "v1",
            ),
        )
