# Memory MRI

Memory MRI is a backend debugger and repair-verification platform for stateful AI agents.

As of Sunday, July 19, 2026, the backend is stabilized through Day 3:

- Deterministic mixed benchmark baseline: `22/30`
- Frozen GPT-5.6 benchmark baseline: `28/30`
- Public FastAPI surface with `34` endpoints
- End-to-end investigation, proposal, approval, diff, verification, and artifact workflows
- Reviewed evidence artifacts for `cs_01` and `exp_09`

## What Memory MRI does

Memory MRI helps us answer four questions:

1. Did memory contribute to a bad agent decision?
2. Which memories look suspicious, contradictory, or interaction-dependent?
3. Is a proposed memory repair safe enough to approve?
4. Does an approved repair improve the original case without causing regressions?

## Repository layout

- `backend/` Python package, FastAPI app, CLI, prompts, and tests
- `benchmark/` reviewed scenario and memory source data
- `artifacts/` reviewed benchmark summaries, investigations, verifications, and verification artifacts
- `docs/` architecture, benchmark notes, API notes, safety notes, and decision history
- `frontend/` reserved for Day 4 work

## Quick start

```powershell
cd backend
python -m pip install -e .[dev]
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest --basetemp .pytest_tmp
```

## Benchmarks

The benchmark corpus contains 30 reviewed scenarios across three domains:

- `customer_support`
- `devops`
- `workplace_expense`

Official stored baselines:

- `artifacts/day1-mixed-baseline-summary.json`: deterministic fake-runner baseline, `22/30`
- `artifacts/gpt-baseline-summary.json`: official GPT baseline, `28/30`

The mixed deterministic benchmark is intentional. It preserves already-correct cases for regression protection while still keeping meaningful failures for replay, repair, and verification.

## Day 3 outcomes

- `cs_01`: remained an unsafe-repair-prevention case. Replay showed behavior could change, but the apparent fix was not support-valid. The reviewed artifact verdict is `VERIFICATION_INCONCLUSIVE`.
- `exp_09`: remained a memory-independent or prompt/policy-level issue. The reviewed artifact verdict is `MEMORY_REPAIR_NOT_APPLICABLE`.

Reviewed artifact fingerprints:

- `artifact_2eeca7add7ca4e0194280e37c0835b43`: `6047d5dfbbab4fe89048ee6869a6ab1687b949ec82ac30595a079f28b9476ef4`
- `artifact_d70a75d09c59496fbf98f85a039b8f8d`: `994509dae7f615aa68f95609b0454f5e13c0b036f0b97362f52bf3b41d0e49c7`

## API

Run the API locally:

```powershell
cd backend
$env:PYTHONPATH="src"
uvicorn memory_mri.api:app --reload
```

Core endpoint groups:

- health and domains
- sanitized scenarios
- trace execution and retrieval
- investigations and replay
- repair proposals and approvals
- memory diffs and verifications
- benchmark runs and verification artifacts

See `docs/API.md` for the full Day 3 surface and workflow order.

## CLI

The unified CLI lives at `memory_mri.cli.day2`. Representative commands:

```powershell
cd backend
$env:PYTHONPATH="src"
python -m memory_mri.cli.day2 run-benchmark --runner fake
python -m memory_mri.cli.day2 create-investigation --trace-id TRACE_ID
python -m memory_mri.cli.day2 generate-proposal --investigation-id INVESTIGATION_ID
python -m memory_mri.cli.day2 approve-proposal --proposal-id PROPOSAL_ID --approval-reason "Reviewed evidence"
python -m memory_mri.cli.day2 verify-full-benchmark --proposal-id PROPOSAL_ID --runner fake
python -m memory_mri.cli.day2 run-demo-workflow --summary-json-path ../artifacts/demo-runtime/day3g-demo-summary.json --summary-md-path ../artifacts/demo-runtime/day3g-demo-summary.md
```

## Privacy boundary

Model-facing input is built only from agent-visible operational data. Benchmark answer-key fields such as `expected_action`, failure categories, and known problematic memory IDs never enter LLM requests or public scenario endpoints.

## Runtime hygiene

Mutable runtime files are intentionally excluded from Git:

- `.env`
- `artifacts/memory_mri.db`
- `artifacts/openai_cache/`
- `artifacts/demo-runtime/`
- pytest and Ruff caches

That keeps reviewed evidence artifacts versioned while preventing transient local state from polluting commits.
