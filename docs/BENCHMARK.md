# Benchmark

## Dataset shape

The Day 1 benchmark corpus contains 30 scenarios:

- 10 customer support scenarios
- 10 DevOps deployment scenarios
- 10 workplace expense approval scenarios

Each scenario includes:

- at least three memories
- a deterministic expected action
- at least one intentionally problematic memory
- a documented failure category
- a natural-language explanation of the expected action

## Privacy boundary

Benchmark source files contain both operational data and private evaluation data.

- Agent-visible operational data includes user input, allowed actions, and realistic memory fields such as content, dates, status, confidence, superseding relationships, and operational metadata.
- Benchmark-private data includes `expected_action`, `expected_problematic_memory_ids`, `failure_category`, `explanation`, `evaluator_config`, and memory-level deterministic hints kept in `benchmark_metadata`.

Only the explicit agent-input serializer may be used to prepare model-facing payloads.

## GPT smoke testing

Day 2B introduced a GPT-backed smoke-test runner for exactly one selected scenario at a time. These runs:

- use the same safe agent-visible serialization boundary
- use versioned domain prompts
- persist development traces
- are not treated as the final benchmark baseline

The deterministic 22/30 fake baseline remains the regression reference for non-LLM regression checks.

## Official Day 2 GPT baseline

The official GPT baseline was executed on Saturday, July 18, 2026 and persisted in `artifacts/gpt-baseline-summary.json`.

- Model: `gpt-5.6`
- Prompt versions: `v1` for `customer_support`, `devops`, and `workplace_expense`
- Result: `28/30`
- Infrastructure errors: `0`

By domain:

- customer support: `9/10`
- devops: `10/10`
- workplace expense: `9/10`

Observed failed scenarios:

- `cs_01` in `stale-memory`
- `exp_09` in `wrong-context-valid-memory`

The corrected Day 1.5 benchmark is intentionally mixed rather than all-failing. A realistic regression benchmark needs:

- already-correct cases so later repairs can prove they did not break working behavior
- believable failure cases so replay and repair logic still has meaningful targets
- suspicious-memory cases that should be ignored, which exercises retrieval quality rather than only action selection
- multiple failure categories among failed cases so a single repair strategy cannot trivially optimize the whole suite

An all-failing baseline weakens regression analysis because any broad behavior change can look like improvement. The mixed suite makes it possible to detect both helpful repairs and unintended regressions.

## Covered failure categories

- stale memory
- contradictory memories
- wrong-user memory
- hallucinated preference
- obsolete policy
- missing expiration
- incorrect retrieval priority
- two-memory interaction
- wrong-context valid memory
- newer-correct-memory-ignored

## Fake runner behavior

The fake runner remains deterministic, but it no longer blindly follows the first biased memory. Instead it scores candidate action-supporting memories from reviewed attributes, including:

- retrieval priority
- memory status
- confidence
- validity range
- superseded or stale state
- memory role, such as policy, evidence, inference, or customer-status note
- entity match metadata
- explicit ignore hints for suspicious memories that should not drive the decision
- pairwise interaction boosts for grouped problematic memories

This produces a stable mixed baseline with both passes and failures in every domain while keeping the behavior grounded in memory attributes rather than scenario IDs.

The operational serializer never exposes the benchmark-only ignore hints, interaction labels, answer key, or failure labels to GPT-facing runners.

## Replay methodology

Individual replay uses the formula:

`influence_delta = intervention_success_rate - original_success_rate`

Wilson score intervals are computed for intervention success rates to make the uncertainty of small replay batches explicit.

Pairwise replay adds:

- `combined_influence`
- `interaction_score = combined_influence - max(individual influences)`
- `interaction_synergy`

These values are descriptive rather than causal. A changed action does not, by itself, prove a memory is semantically wrong.

## Suspicion ranking and contradiction analysis

Suspicion ranking combines:

- deterministic metadata signals
- semantic suspicion scoring
- replay evidence, when available

Contradiction analysis compares:

- deterministic pair relationships from metadata
- semantic pair relationships inferred from the live model

These outputs help prioritize hypotheses, but they do not replace replay evidence.

## Statistical limitations

- Fast replay mode uses only three runs, so intervals remain wide.
- Some failures, such as `exp_09`, can remain insensitive to individual or pairwise memory interventions.
- Correct outcomes after ablation may still be unsupported by the remaining snapshot.
- Pairwise effects remain sensitive to prompt interpretation and model behavior.
