# Suspicion Ranking

- Investigation ID: `inv_6d6c10d634c140f3af029a3eb7826bde`
- Scenario: `cs_01`
- Model: `gpt-5.6`

## Ranked Memories

- `cs_01_mem_1`
  deterministic=0.318, semantic=0.990, priority=0.654, replay=replay tested: no observed influence
  semantic reason: Expired legacy policy is superseded by the current playbook but retains the highest retrieval priority.
- `cs_01_mem_3`
  deterministic=0.116, semantic=0.040, priority=0.078, replay=replay tested: no observed influence
  semantic reason: Current ledger evidence supports two settled charges for the referenced order.
- `cs_01_mem_2`
  deterministic=0.116, semantic=0.020, priority=0.068, replay=replay tested: strong observed influence
  semantic reason: Active current policy directly states the applicable refund threshold and supersedes the legacy note.
