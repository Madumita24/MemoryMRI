from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.analysis.models import ContradictionAnalysisArtifact, SuspicionRankingArtifact
from memory_mri.api_models import (
    ApiError,
    ArtifactBuildRequest,
    ArtifactSummary,
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    CacheClearRequest,
    CacheClearResponse,
    CreateInvestigationRequest,
    DomainInfo,
    HealthResponse,
    IndividualReplayRequest,
    InvestigationResultsResponse,
    PairwiseReplayRequest,
    ProposalActionRequest,
    PublicInvestigation,
    PublicScenarioDetail,
    PublicScenarioSummary,
    PublicTrace,
    RunScenarioRequest,
    VerificationRequest,
)
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.domain.actions import DOMAIN_ACTIONS
from memory_mri.engine.benchmark import BenchmarkService
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.engine.gpt_baseline import GPTBaselineService
from memory_mri.engine.repair_proposals import RepairProposalEngine, RepairProposalError
from memory_mri.engine.verification import VerificationEngine
from memory_mri.engine.verification_artifacts import VerificationArtifactEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    BenchmarkCase,
    MemoryControlsArtifact,
    MemoryDiff,
    PairwiseReplayArtifact,
    RepairProposal,
    VerificationArtifact,
    VerificationRun,
)


class MemoryMRIAppServices:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
        analysis_engine_factory: Callable[[], InvestigationAnalysisEngine] | None = None,
        proposal_engine_factory: Callable[[], RepairProposalEngine] | None = None,
        verification_engine_factory: Callable[[], VerificationEngine] | None = None,
        artifact_engine_factory: Callable[[], VerificationArtifactEngine] | None = None,
    ) -> None:
        self.database_url = database_url
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self._analysis_engine_factory = analysis_engine_factory
        self._proposal_engine_factory = proposal_engine_factory
        self._verification_engine_factory = verification_engine_factory
        self._artifact_engine_factory = artifact_engine_factory

    def load_cases(self) -> list[BenchmarkCase]:
        return load_benchmark_cases(self.data_dir)

    def case_lookup(self) -> dict[str, BenchmarkCase]:
        return {case.scenario.id: case for case in self.load_cases()}

    def repository(self) -> BenchmarkRepository:
        return BenchmarkRepository(create_sqlite_session(self.database_url))

    def replay_engine(self) -> CounterfactualReplayEngine:
        return CounterfactualReplayEngine(
            database_url=self.database_url,
            data_dir=self.data_dir,
            artifacts_dir=self.artifacts_dir,
        )

    def analysis_engine(self) -> InvestigationAnalysisEngine:
        if self._analysis_engine_factory is not None:
            return self._analysis_engine_factory()
        return InvestigationAnalysisEngine(
            database_url=self.database_url,
            artifacts_dir=self.artifacts_dir,
        )

    def proposal_engine(self) -> RepairProposalEngine:
        if self._proposal_engine_factory is not None:
            return self._proposal_engine_factory()
        return RepairProposalEngine(
            database_url=self.database_url,
            data_dir=self.data_dir,
            artifacts_dir=self.artifacts_dir,
        )

    def verification_engine(self) -> VerificationEngine:
        if self._verification_engine_factory is not None:
            return self._verification_engine_factory()
        return VerificationEngine(
            database_url=self.database_url,
            data_dir=self.data_dir,
            artifacts_dir=self.artifacts_dir,
        )

    def artifact_engine(self) -> VerificationArtifactEngine:
        if self._artifact_engine_factory is not None:
            return self._artifact_engine_factory()
        return VerificationArtifactEngine(
            database_url=self.database_url,
            data_dir=self.data_dir,
            artifacts_dir=self.artifacts_dir,
        )

    def run_scenario(self, request: RunScenarioRequest) -> PublicTrace:
        case = self.case_lookup().get(request.scenario_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Unknown scenario: {request.scenario_id}")
        runner = (
            FakeAgentRunner()
            if request.runner == "fake"
            else OpenAIAgentRunner(OpenAISettings.from_env())
        )
        try:
            trace = runner.run_scenario(case.scenario, case.memories)
        except OpenAIRunnerError as exc:
            if exc.trace is None:
                raise HTTPException(status_code=502, detail=exc.failure.message) from exc
            trace = exc.trace
        repository = self.repository()
        repository.import_case(case)
        repository.save_trace(trace)
        repository.session.commit()
        return PublicTrace.from_trace(trace)


def create_app(
    *,
    database_url: str = "sqlite:///../artifacts/memory_mri.db",
    data_dir: Path | None = None,
    artifacts_dir: Path | None = None,
    analysis_engine_factory: Callable[[], InvestigationAnalysisEngine] | None = None,
    proposal_engine_factory: Callable[[], RepairProposalEngine] | None = None,
    verification_engine_factory: Callable[[], VerificationEngine] | None = None,
    artifact_engine_factory: Callable[[], VerificationArtifactEngine] | None = None,
) -> FastAPI:
    resolved_data_dir = (data_dir or Path("../benchmark/data")).resolve()
    resolved_artifacts_dir = (artifacts_dir or Path("../artifacts")).resolve()
    services = MemoryMRIAppServices(
        database_url=database_url,
        data_dir=resolved_data_dir,
        artifacts_dir=resolved_artifacts_dir,
        analysis_engine_factory=analysis_engine_factory,
        proposal_engine_factory=proposal_engine_factory,
        verification_engine_factory=verification_engine_factory,
        artifact_engine_factory=artifact_engine_factory,
    )
    app = FastAPI(title="Memory MRI", version="0.2.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/domains", response_model=list[DomainInfo])
    def list_domains() -> list[DomainInfo]:
        return [
            DomainInfo(domain=domain, allowed_actions=list(actions))
            for domain, actions in DOMAIN_ACTIONS.items()
        ]

    @app.get(
        "/scenarios",
        response_model=list[PublicScenarioSummary],
        responses={404: {"model": ApiError}},
    )
    def list_scenarios() -> list[PublicScenarioSummary]:
        return [
            PublicScenarioSummary(
                scenario_id=case.scenario.id,
                title=case.scenario.title,
                domain=case.scenario.domain,
                allowed_actions=case.scenario.allowed_actions,
                memory_count=len(case.memories),
            )
            for case in services.load_cases()
        ]

    @app.get(
        "/scenarios/{scenario_id}",
        response_model=PublicScenarioDetail,
        responses={404: {"model": ApiError}},
    )
    def get_scenario(scenario_id: str) -> PublicScenarioDetail:
        case = services.case_lookup().get(scenario_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
        agent_input = case.scenario.to_agent_input(case.memories)
        return PublicScenarioDetail(
            scenario_id=case.scenario.id,
            title=case.scenario.title,
            domain=case.scenario.domain,
            user_input=case.scenario.user_input,
            allowed_actions=case.scenario.allowed_actions,
            memory_ids=case.scenario.memory_ids,
            agent_input=agent_input,
        )

    @app.post(
        "/runs",
        response_model=PublicTrace,
        responses={404: {"model": ApiError}, 502: {"model": ApiError}},
    )
    def run_scenario(request: RunScenarioRequest) -> PublicTrace:
        return services.run_scenario(request)

    @app.get("/traces/{trace_id}", response_model=PublicTrace, responses={404: {"model": ApiError}})
    def get_trace(trace_id: str) -> PublicTrace:
        trace = services.repository().get_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail=f"Unknown trace: {trace_id}")
        return PublicTrace.from_trace(trace)

    @app.get(
        "/scenarios/{scenario_id}/traces",
        response_model=list[PublicTrace],
        responses={404: {"model": ApiError}},
    )
    def list_scenario_traces(scenario_id: str) -> list[PublicTrace]:
        if scenario_id not in services.case_lookup():
            raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
        traces = services.repository().list_traces_for_scenario(scenario_id)
        return [PublicTrace.from_trace(trace) for trace in traces]

    @app.post(
        "/investigations",
        response_model=PublicInvestigation,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def create_investigation(request: CreateInvestigationRequest) -> PublicInvestigation:
        try:
            investigation = services.replay_engine().create_investigation(
                parent_trace_id=request.trace_id,
                mode=request.mode,
                run_count=request.run_count,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if message.startswith("unknown trace") else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return PublicInvestigation.from_investigation(investigation)

    @app.get(
        "/investigations/{investigation_id}",
        response_model=PublicInvestigation,
        responses={404: {"model": ApiError}},
    )
    def get_investigation(investigation_id: str) -> PublicInvestigation:
        try:
            investigation = services.replay_engine().load_investigation(investigation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return PublicInvestigation.from_investigation(investigation)

    @app.post(
        "/investigations/{investigation_id}/individual-replay",
        response_model=PublicInvestigation,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def run_individual_replay(
        investigation_id: str,
        request: IndividualReplayRequest,
    ) -> PublicInvestigation:
        engine = services.replay_engine()
        try:
            if request.operation == "all":
                investigation = engine.run_individual_ablation(investigation_id)
            elif request.operation == "remove":
                if request.memory_id is None:
                    raise HTTPException(status_code=400, detail="memory_id is required for remove")
                engine.replay_without_memory(investigation_id, request.memory_id)
                investigation = engine.load_investigation(investigation_id)
            else:
                if request.memory_id is None:
                    raise HTTPException(status_code=400, detail="memory_id is required for disable")
                engine.replay_with_memory_disabled(investigation_id, request.memory_id)
                investigation = engine.load_investigation(investigation_id)
        except ValueError as exc:
            message = str(exc)
            status_code = (
                404 if "unknown investigation" in message or "is not part" in message else 400
            )
            raise HTTPException(status_code=status_code, detail=message) from exc
        return PublicInvestigation.from_investigation(investigation)

    @app.post(
        "/investigations/{investigation_id}/replay",
        response_model=PublicInvestigation,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def replay_alias(
        investigation_id: str,
        request: IndividualReplayRequest,
    ) -> PublicInvestigation:
        return run_individual_replay(investigation_id, request)

    @app.post(
        "/investigations/{investigation_id}/suspicion-ranking",
        response_model=SuspicionRankingArtifact,
        responses={404: {"model": ApiError}, 502: {"model": ApiError}},
    )
    def run_suspicion_ranking(investigation_id: str) -> SuspicionRankingArtifact:
        try:
            return services.analysis_engine().rank_memories(investigation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post(
        "/investigations/{investigation_id}/contradictions",
        response_model=ContradictionAnalysisArtifact,
        responses={404: {"model": ApiError}, 502: {"model": ApiError}},
    )
    def run_contradictions(investigation_id: str) -> ContradictionAnalysisArtifact:
        try:
            return services.analysis_engine().analyze_contradictions(investigation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post(
        "/investigations/{investigation_id}/pairwise-replay",
        response_model=PairwiseReplayArtifact,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def run_pairwise_replay(
        investigation_id: str,
        request: PairwiseReplayRequest,
    ) -> PairwiseReplayArtifact:
        try:
            return services.replay_engine().replay_pairwise(
                investigation_id,
                memory_a=request.memory_a,
                memory_b=request.memory_b,
                all_pairs=request.all_pairs,
                shared_baseline_runs=request.shared_baseline_runs,
                fresh_baseline_per_pair=request.fresh_baseline_per_pair,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "unknown investigation" in message else 400
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.post(
        "/investigations/{investigation_id}/interactions",
        response_model=PairwiseReplayArtifact,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def interactions_alias(
        investigation_id: str,
        request: PairwiseReplayRequest,
    ) -> PairwiseReplayArtifact:
        return run_pairwise_replay(investigation_id, request)

    @app.post(
        "/investigations/{investigation_id}/proposals",
        response_model=RepairProposal,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}, 502: {"model": ApiError}},
    )
    def generate_proposal(investigation_id: str) -> RepairProposal:
        try:
            return services.proposal_engine().generate_proposal(investigation_id)
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=404) from exc
        except RepairProposalError as exc:
            raise HTTPException(
                status_code=400,
                detail={"detail": exc.failure.message, "code": exc.failure.code},
            ) from exc

    @app.get(
        "/investigations/{investigation_id}/results",
        response_model=InvestigationResultsResponse,
        responses={404: {"model": ApiError}},
    )
    def get_investigation_results(investigation_id: str) -> InvestigationResultsResponse:
        engine = services.replay_engine()
        try:
            investigation = engine.load_investigation(investigation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        investigation_dir = resolved_artifacts_dir / "investigations" / investigation_id
        return InvestigationResultsResponse(
            investigation=PublicInvestigation.from_investigation(investigation),
            suspicion_ranking=_load_optional_json_model(
                investigation_dir / "suspicion-ranking.json",
                SuspicionRankingArtifact,
            ),
            contradictions=_load_optional_json_model(
                investigation_dir / "contradictions.json",
                ContradictionAnalysisArtifact,
            ),
            pairwise_replay=_load_optional_json_model(
                investigation_dir / "pairwise-replay.json",
                PairwiseReplayArtifact,
            ),
            memory_controls=_load_optional_json_model(
                investigation_dir / "memory-controls.json",
                MemoryControlsArtifact,
            ),
        )

    @app.post(
        "/cache/clear",
        response_model=CacheClearResponse,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def clear_cache(request: CacheClearRequest) -> CacheClearResponse:
        runner = OpenAIAgentRunner(OpenAISettings.from_env())
        if request.mode == "all":
            return CacheClearResponse(mode=request.mode, cleared=runner.clear_cache())
        if request.mode == "request_hash":
            if request.request_hash is None:
                raise HTTPException(status_code=400, detail="request_hash is required")
            return CacheClearResponse(
                mode=request.mode,
                cleared=runner.clear_cache_for_request_hash(request.request_hash),
            )
        if request.scenario_id is None:
            raise HTTPException(status_code=400, detail="scenario_id is required")
        if request.scenario_id not in services.case_lookup():
            raise HTTPException(status_code=404, detail=f"Unknown scenario: {request.scenario_id}")
        return CacheClearResponse(
            mode=request.mode,
            cleared=runner.clear_cache_for_scenario(request.scenario_id),
        )

    @app.get(
        "/proposals/{proposal_id}",
        response_model=RepairProposal,
        responses={404: {"model": ApiError}},
    )
    def get_proposal(proposal_id: str) -> RepairProposal:
        try:
            return services.proposal_engine().get_proposal(proposal_id)
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=404) from exc

    @app.post(
        "/proposals/{proposal_id}/approve",
        response_model=RepairProposal,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def approve_proposal(proposal_id: str, request: ProposalActionRequest) -> RepairProposal:
        try:
            return services.proposal_engine().approve_proposal(
                proposal_id,
                approval_reason=request.reason,
                notes=request.notes,
            )
        except (ValueError, RepairProposalError) as exc:
            raise _repair_http(exc) from exc

    @app.post(
        "/proposals/{proposal_id}/reject",
        response_model=RepairProposal,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def reject_proposal(proposal_id: str, request: ProposalActionRequest) -> RepairProposal:
        try:
            return services.proposal_engine().reject_proposal(
                proposal_id,
                rejection_reason=request.reason,
                notes=request.notes,
            )
        except (ValueError, RepairProposalError) as exc:
            raise _repair_http(exc) from exc

    @app.post(
        "/proposals/{proposal_id}/apply",
        response_model=dict[str, object],
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def apply_proposal(proposal_id: str) -> dict[str, object]:
        try:
            version = services.proposal_engine().apply_proposal(proposal_id)
            return version.model_dump(mode="json")
        except (ValueError, RepairProposalError) as exc:
            raise _repair_http(exc) from exc

    @app.post(
        "/proposals/{proposal_id}/revert",
        response_model=dict[str, object],
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def revert_proposal(
        proposal_id: str,
        request: ProposalActionRequest,
    ) -> dict[str, object]:
        try:
            version = services.proposal_engine().revert_proposal(
                proposal_id,
                revert_reason=request.reason,
            )
            return version.model_dump(mode="json")
        except (ValueError, RepairProposalError) as exc:
            raise _repair_http(exc) from exc

    @app.get(
        "/proposals/{proposal_id}/diff",
        response_model=MemoryDiff,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def get_proposal_diff(proposal_id: str) -> MemoryDiff:
        try:
            return services.proposal_engine().preview_memory_diff(proposal_id)
        except (ValueError, RepairProposalError) as exc:
            raise _repair_http(exc) from exc

    @app.post(
        "/verifications/original",
        response_model=VerificationRun,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def verify_original(request: VerificationRequest) -> VerificationRun:
        try:
            return services.verification_engine().verify_original(
                request.proposal_id,
                runner_name=request.runner,
            )
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=400) from exc

    @app.post(
        "/verifications/domain",
        response_model=VerificationRun,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def verify_domain(request: VerificationRequest) -> VerificationRun:
        try:
            return services.verification_engine().verify_domain(
                request.proposal_id,
                runner_name=request.runner,
            )
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=400) from exc

    @app.post(
        "/verifications/full",
        response_model=VerificationRun,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def verify_full(request: VerificationRequest) -> VerificationRun:
        try:
            return services.verification_engine().verify_full_benchmark(
                request.proposal_id,
                runner_name=request.runner,
            )
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=400) from exc

    @app.get(
        "/verifications/{verification_id}",
        response_model=VerificationRun,
        responses={404: {"model": ApiError}},
    )
    def get_verification(verification_id: str) -> VerificationRun:
        try:
            return services.verification_engine().show_verification(verification_id)
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=404) from exc

    @app.post(
        "/benchmarks/run",
        response_model=BenchmarkRunResponse,
        responses={400: {"model": ApiError}},
    )
    def run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResponse:
        if request.runner == "fake":
            summary = BenchmarkService(
                database_url=services.database_url,
                runner=FakeAgentRunner(),
                data_dir=services.data_dir,
            ).run_baseline(
                Path(request.artifact_path or services.artifacts_dir / "api-benchmark-summary.json")
            )
            run_id = summary.get("run_id")
            return BenchmarkRunResponse(
                run_id=None if run_id is None else str(run_id),
                summary=summary,
            )
        summary = GPTBaselineService(
            database_url=services.database_url,
            runner=OpenAIAgentRunner(OpenAISettings.from_env()),
            data_dir=services.data_dir,
            git_commit_hash="api-run",
            git_branch_state="api-run",
        ).run_official_baseline(
            summary_json_path=Path(request.summary_json_path)
            if request.summary_json_path is not None
            else services.artifacts_dir / "api-gpt-benchmark-summary.json",
            summary_md_path=Path(
                request.summary_md_path or services.artifacts_dir / "api-gpt-benchmark-summary.md"
            ),
            traces_dir=Path(request.traces_dir or services.artifacts_dir / "api-gpt-traces"),
        )
        run_id = summary.get("run_id")
        return BenchmarkRunResponse(
            run_id=None if run_id is None else str(run_id),
            summary=summary,
        )

    @app.get(
        "/benchmarks/{run_id}",
        response_model=dict[str, object],
        responses={404: {"model": ApiError}},
    )
    def get_benchmark(run_id: str) -> dict[str, object]:
        run = services.repository().get_benchmark_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown benchmark run")
        return run

    @app.post(
        "/artifacts",
        response_model=ArtifactSummary,
        responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    )
    def build_artifact(request: ArtifactBuildRequest) -> ArtifactSummary:
        try:
            artifact = services.artifact_engine().build_artifact(
                request.proposal_id,
                verification_id=request.verification_id,
            )
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=400) from exc
        return ArtifactSummary(
            artifact_id=artifact.artifact_id,
            certificate_id=artifact.certificate_id,
            verification_verdict=artifact.verification_verdict.value,
            scenario_id=artifact.scenario_id,
            proposal_id=artifact.proposal_id,
        )

    @app.get(
        "/artifacts/{artifact_id}",
        response_model=VerificationArtifact,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def get_artifact(artifact_id: str) -> VerificationArtifact:
        try:
            return services.artifact_engine().get_artifact(artifact_id)
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=404) from exc

    @app.get(
        "/artifacts/{artifact_id}/json",
        response_model=VerificationArtifact,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def get_artifact_json(artifact_id: str) -> VerificationArtifact:
        return get_artifact(artifact_id)

    @app.get(
        "/artifacts/{artifact_id}/markdown",
        response_class=PlainTextResponse,
        responses={404: {"model": ApiError}, 400: {"model": ApiError}},
    )
    def get_artifact_markdown(artifact_id: str) -> str:
        try:
            return services.artifact_engine().render_markdown(artifact_id)
        except ValueError as exc:
            raise _http_from_error(str(exc), default_status=404) from exc

    return app


ModelT = TypeVar("ModelT")


def _load_optional_json_model(path: Path, model_type: type[ModelT]) -> ModelT | None:
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return, attr-defined]


def _http_from_error(message: str, *, default_status: int) -> HTTPException:
    lowered = message.lower()
    code = "bad_request"
    status = default_status
    if "unknown" in lowered or "missing" in lowered:
        status = 404
        code = "not_found"
    elif "stale" in lowered:
        status = 409
        code = "stale_snapshot"
    elif "not applicable" in lowered:
        status = 400
        code = "verification_not_applicable"
    elif "hash mismatch" in lowered:
        status = 409
        code = "hash_mismatch"
    elif "invalid" in lowered:
        status = 400
        code = "invalid_transition"
    return HTTPException(status_code=status, detail={"detail": message, "code": code})


def _repair_http(exc: ValueError | RepairProposalError) -> HTTPException:
    if isinstance(exc, RepairProposalError):
        status = 409 if "stale" in exc.failure.code else 400
        if exc.failure.code.startswith("missing") or exc.failure.code == "unknown_proposal":
            status = 404
        return HTTPException(
            status_code=status,
            detail={"detail": exc.failure.message, "code": exc.failure.code},
        )
    return _http_from_error(str(exc), default_status=400)


app = create_app()
