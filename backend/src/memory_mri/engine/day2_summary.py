from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def build_day2_summary(
    *,
    artifacts_dir: Path,
    git_commit_hash: str,
    test_count: int | None = None,
) -> dict[str, Any]:
    deterministic = _read_json(artifacts_dir / "day1-mixed-baseline-summary.json")
    gpt = _read_json(artifacts_dir / "gpt-baseline-summary.json")
    exp_09_pairwise = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_ff4ed6ca0666440a85a758168e5ca9b4"
        / "pairwise-replay.json"
    )
    cs_01_pairwise = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_6d6c10d634c140f3af029a3eb7826bde"
        / "pairwise-replay.json"
    )
    exp_09_controls = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_ff4ed6ca0666440a85a758168e5ca9b4"
        / "memory-controls.json"
    )
    cs_01_controls = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_6d6c10d634c140f3af029a3eb7826bde"
        / "memory-controls.json"
    )
    exp_09_ranking = _read_optional_json(
        artifacts_dir
        / "investigations"
        / "inv_ff4ed6ca0666440a85a758168e5ca9b4"
        / "suspicion-ranking.json"
    )
    exp_09_contradictions = _read_optional_json(
        artifacts_dir
        / "investigations"
        / "inv_ff4ed6ca0666440a85a758168e5ca9b4"
        / "contradictions.json"
    )
    exp_09_individual = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_ff4ed6ca0666440a85a758168e5ca9b4"
        / "individual-replay.json"
    )
    cs_01_individual = _read_json(
        artifacts_dir
        / "investigations"
        / "inv_6d6c10d634c140f3af029a3eb7826bde"
        / "individual-replay.json"
    )

    strongest_individual = _strongest_individual([exp_09_individual, cs_01_individual])
    strongest_pairwise = _strongest_pairwise([exp_09_pairwise, cs_01_pairwise])
    total_api_usage = _sum_usage(
        [
            gpt["totals"]["request_token_usage"],
            exp_09_pairwise["api_usage"],
            cs_01_pairwise["api_usage"],
            exp_09_controls["api_usage"],
            cs_01_controls["api_usage"],
            _analysis_usage(exp_09_ranking),
            _analysis_usage(exp_09_contradictions),
        ]
    )
    approximate_api_cost_usd = _estimate_cost_usd(total_api_usage)
    return {
        "git_commit_hash": git_commit_hash,
        "deterministic_baseline": deterministic,
        "gpt_baseline": {
            "overall": gpt["overall"],
            "results_by_domain": gpt["results_by_domain"],
            "results_by_failure_category": gpt["results_by_failure_category"],
            "failed_scenario_ids": gpt["failed_scenario_ids"],
            "model": gpt["model"],
            "prompt_versions": gpt["prompt_versions"],
        },
        "selected_deep_dive_case": {
            "scenario_id": "exp_09",
            "investigation_id": "inv_ff4ed6ca0666440a85a758168e5ca9b4",
        },
        "strongest_individual_replay_result": strongest_individual,
        "strongest_pairwise_result": strongest_pairwise,
        "api_usage": total_api_usage,
        "approximate_api_cost_usd": approximate_api_cost_usd,
        "pricing_reference": {
            "model_alias": "gpt-5.6",
            "priced_tier": "gpt-5.6-sol",
            "input_per_1m_tokens_usd": 5.0,
            "output_per_1m_tokens_usd": 30.0,
        },
        "test_count": test_count,
        "known_limitations": [
            "Pairwise and isolation evidence remain prompt-sensitive.",
            "Correct outcomes after ablation may still be unsupported by remaining evidence.",
            "Public API intentionally withholds benchmark answer-key fields.",
        ],
    }


def write_day2_summary(
    *,
    artifacts_dir: Path,
    git_commit_hash: str,
    test_count: int | None = None,
) -> dict[str, Any]:
    summary = build_day2_summary(
        artifacts_dir=artifacts_dir,
        git_commit_hash=git_commit_hash,
        test_count=test_count,
    )
    json_path = artifacts_dir / "day2-summary.json"
    md_path = artifacts_dir / "day2-summary.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md_path.write_text(render_day2_summary_markdown(summary), encoding="utf-8")
    return summary


