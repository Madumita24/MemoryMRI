from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import close_all_sessions

from memory_mri.api import create_app
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.db.session import create_sqlite_session, dispose_sqlite_engines
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import ExecutionTrace

CS_01_TRACE_ID = "trace_6e225da6d76a4ae0b76ec0ee5c11fc5c"
CS_01_INVESTIGATION_ID = "inv_6d6c10d634c140f3af029a3eb7826bde"
CS_01_PROPOSAL_ID = "proposal_bf551979f6ea4313893c45a505967b91"
CS_01_ARTIFACT_ID = "artifact_2eeca7add7ca4e0194280e37c0835b43"

EXP_09_TRACE_ID = "trace_0f0477f7cb5c497cb209414fce5e1016"
EXP_09_INVESTIGATION_ID = "inv_ff4ed6ca0666440a85a758168e5ca9b4"
EXP_09_ARTIFACT_ID = "artifact_d70a75d09c59496fbf98f85a039b8f8d"


class DemoSeedManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demo_root: str
    database_url: str
    data_dir: str
    artifacts_dir: str
    seed_dir: str
    cs_01_trace_id: str
    cs_01_investigation_id: str
    cs_01_proposal_id: str
    cs_01_artifact_id: str
    exp_09_trace_id: str
    exp_09_investigation_id: str
    exp_09_artifact_id: str


class ApiStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    method: str
    path: str
    status_code: int
    response_id: str | None = None
    error: str | None = None


def reset_demo_state(demo_root: Path) -> None:
    close_all_sessions()
    dispose_sqlite_engines()
    if demo_root.exists():
        shutil.rmtree(demo_root)


def seed_demo_state(
    *,
    demo_root: Path,
    data_dir: Path,
    source_artifacts_dir: Path,
    seed_dir: Path,
) -> DemoSeedManifest:
    reset_demo_state(demo_root)
    artifacts_dir = demo_root / "artifacts"
    investigations_dir = artifacts_dir / "investigations"
    investigations_dir.mkdir(parents=True, exist_ok=True)

    for investigation_id in (CS_01_INVESTIGATION_ID, EXP_09_INVESTIGATION_ID):
        shutil.copytree(
            source_artifacts_dir / "investigations" / investigation_id,
            investigations_dir / investigation_id,
            dirs_exist_ok=True,
        )
    for filename in (
        "day1-mixed-baseline-summary.json",
        "gpt-baseline-summary.json",
    ):
        shutil.copy2(source_artifacts_dir / filename, artifacts_dir / filename)

    database_path = demo_root / "memory_mri_demo.db"
    database_url = f"sqlite:///{database_path}"
    repository = BenchmarkRepository(create_sqlite_session(database_url))
    for case in load_benchmark_cases(data_dir):
        repository.import_case(case)

    for trace_name in ("cs_01-original-trace.json", "exp_09-original-trace.json"):
        trace = ExecutionTrace.model_validate_json(
            (seed_dir / "traces" / trace_name).read_text(encoding="utf-8")
        )
        repository.save_trace(trace)
    repository.session.commit()
    repository.session.close()

    manifest = DemoSeedManifest(
        demo_root=str(demo_root),
        database_url=database_url,
        data_dir=str(data_dir),
        artifacts_dir=str(artifacts_dir),
        seed_dir=str(seed_dir),
        cs_01_trace_id=CS_01_TRACE_ID,
        cs_01_investigation_id=CS_01_INVESTIGATION_ID,
        cs_01_proposal_id=CS_01_PROPOSAL_ID,
        cs_01_artifact_id=CS_01_ARTIFACT_ID,
        exp_09_trace_id=EXP_09_TRACE_ID,
        exp_09_investigation_id=EXP_09_INVESTIGATION_ID,
        exp_09_artifact_id=EXP_09_ARTIFACT_ID,
    )
    (demo_root / "demo-manifest.json").write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return manifest


def load_demo_manifest(demo_root: Path) -> DemoSeedManifest:
    return DemoSeedManifest.model_validate_json(
        (demo_root / "demo-manifest.json").read_text(encoding="utf-8")
    )


