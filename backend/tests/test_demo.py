from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from memory_mri.api import create_app
from memory_mri.demo import (
    CS_01_INVESTIGATION_ID,
    EXP_09_INVESTIGATION_ID,
    load_demo_manifest,
    reset_demo_state,
    run_demo_workflow,
    seed_demo_state,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = ROOT / "artifacts"
BENCHMARK_ROOT = ROOT / "benchmark" / "data"
SEED_ROOT = ARTIFACTS_ROOT / "demo-seed"


def test_seed_reset_and_end_to_end_demo_workflow(tmp_path: Path) -> None:
    demo_root = tmp_path / "day3f-demo"
    manifest = seed_demo_state(
        demo_root=demo_root,
        data_dir=BENCHMARK_ROOT,
        source_artifacts_dir=ARTIFACTS_ROOT,
        seed_dir=SEED_ROOT,
    )

    assert (demo_root / "demo-manifest.json").exists()
    assert Path(manifest.artifacts_dir, "investigations", CS_01_INVESTIGATION_ID).exists()
    assert Path(manifest.artifacts_dir, "investigations", EXP_09_INVESTIGATION_ID).exists()

    summary = run_demo_workflow(
        manifest=load_demo_manifest(demo_root),
        source_artifacts_dir=ARTIFACTS_ROOT,
        summary_json_path=demo_root / "day3f-demo-summary.json",
        summary_md_path=demo_root / "day3f-demo-summary.md",
    )

    assert summary["selected_demo_case"] == "cs_01"
    assert summary["exp_09"]["proposal"]["repair_type"] == "ESCALATE_PROMPT_OR_POLICY_REVIEW"
    assert summary["exp_09"]["apply_blocked"]["status_code"] == 400
    assert summary["exp_09"]["artifact"]["verification_verdict"] == "MEMORY_REPAIR_NOT_APPLICABLE"
    assert (demo_root / "day3f-demo-summary.json").exists()
    assert (demo_root / "day3f-demo-summary.md").exists()

    reset_demo_state(demo_root)
    assert not demo_root.exists()


def test_demo_api_integration_covers_artifact_path(tmp_path: Path) -> None:
    demo_root = tmp_path / "day3f-api-demo"
    manifest = seed_demo_state(
        demo_root=demo_root,
        data_dir=BENCHMARK_ROOT,
        source_artifacts_dir=ARTIFACTS_ROOT,
        seed_dir=SEED_ROOT,
    )
    client = TestClient(
        create_app(
            database_url=manifest.database_url,
            data_dir=Path(manifest.data_dir),
            artifacts_dir=Path(manifest.artifacts_dir),
        )
    )

    investigation_response = client.get(f"/investigations/{manifest.exp_09_investigation_id}")
    assert investigation_response.status_code == 200

    results_response = client.get(f"/investigations/{manifest.exp_09_investigation_id}/results")
    assert results_response.status_code == 200

    proposal_response = client.post(f"/investigations/{manifest.exp_09_investigation_id}/proposals")
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal_id"]

    approve_response = client.post(
        f"/proposals/{proposal_id}/approve",
        json={"reason": "API demo approval for non-repair workflow."},
    )
    assert approve_response.status_code == 200

    apply_response = client.post(f"/proposals/{proposal_id}/apply")
    assert apply_response.status_code == 400

    diff_response = client.get(f"/proposals/{proposal_id}/diff")
    assert diff_response.status_code == 200

    verify_response = client.post(
        "/verifications/original",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    assert verify_response.status_code == 200

    artifact_response = client.post("/artifacts", json={"proposal_id": proposal_id})
    assert artifact_response.status_code == 200
    artifact_id = artifact_response.json()["artifact_id"]

    assert client.get(f"/artifacts/{artifact_id}").status_code == 200
    assert client.get(f"/artifacts/{artifact_id}/json").status_code == 200
    assert client.get(f"/artifacts/{artifact_id}/markdown").status_code == 200
