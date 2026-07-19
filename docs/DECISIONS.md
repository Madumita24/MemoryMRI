# Decisions

## Day 1 foundations

### Reviewed JSON benchmark source

The benchmark lives in version-controlled JSON so scenarios, memories, and expected actions stay auditable and diffable.

### Shared schema model

All three domains use one schema and execution pipeline. Domain differences are expressed through action sets, prompts, and content rather than separate systems.

### Deterministic fake runner

The fake runner remains the fast regression authority for local development and tests.

### Mixed baseline instead of all-failing

The benchmark must contain both passes and failures in every domain so already-correct cases can detect regressions later.

### Explicit agent-input serializer

Benchmark answer-key fields are intentionally separated from model-visible operational data.

## Day 2 runner and investigation decisions

### Strict structured OpenAI responses

The GPT runner uses validated structured output so unsupported actions, bad memory citations, and malformed payloads fail safely.

### Cache keys include prompt-content hash

Human-readable prompt versions are insufficient for cache safety, so the request key also uses the rendered prompt hash and serializer schema version.

### Cache-hit accounting is separate from live-call accounting

Latency and token usage for cached responses are stored separately from billable live requests.

### Public API uses sanitized views

Public scenario and trace endpoints never expose benchmark answer-key fields.

## Day 3 repair and verification decisions

### Evidence gates come before repair

Replay, suspicion ranking, contradiction analysis, and support-validity checks are required before proposing a memory edit.

### Approval is explicit

Repairs must move through a proposal state machine instead of mutating the store directly.

### Memory changes are versioned

Applicable repairs create versioned memory snapshots so diffs, rollback, and verification all point to concrete states.

### Git-style diffs are first-class artifacts

Both machine-readable and Markdown diffs are persisted for proposal previews and applied versions.

### Verification compares against frozen baselines

Repair verification must compare against the preserved pre-repair result rather than silently rerunning and replacing it.

### Unsupported behavior changes are not counted as repairs

Producing an expected action is insufficient when the remaining evidence no longer supports that outcome.

### Non-memory failures must stay non-memory

`exp_09` demonstrated that some failures are better classified as prompt or policy issues. The system therefore supports `ESCALATE_PROMPT_OR_POLICY_REVIEW` and `NO_MEMORY_REPAIR_RECOMMENDED`.

### Verification artifacts use deterministic content fingerprints

Artifacts include a reproducible fingerprint for auditability, but the project does not claim external cryptographic attestation beyond the implemented hash.

### Reviewed evidence and runtime smoke outputs stay separate

During Day 3G stabilization, the default demo runtime path was moved to `artifacts/demo-runtime/` so resettable smoke runs no longer threaten reviewed artifact trees.