def run_demo_workflow(
    *,
    manifest: DemoSeedManifest,
    source_artifacts_dir: Path,
    summary_json_path: Path,
    summary_md_path: Path,
) -> dict[str, Any]:
    with TestClient(
        create_app(
            database_url=manifest.database_url,
            data_dir=Path(manifest.data_dir),
            artifacts_dir=Path(manifest.artifacts_dir),
        )
    ) as client:
        exp09_result = _run_exp09_api_workflow(client, manifest)
    cs01_summary = _load_cs01_unsafe_demo(source_artifacts_dir, manifest)
    summary = {
        "selected_demo_case": "cs_01",
        "selected_demo_outcome": "repair blocked as unsupported",
        "cs_01": cs01_summary,
        "exp_09": exp09_result,
        "api_smoke": {
            "endpoint_order": [step.model_dump(mode="json") for step in exp09_result["api_steps"]],
            "errors": [
                step.model_dump(mode="json") for step in exp09_result["api_steps"] if step.error
            ],
            "artifact_retrieval": {
                "artifact_id": exp09_result["artifact"]["artifact_id"],
                "json_retrieved": True,
                "markdown_retrieved": True,
            },
        },
    }
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(json.dumps(_jsonable(summary), indent=2), encoding="utf-8")
    summary_md_path.write_text(_render_demo_markdown(summary), encoding="utf-8")
    return summary


