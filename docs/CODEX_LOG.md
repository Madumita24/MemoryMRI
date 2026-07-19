# Codex Log

## 2026-07-17

- Read the Day 1 milestone instructions from the attached build plan.
- Confirmed the repository was empty.
- Built the initial monorepo and backend foundation for schemas, data loading, execution, persistence, reporting, and tests.
- Revised the benchmark metadata and fake-runner heuristics to create a mixed baseline with both passes and failures in every domain.
- Preserved the original baseline artifact and generated a corrected mixed-baseline artifact from a fresh execution.
- Added an explicit privacy boundary so agent-visible payloads exclude benchmark answer-key fields and deterministic fake-runner hints.
- Implemented the OpenAI GPT runner, versioned domain prompts, strict structured output validation, mocked failure-path coverage, and a one-scenario smoke-test command.
- Debugged live Responses API compatibility issues around `text.verbosity`, strict JSON schema transport, and unsupported `temperature` for `gpt-5.6`.
- Ran live GPT-5.6 smoke scenarios `cs_01`, `dev_01`, and `exp_01`, and persisted the resulting traces as development artifacts.

## 2026-07-18

- Executed the official 30-case GPT baseline and persisted `artifacts/gpt-baseline-summary.json`, `artifacts/gpt-baseline-summary.md`, and per-scenario trace artifacts.
- Confirmed the stored baseline score of `28/30` with failures limited to `cs_01` and `exp_09`.
- Implemented replay caching, observable traces, individual-memory replay, suspicion ranking, contradiction analysis, and pairwise replay artifacts.
- Ran live pairwise and memory-control investigations for `exp_09` and `cs_01`.

## 2026-07-19

- Added a public FastAPI surface for health, scenarios, traces, investigations, replay, ranking, contradictions, pairwise analysis, and cache clearing.
- Added a unified Day 2 CLI wrapper for scenario execution, benchmark execution, trace inspection, investigations, replay, ranking, contradiction analysis, pairwise replay, and cache operations.
- Added API contract tests for privacy, trace retrieval, investigation orchestration, and cache clearing.
- Re-ran the deterministic regression benchmark and confirmed `22/30`.
- Verified the stored GPT baseline still matches 30 persisted baseline traces.
- Ran a live semantic suspicion-ranking and contradiction-analysis check for `inv_ff4ed6ca0666440a85a758168e5ca9b4`.
- Generated `artifacts/day2-summary.json` and `artifacts/day2-summary.md`.
