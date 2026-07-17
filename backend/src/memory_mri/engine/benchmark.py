from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

from memory_mri.agents.base import AgentRunner
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import BenchmarkCase, ScenarioResult


class BenchmarkService:
    def __init__(self, database_url: str, runner: AgentRunner, data_dir: Path) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.runner = runner
        self.data_dir = data_dir

    def run_baseline(self, artifact_path: Path) -> dict[str, object]:
        cases = load_benchmark_cases(self.data_dir)
        for case in cases:
            self.repository.import_case(case)
        self.session.commit()

        results: list[ScenarioResult] = []
        for case in cases:
            trace = self.runner.run_scenario(case.scenario, case.memories)
            if trace.selected_action is None or trace.passed is None:
                raise ValueError(
                    f"benchmark trace for scenario {case.scenario.id} is missing evaluation output"
                )
            self.repository.save_trace(trace)
            results.append(
                ScenarioResult(
                    scenario_id=case.scenario.id,
                    selected_action=trace.selected_action,
                    expected_action=case.scenario.expected_action,
                    passed=trace.passed,
                    retrieved_memory_ids=trace.retrieved_memory_ids,
                    trace_id=trace.trace_id,
                    error=None,
                )
            )

        summary = build_summary(cases, results)
        run_id = f"baseline_{uuid4().hex}"
        total_scenarios = cast(int, summary["total_scenarios"])
        passed_scenarios = cast(int, summary["passed_scenarios"])
        self.repository.save_benchmark_run(
            run_id=run_id,
            total_scenarios=total_scenarios,
            passed_scenarios=passed_scenarios,
            payload=summary,
        )
        self.session.commit()

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary


def build_summary(cases: list[BenchmarkCase], results: list[ScenarioResult]) -> dict[str, object]:
    result_map = {result.scenario_id: result for result in results}
    summary_by_domain: dict[str, dict[str, int]] = {}
    summary_by_failure: dict[str, dict[str, int]] = {}
    for case in cases:
        result = result_map[case.scenario.id]
        domain_bucket = summary_by_domain.setdefault(
            case.scenario.domain.value, {"total": 0, "passed": 0, "failed": 0}
        )
        domain_bucket["total"] += 1
        domain_bucket["passed" if result.passed else "failed"] += 1

        failure_bucket = summary_by_failure.setdefault(
            case.scenario.failure_category, {"total": 0, "passed": 0, "failed": 0}
        )
        failure_bucket["total"] += 1
        failure_bucket["passed" if result.passed else "failed"] += 1

    passed_scenarios = sum(1 for result in results if result.passed)
    return {
        "total_scenarios": len(results),
        "passed_scenarios": passed_scenarios,
        "failed_scenarios": len(results) - passed_scenarios,
        "results_by_domain": summary_by_domain,
        "results_by_failure_category": summary_by_failure,
        "scenario_results": [result.model_dump(mode="json") for result in results],
    }
