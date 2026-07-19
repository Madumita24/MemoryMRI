# Architecture

## Current Day 2 architecture

Memory MRI uses one shared backend across all three domains:

- `benchmark/data/*.json` contains the reviewed benchmark corpus.
- `memory_mri.schemas` defines validated contracts for benchmark records, agent-visible input, traces, investigations, and replay artifacts.
- `memory_mri.benchmark_loader` loads and validates the 30 scenarios.
- `memory_mri.agents.fake.FakeAgentRunner` provides deterministic regression behavior.
- `memory_mri.agents.openai_runner.OpenAIAgentRunner` provides GPT-backed execution with strict structured outputs, caching, and trace persistence.
- `memory_mri.analysis.engine.InvestigationAnalysisEngine` handles suspicion ranking and contradiction analysis.
- `memory_mri.engine.counterfactual_replay.CounterfactualReplayEngine` handles individual replay, no-memory controls, isolation controls, and pairwise replay.
- `memory_mri.api` exposes a public FastAPI surface with sanitized response models.

## Privacy boundary

Benchmark records contain both operational and benchmark-private data.

- Agent-visible operational data:
  scenario ID, domain, user input, allowed actions, and memory fields that a real system could retrieve.
- Benchmark-private data:
  `expected_action`, `expected_problematic_memory_ids`, `failure_category`, `explanation`, `evaluator_config`, and fake-runner-only benchmark hints.

`build_agent_input(...)` and `AgentScenario.to_agent_input(...)` are the only supported model-facing serializers. Public scenario API endpoints also use only the agent-visible subset.

## Prompt and runner flow

1. Load benchmark case data.
2. Build agent-visible input in canonical memory order from `scenario.memory_ids`.
3. Load the versioned prompt for the domain.
4. Call the OpenAI Responses API with a strict JSON-schema response model.
5. Validate the selected action against `allowed_actions`.
6. Validate cited memory IDs against the agent-visible snapshot.
7. Persist a structured trace with latency, usage, cache metadata, and any structured error details.

The runner never stores hidden chain-of-thought. Only a short rationale is persisted.

## Caching

The OpenAI cache key includes:

- scenario ID
- user input
- allowed actions
- canonical agent-visible memory snapshot
- requested model
- prompt version
- rendered prompt-content hash
- agent-input schema version
- relevant inference settings

It explicitly excludes benchmark-private answer-key data.

Cache hits are reported separately from live model latency:

- `execution_source`
- `cache_lookup_latency_ms`
- `original_model_latency_ms`
- `request_token_usage`
- `cached_original_token_usage`
- `billable_api_call`

## Trace format

Each trace persists:

- scenario and run IDs
- agent-visible input and memory snapshot
- model and prompt version
- selected action, action arguments, citations, rationale, and uncertainty
- cache status
- latency
- token usage
- pass/fail when evaluation exists
- structured infrastructure errors when evaluation does not occur

The public API exposes sanitized traces that omit benchmark answer-key fields such as the evaluator’s expected action.

## Investigation flow

1. Create an investigation from a genuine failed trace.
2. Reconstruct the original agent-visible memory snapshot.
3. Run individual replay interventions.
4. Rank suspicious memories.
5. Analyze pairwise contradictions.
6. Run pairwise replay and control conditions.
7. Persist JSON and Markdown artifacts for every executed step.

## Public interfaces

FastAPI endpoints now expose:

- health and domain metadata
- sanitized scenario metadata
- trace retrieval
- scenario-scoped trace listing
- investigation creation and retrieval
- individual replay
- suspicion ranking
- contradiction analysis
- pairwise replay
- cache clearing

The unified Day 2 CLI mirrors these core workflows.

## Deliberate constraints

- Deterministic evaluation remains the pass/fail authority.
- Benchmark answer-key fields do not cross the agent boundary.
- Repair proposals are intentionally deferred to Day 3.
- Day 2 metrics come only from executed runs and persisted artifacts.
