# Suspicion Ranking

- Investigation ID: `inv_ff4ed6ca0666440a85a758168e5ca9b4`
- Scenario: `exp_09`
- Model: `gpt-5.6`

## Ranked Memories

- `exp_09_mem_1`
  deterministic=0.155, semantic=0.940, priority=0.548, replay=replay tested: no observed influence
  semantic reason: Temporary relocation stipend eligibility does not establish per-diem eligibility for customer travel, yet has highest retrieval priority.
- `exp_09_mem_2`
  deterministic=0.116, semantic=0.030, priority=0.073, replay=replay tested: no observed influence
  semantic reason: Current meal policy directly addresses documented per-diem requirements for solo dinners during customer travel.
- `exp_09_mem_3`
  deterministic=0.116, semantic=0.020, priority=0.068, replay=replay tested: no observed influence
  semantic reason: Current receipt evidence directly supports that the dinner was employee-only.

## Investigation Note

- All individual replay influence values remain `0.0`.
- Suspicion analysis does not override the replay result.
- Pairwise or whole-snapshot testing may still be needed.
- Prompt or policy interpretation remains a possible cause.
