# Repair Safety

## Purpose

Memory MRI treats repair as a verification problem, not a patch-first problem.

The system is designed to block unsupported memory edits even when an intervention appears to improve the selected action.

## Evidence gates

Before a memory repair is proposed, the backend can require evidence from:

- individual replay
- no-memory and isolation controls
- suspicion ranking
- contradiction analysis
- pairwise replay
- support-validity review

A changed action is not enough on its own.

## Approval workflow

Repairs move through explicit states:

- `PROPOSED`
- `APPROVED`
- `REJECTED`
- `APPLIED`
- `REVERTED`

Applicable memory mutations require approval before application.

## Versioning and diffs

Applicable repairs create versioned memory states and Git-style diffs so we can inspect:

- what fields changed
- whether the change matched the preview
- how to compare before and after states
- how to revert safely

## Verification rules

Verification checks:

- original failed case
- same-domain benchmark cases
- full 30-case benchmark

Supported verdicts:

- `VERIFIED_IMPROVEMENT`
- `IMPROVEMENT_WITH_REGRESSIONS`
- `NO_MEASURABLE_CHANGE`
- `FAILED_TO_REPAIR`
- `UNSUPPORTED_BEHAVIOR_CHANGE`
- `VERIFICATION_INCONCLUSIVE`
- `MEMORY_REPAIR_NOT_APPLICABLE`

## Actual Day 3 outcomes

### `cs_01`

- Replay found a behavior-changing intervention.
- The apparent fix was not support-valid.
- The reviewed proposal became a human-confirmation safeguard rather than a direct memory deletion.
- The reviewed artifact verdict is `VERIFICATION_INCONCLUSIVE`.

This is an unsafe-repair prevention result, not a verified automated repair.

### `exp_09`

- Individual replay did not show a useful memory-specific repair.
- Pairwise evidence did not justify memory mutation.
- The system classified the failure as likely memory-independent.
- The reviewed artifact verdict is `MEMORY_REPAIR_NOT_APPLICABLE`.

This is an honest prompt-or-policy escalation result, not a failed patch attempt.

## Known limitations

- Small replay batches produce wide confidence intervals.
- Some prompt-level failures can still look memory-adjacent.
- Full GPT verification is intentionally expensive and should be used selectively.
- Artifact fingerprints improve auditability but are not external tamper-proof attestations.