def render_day2_summary_markdown(summary: dict[str, Any]) -> str:
    gpt = summary["gpt_baseline"]
    strongest_individual = summary["strongest_individual_replay_result"]
    strongest_pairwise = summary["strongest_pairwise_result"]
    lines = [
        "# Day 2 Summary",
        "",
        f"- Git commit: `{summary['git_commit_hash']}`",
        f"- GPT model: `{gpt['model']}`",
        (
            f"- GPT score: "
            f"`{gpt['overall']['passed_scenarios']}/"
            f"{gpt['overall']['evaluated_scenarios']}`"
        ),
        (
            f"- Deterministic score: "
            f"`{summary['deterministic_baseline']['passed_scenarios']}/"
            f"{summary['deterministic_baseline']['total_scenarios']}`"
        ),
        f"- Deep dive case: `{summary['selected_deep_dive_case']['scenario_id']}`",
        "",
        "## Strongest Individual Replay",
        "",
        (
            f"- `{strongest_individual['scenario_id']}` on "
            f"`{strongest_individual['memory_id']}`: "
            f"delta={strongest_individual['influence_delta']}"
        ),
        "",
        "## Strongest Pairwise Replay",
        "",
        (
            f"- `{strongest_pairwise['scenario_id']}` on "
            f"`{', '.join(strongest_pairwise['target_memory_ids'])}`: "
            f"combined={strongest_pairwise['combined_influence']}, "
            f"interaction={strongest_pairwise['interaction_score']}, "
            f"classification={strongest_pairwise['classification']}"
        ),
        "",
        "## API Usage",
        "",
        f"- Total tokens: `{summary['api_usage']['total_tokens']}`",
        f"- Approximate cost: `${summary['approximate_api_cost_usd']:.4f}`",
        "",
        "## Known Limitations",
        "",
    ]
    for item in summary["known_limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _strongest_individual(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for artifact in artifacts:
        investigation = artifact["investigation"]
        for result in investigation["replay_results"]:
            candidate = {
                "scenario_id": investigation["scenario_id"],
                "memory_id": result["intervention"]["target_memory_ids"][0],
                "intervention_type": result["intervention"]["intervention_type"],
                "influence_delta": result["influence_delta"],
                "action_distribution": result["intervention_action_distribution"],
            }
            if best is None or abs(candidate["influence_delta"]) > abs(best["influence_delta"]):
                best = candidate
    if best is None:
        raise ValueError("no individual replay results found")
    return best


def _strongest_pairwise(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for artifact in artifacts:
        for result in artifact["pair_results"]:
            candidate = {
                "scenario_id": artifact["scenario_id"],
                "target_memory_ids": result["intervention"]["target_memory_ids"],
                "intervention_type": result["intervention"]["intervention_type"],
                "combined_influence": result["combined_influence"],
                "interaction_score": result["interaction_score"],
                "interaction_synergy": result["interaction_synergy"],
                "classification": result["evidence_classification"],
            }
            score = (abs(candidate["combined_influence"]), abs(candidate["interaction_score"]))
            best_score = (
                (-1.0, -1.0)
                if best is None
                else (abs(best["combined_influence"]), abs(best["interaction_score"]))
            )
            if best is None or score > best_score:
                best = candidate
    if best is None:
        raise ValueError("no pairwise replay results found")
    return best


def _sum_usage(usages: list[dict[str, int]]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for usage in usages:
        for key in total:
            total[key] += usage.get(key, 0)
    return total


def _analysis_usage(payload: dict[str, Any] | None) -> dict[str, int]:
    if payload is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return cast(dict[str, int], payload["metadata"]["api_usage"])


def _estimate_cost_usd(usage: dict[str, int]) -> float:
    input_cost = (usage["input_tokens"] / 1_000_000) * 5.0
    output_cost = (usage["output_tokens"] / 1_000_000) * 30.0
    return round(input_cost + output_cost, 6)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)
