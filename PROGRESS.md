# Progress

## 2026-07-17

- Built the backend foundation for schemas, loading, deterministic execution, persistence, reporting, and tests.
- Authored the 30 reviewed benchmark scenarios across customer support, DevOps, and workplace expense.
- Corrected the benchmark into a mixed deterministic suite and preserved the original all-failing baseline artifact separately.
- Added the explicit agent-input serializer and benchmark-private metadata split.
- Implemented the GPT-5.6 runner, versioned prompts, strict response validation, and smoke-test commands.

## 2026-07-18

- Executed the official 30-case GPT baseline and persisted raw traces and summary artifacts.
- Confirmed the official GPT result of `28/30` with no infrastructure errors.
- Added caching, observable traces, individual replay, suspicion ranking, contradiction analysis, and pairwise replay.
- Persisted deep-dive investigation artifacts for `cs_01` and `exp_09`.

## 2026-07-19

- Added FastAPI coverage for runs, traces, investigations, replay, proposals, approvals, diffs, verifications, benchmarks, artifacts, and cache clearing.
- Added repair proposals, approval workflow, memory versioning, Git-style diffs, verification runs, and verification artifacts.
- Added reproducible demo seed/reset tooling and a Day 3 end-to-end workflow.
- Stabilized the backend and documentation for Day 4 handoff.
- Increased the automated backend suite to `104` passing tests.
- Re-ran the deterministic regression benchmark and confirmed `22/30`.
- Re-verified the frozen GPT baseline and confirmed `28/30` with the same two failures.
- Re-ran the Day 3 demo workflow in isolated runtime state and confirmed:
  - `cs_01` remains an unsafe-repair prevention case
  - `exp_09` remains a memory-independent escalation case
- Fixed the default demo runtime path so smoke runs no longer target the reviewed `artifacts/day3f-demo/` tree.

## Current backend status

- API endpoints: `34`
- Automated tests: `104` passing
- Deterministic benchmark: `22/30`
- Frozen GPT benchmark: `28/30`
- Reviewed artifact IDs:
  - `artifact_2eeca7add7ca4e0194280e37c0835b43`
  - `artifact_d70a75d09c59496fbf98f85a039b8f8d`

## Remaining Day 4 frontend risks

- The frontend still needs a clear workflow for displaying privacy-safe scenario data versus internal investigation evidence.
- Large replay and trace artifacts will need pagination or summary views.
- Verification verdicts and support-validity results need careful UX so unsafe-repair prevention does not look like failure.
- Runtime smoke outputs must remain isolated from reviewed evidence artifacts in the frontend developer workflow.
