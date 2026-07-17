# Memory MRI

Memory MRI is a debugger and verification platform for stateful AI agents.

Day 1 establishes the shared backend engine, benchmark corpus, deterministic fake runner, trace persistence, and baseline reporting pipeline.

## Repository layout

- `backend/` FastAPI-adjacent backend package and tests
- `benchmark/` reviewed benchmark source data
- `docs/` architecture, decisions, benchmark notes, and Codex log
- `frontend/` reserved for the later Next.js dashboard

## Quick start

```powershell
cd backend
python -m pip install -e .[dev]
python -m memory_mri.cli.main --database-url sqlite:///../artifacts/memory_mri.db --artifact-path ../artifacts/baseline-summary.json
pytest
```
