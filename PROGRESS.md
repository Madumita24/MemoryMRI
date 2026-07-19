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

## 2026-07-18

- Executed the official GPT baseline across all 30 scenarios and persisted the summary plus raw traces.
- Confirmed the official GPT baseline result of `28/30` with no infrastructure errors.
- Added response caching, observable traces, and cache invalidation controls.
- Implemented individual-memory replay, suspicion ranking, contradiction analysis, and pairwise replay.
- Persisted deep-dive investigation artifacts for `cs_01` and `exp_09`.

## 2026-07-19

- Added a public FastAPI app and strict API schemas for scenarios, traces, investigations, replay, ranking, contradiction analysis, pairwise replay, and cache clearing.
- Added a unified Day 2 CLI surface for scenario runs, benchmark runs, trace inspection, investigations, replay, ranking, contradiction analysis, pairwise replay, and cache operations.
- Added API contract tests and increased the backend automated suite to `74` passing tests.
- Re-ran the deterministic regression benchmark and confirmed the mixed fake baseline remains `22/30`.
- Verified the stored GPT baseline still matches `30` persisted scenario traces and remains `28/30`.
- Ran a live Day 2H semantic verification pass for `exp_09` and generated the Day 2 summary artifacts.

## Remaining Day 2 risks

- Day 3 still needs repair proposal generation, controlled repair application, and regression-safe repair verification workflows.
- Some failures remain weakly explained by individual or pairwise ablation, especially `exp_09`.
- The frontend dashboard has not started yet.
