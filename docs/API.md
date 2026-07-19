# API

## Overview

The FastAPI backend currently exposes `34` endpoints.

Public scenario endpoints are sanitized. They do not expose:

- `expected_action`
- `expected_problematic_memory_ids`
- `failure_category`
- benchmark answer-key labels
- fake-runner-only hints

## Endpoint groups

### Health and catalog

- `GET /health`
- `GET /domains`
- `GET /scenarios`
- `GET /scenarios/{scenario_id}`

### Runs and traces

- `POST /runs`
- `GET /traces/{trace_id}`
- `GET /scenarios/{scenario_id}/traces`

### Investigations

- `POST /investigations`
- `GET /investigations/{investigation_id}`
- `GET /investigations/{investigation_id}/results`

### Replay and analysis

- `POST /investigations/{investigation_id}/individual-replay`
- `POST /investigations/{investigation_id}/replay`
- `POST /investigations/{investigation_id}/suspicion-ranking`
- `POST /investigations/{investigation_id}/contradictions`
- `POST /investigations/{investigation_id}/pairwise-replay`
- `POST /investigations/{investigation_id}/interactions`

### Proposals and memory changes

- `POST /investigations/{investigation_id}/proposals`
- `GET /proposals/{proposal_id}`
- `POST /proposals/{proposal_id}/approve`
- `POST /proposals/{proposal_id}/reject`
- `POST /proposals/{proposal_id}/apply`
- `POST /proposals/{proposal_id}/revert`
- `GET /proposals/{proposal_id}/diff`

### Verification

- `POST /verifications/original`
- `POST /verifications/domain`
- `POST /verifications/full`
- `GET /verifications/{verification_id}`

### Benchmarks and cache

- `POST /benchmarks/run`
- `GET /benchmarks/{run_id}`
- `POST /cache/clear`

### Verification artifacts

- `POST /artifacts`
- `GET /artifacts/{artifact_id}`
- `GET /artifacts/{artifact_id}/json`
- `GET /artifacts/{artifact_id}/markdown`

## Workflow order

Typical Day 3 workflow:

1. `POST /runs`
2. `POST /investigations`
3. replay and analysis endpoints
4. `POST /investigations/{investigation_id}/proposals`
5. `POST /proposals/{proposal_id}/approve` or reject
6. `POST /proposals/{proposal_id}/apply` when applicable
7. `GET /proposals/{proposal_id}/diff`
8. verification endpoints
9. `POST /artifacts`
10. artifact retrieval endpoints

## Error behavior

The API returns structured errors for important invalid states, including:

- proposal not approved
- invalid transition
- stale snapshot
- missing investigation
- missing memory
- invalid repair
- verification not applicable
- artifact not ready
- hash mismatch
- model failure
- infrastructure error

One intentional Day 3 example:

- applying `ESCALATE_PROMPT_OR_POLICY_REVIEW` returns HTTP `400` with code `non_applicable_repair_type`

## Notes

- The API surface is suitable for the hackathon MVP backend.
- Code-level privacy separation exists, but the project does not yet claim production-grade authorization controls.
