# Suspicion Ranking

- Investigation ID: `inv_ff4ed6ca0666440a85a758168e5ca9b4`
- Scenario: `exp_09`
- Model: `gpt-5.6`

## Ranked Memories

- `exp_09_mem_1`
  deterministic=0.155, semantic=0.970, priority=0.563, replay=replay tested: no observed influence
  semantic reason: Temporary relocation stipend eligibility does not establish per-diem eligibility for customer travel, yet it has the highest retrieval priority.
- `exp_09_mem_2`
  deterministic=0.116, semantic=0.030, priority=0.073, replay=replay tested: no observed influence
  semantic reason: Current meal policy directly addresses solo dinners during customer travel and documentation requirements.
- `exp_09_mem_3`
  deterministic=0.116, semantic=0.020, priority=0.068, replay=replay tested: no observed influence
  semantic reason: Receipt evidence is current, entity-matched, and directly relevant to the expense request.

## Investigation Note

- All individual replay influence values remain `0.0`.
- Suspicion analysis does not override the replay result.
- Pairwise or whole-snapshot testing may still be needed.
- Prompt or policy interpretation remains a possible cause.
