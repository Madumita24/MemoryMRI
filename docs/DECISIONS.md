# Decisions

## Day 1

### JSON benchmark source files

Reviewed source data lives in version-controlled JSON files so scenarios and memories remain auditable and easy to diff.

### Shared scenario model

All domains reuse the same `AgentScenario` model and benchmark execution engine. Domain-specific differences are expressed through action enums, prompt templates, and scenario content rather than separate pipelines.

### Deterministic fake runner

Tests and local development use a fake runner that never needs API credentials. It exercises retrieval, action selection, evaluation, and persistence without introducing LLM variance.

### Mixed benchmark baseline

The benchmark baseline must contain both passes and failures in each domain. This preserves already-correct cases for regression protection and keeps failed cases available for later replay, repair proposal, and verification work. The fake runner therefore uses reviewed heuristic scoring from memory attributes instead of a universal fail-first rule.

### Explicit agent-input serializer

Benchmark cases include private answer-key fields that are necessary for deterministic evaluation but unsafe to expose to GPT-5.6. The codebase now uses an explicit serializer that emits only agent-visible operational data, while fake-runner hints and evaluation labels remain private benchmark data.

### Responses API with strict schema parsing

The GPT-backed runner uses the OpenAI Responses API with a strict Pydantic response schema. This keeps model output constrained to allowed actions, cited memory IDs, concise rationale, and uncertainty flags while rejecting malformed or out-of-policy responses before they reach the evaluator.

### SQLite first

SQLite is sufficient for local benchmark imports, trace persistence, and artifact generation during the MVP foundation phase.

## Day 2

### Public API uses sanitized scenario and trace views

The Day 2 API exposes only agent-visible scenario data and sanitized traces. Expected actions, failure labels, and other benchmark-private answer-key fields remain internal artifacts.

### Cache keys depend on prompt content, not prompt version alone

The OpenAI request hash includes the rendered prompt-content hash and the serializer schema version. This prevents stale cache hits when prompt text or serialization logic changes without a human-readable version bump.

### Cache-hit accounting is separated from live-call accounting

Cache lookup latency, original model latency, current request token usage, cached original usage, and billable-call status are stored separately. This avoids overcounting cost or making cache hits appear slow.

### Day 2 summary is artifact-driven

The final Day 2 rollup reads persisted benchmark, replay, and analysis artifacts instead of reconstructing results heuristically. This keeps the summary aligned with executed runs.

### Repair workflows remain out of scope

Day 2 stops at diagnosis, replay, ranking, contradiction analysis, and pairwise interaction analysis. Automated repair proposals are intentionally deferred to Day 3.
