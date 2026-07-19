# Memory MRI

Memory MRI is a debugger and verification platform for stateful AI agents.

As of Sunday, July 19, 2026, Day 2 is complete:

- deterministic mixed benchmark baseline: `22/30`
- GPT-5.6 baseline: `28/30`
- live deep-dive artifacts for individual replay, suspicion ranking, contradiction analysis, and pairwise replay
- public FastAPI and CLI access for benchmark, trace, cache, and investigation workflows

## Repository layout

- `backend/` backend package, FastAPI app, CLI tools, and tests
- `benchmark/` reviewed benchmark source data
- `docs/` architecture, decisions, benchmark notes, and Codex log
- `frontend/` reserved for the later Next.js dashboard

## Quick start

```powershell
cd backend
python -m pip install -e .[dev]
python -m memory_mri.cli.day2 run-benchmark --runner fake
pytest
```

## API

Run the public API locally:

```powershell
cd backend
uvicorn memory_mri.api:app --reload
```

Key endpoints:

- `GET /health`
- `GET /domains`
- `GET /scenarios`
- `GET /scenarios/{scenario_id}`
- `POST /runs`
- `GET /traces/{trace_id}`
- `POST /investigations`
- `POST /investigations/{investigation_id}/individual-replay`
- `POST /investigations/{investigation_id}/suspicion-ranking`
- `POST /investigations/{investigation_id}/contradictions`
- `POST /investigations/{investigation_id}/pairwise-replay`

Public scenario endpoints expose only agent-visible operational data. Benchmark answer-key fields such as `expected_action`, failure labels, and known problematic memory IDs remain private.

## CLI

Unified Day 2 CLI:

```powershell
cd backend
python -m memory_mri.cli.day2 run-scenario --scenario-id cs_01 --runner fake
python -m memory_mri.cli.day2 inspect-trace --trace-id TRACE_ID
python -m memory_mri.cli.day2 create-investigation --trace-id TRACE_ID
python -m memory_mri.cli.day2 individual-replay --investigation-id INVESTIGATION_ID --operation all
python -m memory_mri.cli.day2 rank-suspicion --investigation-id INVESTIGATION_ID
python -m memory_mri.cli.day2 detect-contradictions --investigation-id INVESTIGATION_ID
python -m memory_mri.cli.day2 pairwise-replay --investigation-id INVESTIGATION_ID --all-pairs
python -m memory_mri.cli.day2 clear-cache --mode all
```

## Day 2 checkpoints

- `artifacts/gpt-baseline-summary.json` stores the official 30-case GPT baseline.
- `artifacts/day2-summary.json` stores the Day 2 rollup.
- `artifacts/investigations/` contains replay, suspicion, contradiction, and pairwise artifacts.
- `artifacts/gpt-baseline-traces/` contains one persisted trace per official GPT scenario run.
