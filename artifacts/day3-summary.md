# Day 3 Summary

## Backend state

- Date: Sunday, July 19, 2026
- Git commit: `74a6ae2233ad8cd56eca00b10242ed4f850e4ac3`
- Automated tests: `104` passing
- API endpoints: `34`

## Baselines

- Deterministic mixed benchmark: `22/30`
- Deterministic by domain: customer support `7/10`, devops `8/10`, workplace expense `7/10`
- Frozen GPT baseline: `28/30`
- GPT by domain: customer support `9/10`, devops `10/10`, workplace expense `9/10`
- Frozen GPT failures: `cs_01`, `exp_09`

## Investigations

- `cs_01`
  - Investigation: `inv_6d6c10d634c140f3af029a3eb7826bde`
  - Classification: `individual-memory dependent`
  - Outcome: unsafe-repair prevention
- `exp_09`
  - Investigation: `inv_ff4ed6ca0666440a85a758168e5ca9b4`
  - Classification: `likely memory-independent`
  - Outcome: prompt-or-policy escalation

## Proposals

- `proposal_bf551979f6ea4313893c45a505967b91`
  - Scenario: `cs_01`
  - Repair type: `REQUIRE_HUMAN_CONFIRMATION`
  - Status: `applied`
  - Result: support-valid automated memory repair not established
- `proposal_7e2d78f3769943b1bb5a6e7281fad2ba`
  - Scenario: `exp_09`
  - Repair type: `ESCALATE_PROMPT_OR_POLICY_REVIEW`
  - Status: `proposed`
  - Result: no memory mutation recommended

Proposal outcome counts:

- applied: `1`
- rejected: `0`
- non-memory escalations: `1`

## Versions and verifications

- Versions created: `3`
- Verification runs recorded: `6`
- Verdict counts:
  - `UNSUPPORTED_BEHAVIOR_CHANGE`: `3`
  - `VERIFICATION_INCONCLUSIVE`: `2`
  - `MEMORY_REPAIR_NOT_APPLICABLE`: `1`
- Reviewed regression result: no new regressions were recorded in the reviewed artifact set

## Artifacts

- `artifact_2eeca7add7ca4e0194280e37c0835b43`
  - Scenario: `cs_01`
  - Verdict: `VERIFICATION_INCONCLUSIVE`
  - Fingerprint: `6047d5dfbbab4fe89048ee6869a6ab1687b949ec82ac30595a079f28b9476ef4`
- `artifact_d70a75d09c59496fbf98f85a039b8f8d`
  - Scenario: `exp_09`
  - Verdict: `MEMORY_REPAIR_NOT_APPLICABLE`
  - Fingerprint: `994509dae7f615aa68f95609b0454f5e13c0b036f0b97362f52bf3b41d0e49c7`

Artifact hash verification passed for both reviewed artifacts and the isolated runtime smoke artifact.

## Checks run

- `python -m ruff check .`
- `python -m ruff format --check .`
- `python -m mypy src`
- `python -m pytest --basetemp .pytest_tmp`
- deterministic benchmark regression
- frozen GPT baseline integrity verification
- `cs_01` workflow check
- `exp_09` workflow check
- API smoke test
- artifact hash verification
- demo seed/reset check

## Approximate cumulative API usage

- input tokens: `35212`
- output tokens: `4494`
- total tokens: `39706`

This approximation is based on the frozen GPT baseline plus persisted semantic-analysis artifacts and excludes cache hits and ignored runtime smoke duplicates.

## Known limitations

- Fast replay batches remain statistically small.
- Some failures are prompt-level or policy-level, not safely repairable through memory edits.
- Correct actions after ablation can still be unsupported.
- Full GPT verification remains expensive.
- Day 4 still needs a careful frontend model for public versus internal evidence views.
