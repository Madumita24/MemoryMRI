from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

from fastapi import FastAPI, HTTPException

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.analysis.models import ContradictionAnalysisArtifact, SuspicionRankingArtifact
from memory_mri.api_models import (
    ApiError,
    CacheClearRequest,
    CacheClearResponse,
    CreateInvestigationRequest,
    DomainInfo,
    HealthResponse,
    IndividualReplayRequest,
    InvestigationResultsResponse,
    PairwiseReplayRequest,
    PublicInvestigation,
    PublicScenarioDetail,
    PublicScenarioSummary,
    PublicTrace,
    RunScenarioRequest,
)
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.domain.actions import DOMAIN_ACTIONS
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import BenchmarkCase, MemoryControlsArtifact, PairwiseReplayArtifact


class MemoryMRIAppServices:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
        analysis_engine_factory: Callable[[], InvestigationAnalysisEngine] | None = None,
    ) -> None:
        self.database_url = database_url
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self._analysis_engine_factory = analysis_engine_factory

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
) -> FastAPI:
    resolved_data_dir = (data_dir or Path("../benchmark/data")).resolve()
    resolved_artifacts_dir = (artifacts_dir or Path("../artifacts")).resolve()
    services = MemoryMRIAppServices(
        database_url=database_url,
        data_dir=resolved_data_dir,
        artifacts_dir=resolved_artifacts_dir,
        analysis_engine_factory=analysis_engine_factory,
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

    return app


ModelT = TypeVar("ModelT")


def _load_optional_json_model(path: Path, model_type: type[ModelT]) -> ModelT | None:
    if not path.exists():
        return None
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return, attr-defined]


app = create_app()
