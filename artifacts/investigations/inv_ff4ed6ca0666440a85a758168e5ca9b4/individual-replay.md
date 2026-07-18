# Individual Memory Replay

- Investigation ID: `inv_ff4ed6ca0666440a85a758168e5ca9b4`
- Parent trace: `trace_0f0477f7cb5c497cb209414fce5e1016`
- Scenario: `exp_09`
- Expected action: `DENY_EXPENSE`
- Original action: `REQUEST_DOCUMENTATION`
- Replay mode: `fast`
- Run count: `3`
- Cache policy: cache disabled during replay to measure repeated live executions

## Results

- `REMOVE_MEMORY` on `exp_09_mem_1`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
- `DISABLE_MEMORY` on `exp_09_mem_1`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
- `REMOVE_MEMORY` on `exp_09_mem_2`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
- `DISABLE_MEMORY` on `exp_09_mem_2`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
- `REMOVE_MEMORY` on `exp_09_mem_3`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
- `DISABLE_MEMORY` on `exp_09_mem_3`: before={'REQUEST_DOCUMENTATION': 3} after={'REQUEST_DOCUMENTATION': 3} delta=0.000
