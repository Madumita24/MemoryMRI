# Benchmark

## Corpus shape

The reviewed benchmark contains 30 scenarios:

- 10 `customer_support`
- 10 `devops`
- 10 `workplace_expense`

Every scenario preserves:

- a stable scenario ID
- stable memory IDs
- at least three memories
- a valid expected action
- a documented expected outcome
- valid domain actions

## Mixed benchmark rationale

The benchmark is intentionally mixed rather than all-failing.

It includes:

- clearly correct-memory cases that should pass
- stale-memory cases that should fail
- contradictory-memory cases
- suspicious-memory cases that should be ignored
- wrong-entity cases
- pairwise interaction failures
- difficult cases that remain hard after simple intervention

This matters for regression analysis because an all-failing suite can make broad behavior changes look like improvement. The mixed suite preserves already-correct cases so repairs can be judged for both benefit and collateral damage.

## Privacy boundary

Benchmark source files combine operational data and benchmark-private evaluation data.

Agent-visible data:

- scenario ID
- domain
- user input
- allowed actions
- operational memory fields

Benchmark-private data:

- `expected_action`
- `expected_problematic_memory_ids`
- `failure_category`
- expected explanation
- evaluator configuration
- fake-runner-only hints

Only the explicit serializer may feed an LLM request.

## Deterministic baseline

Stored artifact:

- `artifacts/day1-mixed-baseline-summary.json`

Current result:

- overall: `22/30`
- customer support: `7/10`
- devops: `8/10`
- workplace expense: `7/10`

The deterministic baseline still contains both passes and failures in every domain.

## Frozen GPT baseline

Stored artifacts:

- `artifacts/gpt-baseline-summary.json`
- `artifacts/gpt-baseline-summary.md`
- `artifacts/gpt-baseline-traces/`

Official run facts:

- date: Saturday, July 18, 2026
- model: `gpt-5.6`
- prompt versions: `v1` for all three domains
- result: `28/30`
- infrastructure errors: `0`

By domain:

- customer support: `9/10`
- devops: `10/10`
- workplace expense: `9/10`

Failed scenarios:

- `cs_01`
- `exp_09`

Integrity was re-verified on Sunday, July 19, 2026:

- 30 stored trace files exist
- the frozen summary still reports the same two failures
- no benchmark fields or prompts were altered during verification

## Failure categories

The benchmark covers:

- `stale-memory`
- `contradictory-memories`
- `wrong-user-memory`
- `hallucinated-preference`
- `obsolete-policy`
- `missing-expiration`
- `incorrect-retrieval-priority`
- `two-memory-interaction`
- `wrong-context-valid-memory`
- `newer-correct-memory-ignored`

## Day 3 benchmark use

Day 3 repair work does not overwrite the frozen GPT baseline.

Instead, verification compares repair outcomes against:

- the frozen official baseline trace when available
- the deterministic mixed baseline for fast regression checks
- versioned verification outputs persisted under `artifacts/verifications/`

## Statistical limitations

- Fast replay uses only three runs.
- Some failures remain insensitive to individual or pairwise memory changes.
- A correct action after ablation may still be unsupported by the remaining evidence.
- A prompt or policy problem can masquerade as a memory problem, as seen in `exp_09`.
