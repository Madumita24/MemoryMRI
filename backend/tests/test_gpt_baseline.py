from __future__ import annotations

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.engine.gpt_baseline import GPTBaselineRunConfig, build_gpt_baseline_summary


def test_gpt_baseline_summary_separates_infrastructure_errors(benchmark_cases) -> None:
    case_a = benchmark_cases[0]
    case_b = benchmark_cases[1]
    trace_a = FakeAgentRunner().run_scenario(case_a.scenario, case_a.memories)
    trace_b = FakeAgentRunner().run_scenario(case_b.scenario, case_b.memories)
    trace_b.selected_action = None
    trace_b.passed = None
    trace_b.evaluation.evaluator_result = None
    trace_b.error = {
        "code": "transient_openai_error",
        "message": "network timeout",
        "retryable": True,
        "attempts": 2,
    }

    summary = build_gpt_baseline_summary(
        cases=[case_a, case_b],
        traces=[
            {
                "scenario_id": case_a.scenario.id,
                "domain": case_a.scenario.domain.value,
                "failure_category": case_a.scenario.failure_category,
                "trace_id": trace_a.trace_id,
                "result_type": "evaluated",
                "expected_action": case_a.scenario.expected_action,
                "actual_selected_action": trace_a.selected_action,
                "passed": trace_a.passed,
                "cache_status": trace_a.cache.hit,
                "execution_source": trace_a.execution_source,
                "latency_ms": trace_a.latency_ms,
                "request_token_usage": trace_a.request_token_usage,
                "cached_original_token_usage": trace_a.cached_original_token_usage,
                "billable_api_call": trace_a.billable_api_call,
                "error": None,
            },
            {
                "scenario_id": case_b.scenario.id,
                "domain": case_b.scenario.domain.value,
                "failure_category": case_b.scenario.failure_category,
                "trace_id": trace_b.trace_id,
                "result_type": "infrastructure_error",
                "expected_action": case_b.scenario.expected_action,
                "actual_selected_action": None,
                "passed": None,
                "cache_status": False,
                "execution_source": "error",
                "latency_ms": 0,
                "request_token_usage": None,
                "cached_original_token_usage": None,
                "billable_api_call": False,
                "error": trace_b.error,
            },
        ],
        requested_model="gpt-5.6",
        prompt_version="v1",
        run_config=GPTBaselineRunConfig(
            requested_model="gpt-5.6",
            prompt_version="v1",
            timeout_seconds=30.0,
            max_retries=2,
            cache_enabled=False,
            reasoning_effort=None,
            verbosity="low",
            cache_dir="artifacts/openai_cache",
        ),
        git_commit_hash="abc123",
        git_branch_state="## main",
        timestamp="2026-07-18T00:00:00Z",
        total_latency_ms=1,
        total_request_tokens={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        total_cached_original_tokens={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        total_billable_api_calls=0,
    )

    assert summary["overall"]["attempted_scenarios"] == 2
    assert summary["overall"]["evaluated_scenarios"] == 1
    assert summary["overall"]["infrastructure_errors"] == 1
    assert len(summary["infrastructure_errors"]) == 1
