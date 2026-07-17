# Architecture

## Day 1 scope

Memory MRI uses a single shared replay engine across all domains.

- `benchmark/data/*.json` contains reviewed source-of-truth benchmark cases.
- `memory_mri.schemas` defines validated Pydantic contracts for memories, scenarios, traces, repairs, and verification artifacts.
- `build_agent_input(...)` and `AgentScenario.to_agent_input(...)` create the only agent-visible scenario payload.
- `memory_mri.benchmark_loader` validates benchmark files into domain-neutral case objects.
- `memory_mri.agents.fake.FakeAgentRunner` provides deterministic local execution without API credentials.
- `memory_mri.agents.openai_runner.OpenAIAgentRunner` uses the OpenAI Responses API with strict structured output parsing.
- `memory_mri.engine.benchmark.BenchmarkService` imports source data, executes scenarios, persists traces, and writes summary artifacts.
- `memory_mri.db` stores imported benchmark copies, traces, repair proposals, benchmark runs, and verification artifacts in SQLite.

## Privacy boundary

Benchmark cases now contain two different data classes:

- Agent-visible operational data:
  scenario ID, domain, user input, allowed actions, and operational memory fields that a real agent could retrieve.
- Benchmark-private evaluation data:
  expected actions, known problematic memories, failure labels, evaluator settings, and deterministic fake-runner hints.

The agent-visible serializer returns only the operational subset. Model-facing runners must use this serializer rather than raw `model_dump()` output from benchmark models.

## GPT runner flow

1. Load environment-backed OpenAI settings.
2. Build an agent-visible payload with `build_agent_input(...)`.
3. Load a versioned domain prompt file based on domain and configured prompt version.
4. Call the OpenAI Responses API with a strict Pydantic response schema.
5. Validate the selected action and cited memory IDs against the agent-visible payload.
6. Persist the resulting development trace with latency and token-usage metadata when available.

The GPT runner never receives benchmark-private fields and never stores hidden chain-of-thought. Only the short structured rationale is kept.

## Execution flow

1. Load reviewed benchmark files from `benchmark/data`.
2. Validate source records into `BenchmarkCase` objects.
3. Split memory data into operational metadata and benchmark-private metadata.
4. Persist imported memories and scenarios.
5. Serialize only agent-visible fields for model-facing runners.
6. Run each scenario through an `AgentRunner`.
7. Deterministically evaluate the selected action against the expected action.
8. Persist traces and aggregate benchmark summaries by domain and failure category.
9. Write the baseline artifact.

## Deliberate constraints

- Deterministic evaluators decide pass or fail.
- Answer-key benchmark fields do not cross the agent-input boundary.
- Memory edits are not applied silently; proposal models exist for later approval workflows.
- Displayed metrics come from executed runs only.
- The fake runner uses benchmark-private metadata hints to simulate retrieval mistakes without claiming scientific causality.
