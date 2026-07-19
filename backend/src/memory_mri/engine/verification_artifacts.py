from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from memory_mri.analysis.models import ContradictionAnalysisArtifact, SuspicionRankingArtifact
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.repair_proposals import RepairProposalEngine
from memory_mri.engine.verification import VerificationEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    MemoryControlsArtifact,
    PairwiseReplayArtifact,
    RepairProposal,
    VerificationArtifact,
    VerificationRun,
)

ARTIFACT_VERSION = "day3e-v1"


class VerificationArtifactEngine:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self.proposal_engine = RepairProposalEngine(
            database_url=database_url,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
        )
        self.verification_engine = VerificationEngine(
            database_url=database_url,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
        )

    def build_artifact(
        self,
        proposal_id: str,
        *,
        verification_id: str | None = None,
    ) -> VerificationArtifact:
        proposal = self.proposal_engine.get_proposal(proposal_id)
        investigation_dir = self.artifacts_dir / "investigations" / proposal.investigation_id
        original_verification, domain_verification, full_verification = self._select_verifications(
            proposal_id=proposal_id,
            verification_id=verification_id,
        )
        suspicion = self._load_optional_model(
            investigation_dir / "suspicion-ranking.json",
            SuspicionRankingArtifact,
        )
        contradictions = self._load_optional_model(
            investigation_dir / "contradictions.json",
            ContradictionAnalysisArtifact,
        )
        pairwise = self._load_optional_model(
            investigation_dir / "pairwise-replay.json",
            PairwiseReplayArtifact,
        )
        controls = self._load_optional_model(
            investigation_dir / "memory-controls.json",
            MemoryControlsArtifact,
        )
        investigation = self.proposal_engine.replay_engine.load_investigation(
            proposal.investigation_id
        )
        diff = self._latest_diff_for_proposal(proposal)
        original_trace = self.repository.get_trace(proposal.evidence_references.parent_trace_id)
        if original_trace is None:
            raise ValueError(
                f"missing parent trace: {proposal.evidence_references.parent_trace_id}"
            )

        artifact_payload = {
            "artifact_id": f"artifact_{uuid4().hex}",
            "certificate_id": "",
            "artifact_version": ARTIFACT_VERSION,
            "investigation_id": proposal.investigation_id,
            "proposal_id": proposal.proposal_id,
            "applied_version_id": proposal.applied_version_id,
            "verification_id": original_verification.verification_id,
            "domain": proposal.domain,
            "scenario_id": proposal.scenario_id,
            "failure_description": proposal.concise_explanation,
            "original_action": original_trace.selected_action,
            "expected_action": proposal.before_state.get("expected_action", ""),
            "likely_influential_memories": self._likely_influential_memories(
                proposal,
                suspicion,
            ),
            "individual_replay_evidence": [
                result.model_dump(mode="json") for result in investigation.replay_results
            ],
            "pairwise_replay_evidence": (
                []
                if pairwise is None
                else [result.model_dump(mode="json") for result in pairwise.pair_results]
            ),
            "memory_dependence_classification": (
                controls.memory_dependence_classification.value
                if controls is not None
                else proposal.before_state.get("memory_dependence_classification", "unknown")
            ),
            "suspicion_analysis": {} if suspicion is None else suspicion.model_dump(mode="json"),
            "contradiction_analysis": (
                {} if contradictions is None else contradictions.model_dump(mode="json")
            ),
            "approved_repair": proposal.model_dump(mode="json"),
            "approval_record": (
                None
                if proposal.approval_record is None
                else proposal.approval_record.model_dump(mode="json")
            ),
            "memory_diff": None if diff is None else diff.model_dump(mode="json"),
            "original_case_verification": self._normalized_verification(original_verification),
            "domain_verification": self._normalized_verification(domain_verification),
            "full_benchmark_verification": self._normalized_verification(full_verification),
            "repaired_failures": full_verification.repaired_failures,
            "new_regressions": full_verification.new_regressions,
            "support_validity_result": proposal.support_validity_result.model_dump(mode="json"),
            "verification_verdict": original_verification.verdict,
            "known_limitations": self._known_limitations(
                proposal=proposal,
                original=original_verification,
                domain=domain_verification,
                full=full_verification,
            ),
            "model": proposal.model,
            "prompt_version": proposal.prompt_version,
            "benchmark_version": Path(original_verification.before_benchmark_id).name,
            "git_commit_hash": self._git_commit_hash(),
            "created_at": datetime.now(timezone.utc),
            "content_hash": "",
        }
        artifact = VerificationArtifact.model_validate(artifact_payload)
        canonical = self._canonical_artifact_content(artifact.model_dump(mode="json"))
        content_hash = hashlib.sha256(canonical).hexdigest()
        artifact = artifact.model_copy(
            update={
                "content_hash": content_hash,
                "certificate_id": content_hash,
            },
            deep=True,
        )
        self._persist_artifact(artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> VerificationArtifact:
        record = self.repository.get_verification_artifact(artifact_id)
        if record is None:
            raise ValueError(f"unknown artifact: {artifact_id}")
        artifact = VerificationArtifact.model_validate_json(record)
        expected_hash = hashlib.sha256(
            self._canonical_artifact_content(artifact.model_dump(mode="json"))
        ).hexdigest()
        if artifact.content_hash != expected_hash:
            raise ValueError("artifact hash mismatch")
        return artifact

    def render_markdown(self, artifact_id: str) -> str:
        artifact = self.get_artifact(artifact_id)
        lines = [
            "# Verification Artifact",
            "",
            "## Executive Summary",
            "",
            f"- Artifact ID: `{artifact.artifact_id}`",
            f"- Certificate ID: `{artifact.certificate_id}`",
            f"- Scenario ID: `{artifact.scenario_id}`",
            f"- Domain: `{artifact.domain.value}`",
            f"- Verdict: `{artifact.verification_verdict.value}`",
            "",
            "## Original Failure",
            "",
            f"- Original action: `{artifact.original_action}`",
            f"- Expected action: `{artifact.expected_action}`",
            f"- Failure description: {artifact.failure_description}",
            "",
            "## Investigation Evidence",
            "",
            (
                f"- Likely influential memories: "
                f"`{', '.join(artifact.likely_influential_memories) or 'none'}`"
            ),
            f"- Memory dependence: `{artifact.memory_dependence_classification}`",
            "",
            "## Proposed Repair",
            "",
            f"- Repair type: `{artifact.approved_repair['repair_type']}`",
            f"- Proposal ID: `{artifact.proposal_id}`",
            "",
            "## Approval",
            "",
            (
                "- No approval record."
                if artifact.approval_record is None
                else f"- Approval reason: {artifact.approval_record['approval_reason']}"
            ),
            "",
            "## Memory Diff",
            "",
            (
                "No memory changes proposed."
                if artifact.memory_diff is None
                else f"- Diff ID: `{artifact.memory_diff['diff_id']}`"
            ),
            "",
            "## Original-case Result",
            "",
            (
                f"- Before: "
                f"`{artifact.original_case_verification['original_case_before']['selected_action']}`"
            ),
            (
                f"- After: "
                f"`{artifact.original_case_verification['original_case_after']['selected_action']}`"
            ),
            "",
            "## Domain Regression Result",
            "",
            (
                f"- Before pass count: "
                f"`{artifact.domain_verification['domain_before']['passed']}`\n"
                f"- After pass count: `{artifact.domain_verification['domain_after']['passed']}`"
            ),
            "",
            "## Full Benchmark Result",
            "",
            (
                f"- Before pass count: "
                f"`{artifact.full_benchmark_verification['full_before']['passed_scenarios']}`\n"
                f"- After pass count: "
                f"`{artifact.full_benchmark_verification['full_after']['passed_scenarios']}`"
            ),
            "",
            "## Regressions",
            "",
            (
                "- None"
                if not artifact.new_regressions
                else "\n".join(f"- `{scenario_id}`" for scenario_id in artifact.new_regressions)
            ),
            "",
            "## Verdict",
            "",
            f"- `{artifact.verification_verdict.value}`",
            "",
            "## Limitations",
            "",
        ]
        if artifact.known_limitations:
            lines.extend([f"- {item}" for item in artifact.known_limitations])
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Artifact Fingerprint",
                "",
                f"- `{artifact.content_hash}`",
            ]
        )
        return "\n".join(lines)

    def _select_verifications(
        self,
        *,
        proposal_id: str,
        verification_id: str | None,
    ) -> tuple[VerificationRun, VerificationRun, VerificationRun]:
        runs = self.repository.list_verification_runs_for_proposal(proposal_id)
        if not runs:
            raise ValueError("artifact not ready: missing verification runs")
        if verification_id is not None:
            primary = next((run for run in runs if run.verification_id == verification_id), None)
            if primary is None:
                raise ValueError(f"unknown verification run: {verification_id}")
        original = next(
            (
                run
                for run in reversed(runs)
                if "original-after-summary" in run.after_benchmark_id
                or run.after_benchmark_id == "not-applicable"
            ),
            runs[-1],
        )
        domain = next(
            (
                run
                for run in reversed(runs)
                if "domain-after-summary" in run.after_benchmark_id
                or run.after_benchmark_id == "not-applicable"
            ),
            original,
        )
        full = next(
            (
                run
                for run in reversed(runs)
                if "full-after-summary" in run.after_benchmark_id
                or run.after_benchmark_id == "not-applicable"
            ),
            domain,
        )
        return original, domain, full

    def _likely_influential_memories(
        self,
        proposal: RepairProposal,
        suspicion: SuspicionRankingArtifact | None,
    ) -> list[str]:
        memory_ids = list(proposal.target_memory_ids)
        if suspicion is not None:
            for item in suspicion.summary.top_ranked_memories[:3]:
                if item not in memory_ids:
                    memory_ids.append(item)
        return memory_ids

    def _latest_diff_for_proposal(self, proposal: RepairProposal) -> Any | None:
        diffs = self.repository.list_memory_diffs_for_proposal(proposal.proposal_id)
        return diffs[-1] if diffs else None

    def _normalized_verification(self, verification: VerificationRun) -> dict[str, Any]:
        payload = verification.model_dump(mode="json")
        payload["before_benchmark_id"] = Path(verification.before_benchmark_id).name
        payload["after_benchmark_id"] = Path(verification.after_benchmark_id).name
        return payload

    def _known_limitations(
        self,
        *,
        proposal: RepairProposal,
        original: VerificationRun,
        domain: VerificationRun,
        full: VerificationRun,
    ) -> list[str]:
        limitations = list(proposal.risks)
        if original.verdict == original.verdict.VERIFICATION_INCONCLUSIVE:
            limitations.append(
                "Original-case verification was inconclusive due to infrastructure errors."
            )
        if domain.infrastructure_errors:
            limitations.append("Domain verification includes infrastructure errors.")
        if full.after_benchmark_id == "not-applicable":
            limitations.append("Full benchmark verification was not applicable for this proposal.")
        if proposal.repair_type in {
            proposal.repair_type.NO_MEMORY_REPAIR_RECOMMENDED,
            proposal.repair_type.ESCALATE_PROMPT_OR_POLICY_REVIEW,
        }:
            limitations.append(
                "No memory mutation was recommended; prompt or policy review is still required."
            )
        return limitations

    def _persist_artifact(self, artifact: VerificationArtifact) -> None:
        self.repository.save_verification_artifact(artifact)
        self.session.commit()
        artifact_dir = self.artifacts_dir / "verification-artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / f"{artifact.artifact_id}.json").write_text(
            artifact.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (artifact_dir / f"{artifact.artifact_id}.md").write_text(
            self.render_markdown(artifact.artifact_id),
            encoding="utf-8",
        )

    def _canonical_artifact_content(self, payload: dict[str, Any]) -> bytes:
        sanitized = json.loads(json.dumps(payload, default=str))
        sanitized.pop("artifact_id", None)
        sanitized.pop("created_at", None)
        sanitized.pop("content_hash", None)
        sanitized.pop("certificate_id", None)
        sanitized = self._normalize_paths(sanitized)
        return json.dumps(sanitized, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _git_commit_hash(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3],
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    def _load_optional_model(self, path: Path, model_type: type[Any]) -> Any | None:
        if not path.exists():
            return None
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def _normalize_paths(self, value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                item_key: self._normalize_paths(item_value, item_key)
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [self._normalize_paths(item, key) for item in value]
        if isinstance(value, str) and key in {"before_benchmark_id", "after_benchmark_id"}:
            return Path(value).name
        return value
