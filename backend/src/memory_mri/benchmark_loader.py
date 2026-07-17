from __future__ import annotations

import json
from pathlib import Path

from memory_mri.schemas import BenchmarkCase, BenchmarkDomainFile


def load_benchmark_cases(data_dir: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for path in sorted(data_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        domain_file = BenchmarkDomainFile.model_validate(payload)
        cases.extend(domain_file.cases)
    _validate_global_uniqueness(cases)
    return cases


def _validate_global_uniqueness(cases: list[BenchmarkCase]) -> None:
    scenario_ids = [case.scenario.id for case in cases]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario IDs must be globally unique")
    memory_ids = [memory.id for case in cases for memory in case.memories]
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("memory IDs must be globally unique")
