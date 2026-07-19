# Architecture

## Current backend shape

As of Sunday, July 19, 2026, Memory MRI is a single Python backend organized around six layers:

1. Benchmark loading and schemas
2. Agent runners
3. Trace persistence and caching
4. Investigation and replay analysis
5. Repair proposal, approval, diff, and versioning
6. Verification artifacts and public API access

## Core modules

- `benchmark/data/*.json`: reviewed 30-scenario benchmark corpus
- `backend/src/memory_mri/schemas.py`: shared contracts for scenarios, memories, traces, replay artifacts, repair proposals, diffs, verifications, and verification artifacts
- `backend/src/memory_mri/benchmark_loader.py`: validated benchmark loading
- `backend/src/memory_mri/agents/fake.py`: deterministic regression runner
- `backend/src/memory_mri/agents/openai_runner.py`: GPT-backed runner with strict structured output validation
- `backend/src/memory_mri/engine/`: benchmark, replay, repair, verification, and artifact engines
- `backend/src/memory_mri/api.py`: public FastAPI surface
- `backend/src/memory_mri/demo.py`: reproducible Day 3 demo seeding and smoke workflow helpers

## Privacy boundary

Benchmark records contain both operational data and benchmark-private evaluation data.

Agent-visible operational data includes:

- scenario ID
- domain
- user input
- allowed actions
- realistic memory fields such as content, dates, status, confidence, source, entity, priority, and superseding relationships

Benchmark-private data includes:

- `expected_action`
- `expected_problematic_memory_ids`
- `failure_category`
- `explanation`
- evaluator configuration
- fake-runner-only hints

Only `AgentScenario.to_agent_input(...)` and `build_agent_input(...)` may produce model-facing payloads. Public scenario endpoints also use the sanitized operational subset.

## Runner layer

### FakeAgentRunner

The deterministic runner uses documented heuristics from memory content and metadata rather than scenario IDs. It reads:

- retrieval priority
- status
- validity windows
- superseding relationships
- entity match
- policy and customer-status combinations

This produces the stable mixed baseline of `22/30`.

### OpenAIAgentRunner

The GPT runner:

- uses the safe serializer
- loads versioned prompts per domain
- validates structured responses
- rejects unknown actions and cited memory IDs
- records latency and usage
- supports caching
- persists structured errors separately from evaluated failures

The frozen official baseline remains `28/30` on `gpt-5.6`.

## Caching and traces

The request hash depends on:

- scenario ID
- user input
- allowed actions
- canonical agent-visible memory snapshot
- requested model
- prompt version
- rendered prompt-content hash
- serializer schema version
- relevant inference settings

It explicitly excludes benchmark-private answer-key fields.

Each trace persists:

- run and trace IDs
- agent-visible input
- retrieved memories
- model and prompt version
- selected action, arguments, citations, rationale, and uncertainty
- cache metadata
- latency and usage
- evaluation result when available
- infrastructure errors when evaluation does not occur

## Investigation and repair flow

1. Start from a failed trace.
2. Reconstruct the original agent-visible snapshot.
3. Run individual replay and controls.
4. Run suspicion ranking, contradiction analysis, and pairwise replay.
5. Generate an evidence-gated repair proposal.
6. Require approval before memory mutation.
7. Persist memory versions and Git-style diffs when changes are applicable.
8. Verify original case, domain, and full benchmark outcomes.
9. Generate a deterministic verification artifact with a content fingerprint.

## Verification and artifacts

Verification supports these verdicts:

- `VERIFIED_IMPROVEMENT`
- `IMPROVEMENT_WITH_REGRESSIONS`
- `NO_MEASURABLE_CHANGE`
- `FAILED_TO_REPAIR`
- `UNSUPPORTED_BEHAVIOR_CHANGE`
- `VERIFICATION_INCONCLUSIVE`
- `MEMORY_REPAIR_NOT_APPLICABLE`

Reviewed Day 3 outcomes:

- `cs_01`: unsafe repair blocked, artifact verdict `VERIFICATION_INCONCLUSIVE`
- `exp_09`: no memory repair recommended, artifact verdict `MEMORY_REPAIR_NOT_APPLICABLE`

## API and CLI

The FastAPI app currently exposes `34` endpoints covering:

- health
- domains and scenarios
- trace execution and retrieval
- investigations
- replay and analysis
- proposals, approvals, apply/revert
- diffs
- verifications
- benchmarks
- verification artifacts
- cache clearing

The CLI mirrors the same Day 3 workflow for local use and scripted smoke tests.

## Runtime isolation

Reviewed artifacts live under `artifacts/`.

Mutable runtime smoke outputs now live under `artifacts/demo-runtime/` by default so `seed-demo` and `reset-demo` do not delete reviewed evidence trees. That separation was added during Day 3G stabilization.