def _run_exp09_api_workflow(
    client: TestClient,
    manifest: DemoSeedManifest,
) -> dict[str, Any]:
    steps: list[ApiStepRecord] = []
    case_lookup = {case.scenario.id: case for case in load_benchmark_cases(Path(manifest.data_dir))}

    trace_response = client.get(f"/traces/{manifest.exp_09_trace_id}")
    steps.append(
        _step("load_original_trace", "GET", f"/traces/{manifest.exp_09_trace_id}", trace_response)
    )
    trace_payload = trace_response.json()

    investigation_response = client.get(f"/investigations/{manifest.exp_09_investigation_id}")
    steps.append(
        _step(
            "load_investigation",
            "GET",
            f"/investigations/{manifest.exp_09_investigation_id}",
            investigation_response,
        )
    )

    results_response = client.get(f"/investigations/{manifest.exp_09_investigation_id}/results")
    steps.append(
        _step(
            "show_preserved_results",
            "GET",
            f"/investigations/{manifest.exp_09_investigation_id}/results",
            results_response,
        )
    )
    results_payload = results_response.json()

    proposal_response = client.post(f"/investigations/{manifest.exp_09_investigation_id}/proposals")
    steps.append(
        _step(
            "generate_proposal",
            "POST",
            f"/investigations/{manifest.exp_09_investigation_id}/proposals",
            proposal_response,
            response_id_key="proposal_id",
        )
    )
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["proposal_id"]

    approve_response = client.post(
        f"/proposals/{proposal_id}/approve",
        json={"reason": "Approved to document the prompt/policy escalation path."},
    )
    steps.append(
        _step(
            "approve_proposal",
            "POST",
            f"/proposals/{proposal_id}/approve",
            approve_response,
            response_id_key="proposal_id",
        )
    )

    apply_response = client.post(f"/proposals/{proposal_id}/apply")
    steps.append(
        _step(
            "apply_proposal_blocked",
            "POST",
            f"/proposals/{proposal_id}/apply",
            apply_response,
        )
    )

    diff_response = client.get(f"/proposals/{proposal_id}/diff")
    steps.append(
        _step(
            "generate_memory_diff",
            "GET",
            f"/proposals/{proposal_id}/diff",
            diff_response,
            response_id_key="diff_id",
        )
    )

    verify_original = client.post(
        "/verifications/original",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    steps.append(
        _step(
            "verify_original_case",
            "POST",
            "/verifications/original",
            verify_original,
            response_id_key="verification_id",
        )
    )

    verify_domain = client.post(
        "/verifications/domain",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    steps.append(
        _step(
            "verify_domain",
            "POST",
            "/verifications/domain",
            verify_domain,
            response_id_key="verification_id",
        )
    )

    verify_full = client.post(
        "/verifications/full",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    steps.append(
        _step(
            "verify_full_benchmark",
            "POST",
            "/verifications/full",
            verify_full,
            response_id_key="verification_id",
        )
    )

    artifact_response = client.post("/artifacts", json={"proposal_id": proposal_id})
    steps.append(
        _step(
            "generate_verification_artifact",
            "POST",
            "/artifacts",
            artifact_response,
            response_id_key="artifact_id",
        )
    )
    artifact_payload = artifact_response.json()
    artifact_id = artifact_payload["artifact_id"]

    artifact_json = client.get(f"/artifacts/{artifact_id}/json")
    steps.append(
        _step(
            "retrieve_artifact_json",
            "GET",
            f"/artifacts/{artifact_id}/json",
            artifact_json,
            response_id_key="artifact_id",
        )
    )

    artifact_markdown = client.get(f"/artifacts/{artifact_id}/markdown")
    steps.append(
        _step(
            "retrieve_artifact_markdown",
            "GET",
            f"/artifacts/{artifact_id}/markdown",
            artifact_markdown,
        )
    )

    return {
        "scenario_id": "exp_09",
        "original_trace": {
            "trace_id": trace_payload["trace_id"],
            "selected_action": trace_payload["selected_action"],
            "expected_action": case_lookup["exp_09"].scenario.expected_action,
        },
        "investigation_id": manifest.exp_09_investigation_id,
        "suspicion_ranking": results_payload["suspicion_ranking"],
        "contradictions": results_payload["contradictions"],
        "individual_replay": results_payload["investigation"]["replay_results"],
        "pairwise_replay": results_payload["pairwise_replay"],
        "support_validity_audit": results_payload["memory_controls"],
        "proposal": proposal_payload,
        "approval": approve_response.json(),
        "apply_blocked": {
            "status_code": apply_response.status_code,
            "detail": apply_response.json(),
        },
        "diff": diff_response.json(),
        "original_verification": verify_original.json(),
        "domain_verification": verify_domain.json(),
        "full_verification": verify_full.json(),
        "artifact": artifact_json.json(),
        "artifact_markdown_preview": artifact_markdown.text,
        "api_steps": steps,
    }


def _load_cs01_unsafe_demo(
    source_artifacts_dir: Path,
    manifest: DemoSeedManifest,
) -> dict[str, Any]:
    artifact_path = (
        source_artifacts_dir / "verification-artifacts" / f"{manifest.cs_01_artifact_id}.json"
    )
    proposal_path = (
        source_artifacts_dir
        / "investigations"
        / manifest.cs_01_investigation_id
        / "repair-proposals"
        / f"{manifest.cs_01_proposal_id}.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    return {
        "scenario_id": "cs_01",
        "trace_id": manifest.cs_01_trace_id,
        "investigation_id": manifest.cs_01_investigation_id,
        "proposal_id": manifest.cs_01_proposal_id,
        "proposal_repair_type": proposal["repair_type"],
        "proposal_status": proposal["proposal_status"],
        "support_validity_result": proposal["support_validity_result"],
        "verification_verdict": artifact["verification_verdict"],
        "artifact_id": artifact["artifact_id"],
        "artifact_fingerprint": artifact["content_hash"],
        "blocked_reason": (
            "cs_01 remains an unsafe-repair-prevention demo because the preserved workflow "
            "did not produce a support-valid verified repair."
        ),
    }


def _step(
    step_name: str,
    method: str,
    path: str,
    response: Any,
    *,
    response_id_key: str | None = None,
) -> ApiStepRecord:
    payload: dict[str, Any] | None = None
    try:
        payload = response.json()
    except Exception:
        payload = None
    response_id = None
    if response_id_key is not None and isinstance(payload, dict):
        response_id = payload.get(response_id_key)
    error = None
    if response.status_code >= 400:
        error = response.text
    return ApiStepRecord(
        step=step_name,
        method=method,
        path=path,
        status_code=response.status_code,
        response_id=None if response_id is None else str(response_id),
        error=error,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _render_demo_markdown(summary: dict[str, Any]) -> str:
    cs01 = summary["cs_01"]
    exp09 = summary["exp_09"]
    lines = [
        "# Day 3F Demo Workflow",
        "",
        "## Selected Demo Case",
        "",
        f"- Primary demo case: `{summary['selected_demo_case']}`",
        f"- Primary outcome: `{summary['selected_demo_outcome']}`",
        "",
        "## cs_01 Unsafe-Repair Prevention",
        "",
        f"- Proposal ID: `{cs01['proposal_id']}`",
        f"- Repair type: `{cs01['proposal_repair_type']}`",
        f"- Verification verdict: `{cs01['verification_verdict']}`",
        f"- Artifact ID: `{cs01['artifact_id']}`",
        f"- Artifact fingerprint: `{cs01['artifact_fingerprint']}`",
        f"- Outcome: {cs01['blocked_reason']}",
        "",
        "## exp_09 Memory-Independent Workflow",
        "",
        f"- Original action: `{exp09['original_trace']['selected_action']}`",
        f"- Expected action: `{exp09['original_trace']['expected_action']}`",
        f"- Proposal ID: `{exp09['proposal']['proposal_id']}`",
        f"- Repair type: `{exp09['proposal']['repair_type']}`",
        f"- Apply blocked: `{exp09['apply_blocked']['status_code']}`",
        f"- Verification verdict: `{exp09['artifact']['verification_verdict']}`",
        f"- Artifact ID: `{exp09['artifact']['artifact_id']}`",
        "",
        "## API Smoke Order",
        "",
    ]
    lines.extend(
        [
            f"- `{step['method']} {step['path']}` -> `{step['status_code']}`"
            for step in summary["api_smoke"]["endpoint_order"]
        ]
    )
    return "\n".join(lines)
