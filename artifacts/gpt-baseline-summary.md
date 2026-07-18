# GPT Baseline Summary

- Model: `gpt-5.6`
- Prompt version: `v1`
- Timestamp: `2026-07-18T05:42:23.462472Z`
- Git commit: `8cc4d1f406870e33a3e3822db4d4f96ae2eac234`
- Cache enabled: `False`
- Attempted scenarios: `30`
- Evaluated scenarios: `30`
- Passed: `28`
- Failed: `2`
- Infrastructure errors: `0`

## By Domain

- `customer_support`: attempted=10 evaluated=10 passed=9 failed=1 infra_errors=0
- `devops`: attempted=10 evaluated=10 passed=10 failed=0 infra_errors=0
- `workplace_expense`: attempted=10 evaluated=10 passed=9 failed=1 infra_errors=0

## By Failure Category

- `contradictory-memories`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `hallucinated-preference`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `incorrect-retrieval-priority`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `missing-expiration`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `newer-correct-memory-ignored`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `obsolete-policy`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `stale-memory`: attempted=3 evaluated=3 passed=2 failed=1 infra_errors=0
- `two-memory-interaction`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0
- `wrong-context-valid-memory`: attempted=3 evaluated=3 passed=2 failed=1 infra_errors=0
- `wrong-user-memory`: attempted=3 evaluated=3 passed=3 failed=0 infra_errors=0

## Failed Scenarios

- `cs_01`: expected `ISSUE_REFUND`, actual `ASK_FOR_INFORMATION`, cache `False`
- `exp_09`: expected `DENY_EXPENSE`, actual `REQUEST_DOCUMENTATION`, cache `False`

## Infrastructure Errors

- None

## Deep Dive Candidates

- `contradictory-memories`: no failure in this category
- `two-memory-interaction`: no failure in this category
- `wrong-context-valid-memory`: `exp_09` (`DENY_EXPENSE` -> `REQUEST_DOCUMENTATION`)
