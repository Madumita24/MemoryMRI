# Progress

## 2026-07-17

- Initialized the monorepo structure for the Memory MRI Day 1 milestone.
- Added the shared backend schemas, benchmark loader, deterministic fake runner, SQLite persistence, CLI runner, and statistical utilities.
- Authored 30 benchmark scenarios across customer support, DevOps, and workplace expense approval.
- Added pytest coverage for schema validation, loading, evaluation, aggregation, persistence, fake execution, invalid actions, and Wilson intervals.
- Corrected the Day 1.5 benchmark so the deterministic baseline now mixes passes and failures in every domain.
- Preserved the original all-failing artifact as `artifacts/day1-initial-baseline-summary.json`.
- Added benchmark-quality tests that reject 0 percent and 100 percent baselines.
- Added an explicit agent-input serialization layer that keeps benchmark answer-key fields and fake-runner hints out of model-facing payloads.
- Split memory metadata into agent-visible operational metadata and benchmark-private metadata.
- Implemented the GPT-backed OpenAI runner with versioned prompts, strict structured output validation, mocked retry and error-path tests, and a one-scenario smoke-test CLI.
- Completed live GPT-5.6 smoke tests for one scenario in each domain and saved development trace artifacts under `artifacts/openai-smoke-*.json`.

## Remaining Day 2 risks

- Repair proposal generation, replay interventions, pairwise interaction analysis, and verification artifacts are modeled but not yet orchestrated.
- The frontend dashboard has not started yet.
- The full 30-scenario GPT benchmark has not been executed yet; only the three-scenario Day 2B smoke test is complete.
