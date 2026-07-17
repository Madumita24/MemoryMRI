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
