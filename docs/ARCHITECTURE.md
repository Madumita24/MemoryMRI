# Architecture

## Day 1 scope

Memory MRI uses a single shared replay engine across all domains.

- `benchmark/data/*.json` contains reviewed source-of-truth benchmark cases.
- `memory_mri.schemas` defines validated Pydantic contracts for memories, scenarios, traces, repairs, and verification artifacts.
- `memory_mri.benchmark_loader` validates benchmark files into domain-neutral case objects.
- `memory_mri.agents.fake.FakeAgentRunner` provides deterministic local execution without API credentials.
- `memory_mri.engine.benchmark.BenchmarkService` imports source data, executes scenarios, persists traces, and writes summary artifacts.
- `memory_mri.db` stores imported benchmark copies, traces, repair proposals, benchmark runs, and verification artifacts in SQLite.

## Execution flow

1. Load reviewed benchmark files from `benchmark/data`.
2. Validate source records into `BenchmarkCase` objects.
3. Persist imported memories and scenarios.
4. Run each scenario through an `AgentRunner`.
5. Deterministically evaluate the selected action against the expected action.
6. Persist traces and aggregate benchmark summaries by domain and failure category.
7. Write the baseline artifact to `artifacts/baseline-summary.json`.

## Deliberate constraints

- Deterministic evaluators decide pass or fail.
- Memory edits are not applied silently; proposal models exist for later approval workflows.
- Displayed metrics come from executed runs only.
- The fake runner uses memory metadata hints to simulate retrieval mistakes without claiming scientific causality.
