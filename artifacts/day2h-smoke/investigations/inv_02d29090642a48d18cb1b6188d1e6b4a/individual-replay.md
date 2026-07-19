# Individual Memory Replay

- Investigation ID: `inv_02d29090642a48d18cb1b6188d1e6b4a`
- Parent trace: `trace_a80d51a03c734f078e4b78fef084615b`
- Scenario: `cs_02`
- Expected action: `REQUEST_MANAGER_APPROVAL`
- Original action: `ISSUE_REFUND`
- Replay mode: `fast`
- Run count: `3`
- Cache policy: cache disabled during replay to measure repeated live executions

## Results

- `REMOVE_MEMORY` on `cs_02_mem_1`: before={'ISSUE_REFUND': 3} after={'REQUEST_MANAGER_APPROVAL': 3} delta=1.000
