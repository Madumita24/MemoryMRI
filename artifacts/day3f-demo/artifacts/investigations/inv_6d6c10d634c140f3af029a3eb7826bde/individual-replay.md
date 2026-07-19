# Individual Memory Replay

- Investigation ID: `inv_6d6c10d634c140f3af029a3eb7826bde`
- Parent trace: `trace_6e225da6d76a4ae0b76ec0ee5c11fc5c`
- Scenario: `cs_01`
- Expected action: `ISSUE_REFUND`
- Original action: `ASK_FOR_INFORMATION`
- Replay mode: `fast`
- Run count: `3`
- Cache policy: cache disabled during replay to measure repeated live executions

## Results

- `REMOVE_MEMORY` on `cs_01_mem_1`: before={'ASK_FOR_INFORMATION': 3} after={'ASK_FOR_INFORMATION': 3} delta=0.000
- `DISABLE_MEMORY` on `cs_01_mem_1`: before={'ASK_FOR_INFORMATION': 3} after={'ASK_FOR_INFORMATION': 3} delta=0.000
- `REMOVE_MEMORY` on `cs_01_mem_2`: before={'ASK_FOR_INFORMATION': 3} after={'ISSUE_REFUND': 3} delta=1.000
- `DISABLE_MEMORY` on `cs_01_mem_2`: before={'ASK_FOR_INFORMATION': 3} after={'REQUEST_MANAGER_APPROVAL': 3} delta=0.000
- `REMOVE_MEMORY` on `cs_01_mem_3`: before={'ASK_FOR_INFORMATION': 3} after={'ASK_FOR_INFORMATION': 3} delta=0.000
- `DISABLE_MEMORY` on `cs_01_mem_3`: before={'ASK_FOR_INFORMATION': 3} after={'ASK_FOR_INFORMATION': 3} delta=0.000
