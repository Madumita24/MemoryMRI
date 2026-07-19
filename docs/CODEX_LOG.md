# Codex Log

## 2026-07-17

- Built the initial backend foundation for schemas, loading, deterministic execution, persistence, reporting, and tests.
- Revised the benchmark and fake-runner heuristics to create a mixed baseline with passes and failures in every domain.
- Preserved the original all-failing artifact and generated the corrected mixed baseline.
- Added the explicit agent-visible serialization boundary so benchmark answer-key fields never reach model prompts.
- Implemented the GPT runner, domain prompts, strict structured validation, and smoke-test commands.
- Ran the first live GPT smoke scenarios and saved development traces.

## 2026-07-18

- Executed the official 30-case GPT baseline and persisted summary plus raw traces.
- Confirmed the official frozen baseline score of `28/30` with failures limited to `cs_01` and `exp_09`.
- Added request caching, observable traces, individual replay, suspicion ranking, contradiction analysis, and pairwise replay.
- Persisted investigation artifacts for the primary failure cases.

## 2026-07-19

- Added the public FastAPI surface and expanded the CLI to cover runs, investigations, replay, proposals, diffs, verifications, artifacts, and demo utilities.
- Added evidence-gated repair proposals, approval workflow, memory versioning, Git-style diffs, verification runs, and verification artifacts.
- Added end-to-end demo seeding and reset tooling for the reviewed Day 3 workflows.
- Increased the backend automated suite to `104` passing tests.
- Re-ran the deterministic regression benchmark and confirmed `22/30`.
- Re-verified the frozen GPT baseline integrity: `30` stored traces, `28/30`, same two failures.
- Re-ran the Day 3 demo workflow in an isolated runtime sandbox and confirmed:
  - `cs_01` remains an unsafe-repair prevention case
  - `exp_09` remains a memory-independent escalation case
- Verified reviewed artifact fingerprints for:
  - `artifact_2eeca7add7ca4e0194280e37c0835b43`
  - `artifact_d70a75d09c59496fbf98f85a039b8f8d`
  - runtime smoke artifact `artifact_381599f75d584d5eb356813a51884b0e`
- Fixed a stabilization issue where the default demo runtime path overlapped reviewed evidence and could delete tracked demo artifacts during reset.
