# Day 3F Demo Workflow

## Selected Demo Case

- Primary demo case: `cs_01`
- Primary outcome: `repair blocked as unsupported`

## cs_01 Unsafe-Repair Prevention

- Proposal ID: `proposal_bf551979f6ea4313893c45a505967b91`
- Repair type: `REQUIRE_HUMAN_CONFIRMATION`
- Verification verdict: `VERIFICATION_INCONCLUSIVE`
- Artifact ID: `artifact_2eeca7add7ca4e0194280e37c0835b43`
- Artifact fingerprint: `6047d5dfbbab4fe89048ee6869a6ab1687b949ec82ac30595a079f28b9476ef4`
- Outcome: cs_01 remains an unsafe-repair-prevention demo because the preserved workflow did not produce a support-valid verified repair.

## exp_09 Memory-Independent Workflow

- Original action: `REQUEST_DOCUMENTATION`
- Expected action: `DENY_EXPENSE`
- Proposal ID: `proposal_e70b5e3300e945c3a06cbd9bda8cf49f`
- Repair type: `ESCALATE_PROMPT_OR_POLICY_REVIEW`
- Apply blocked: `400`
- Verification verdict: `MEMORY_REPAIR_NOT_APPLICABLE`
- Artifact ID: `artifact_1c4d4d16386c4463bee27935e46eabd1`

## API Smoke Order

- `GET /traces/trace_0f0477f7cb5c497cb209414fce5e1016` -> `200`
- `GET /investigations/inv_ff4ed6ca0666440a85a758168e5ca9b4` -> `200`
- `GET /investigations/inv_ff4ed6ca0666440a85a758168e5ca9b4/results` -> `200`
- `POST /investigations/inv_ff4ed6ca0666440a85a758168e5ca9b4/proposals` -> `200`
- `POST /proposals/proposal_e70b5e3300e945c3a06cbd9bda8cf49f/approve` -> `200`
- `POST /proposals/proposal_e70b5e3300e945c3a06cbd9bda8cf49f/apply` -> `400`
- `GET /proposals/proposal_e70b5e3300e945c3a06cbd9bda8cf49f/diff` -> `200`
- `POST /verifications/original` -> `200`
- `POST /verifications/domain` -> `200`
- `POST /verifications/full` -> `200`
- `POST /artifacts` -> `200`
- `GET /artifacts/artifact_1c4d4d16386c4463bee27935e46eabd1/json` -> `200`
- `GET /artifacts/artifact_1c4d4d16386c4463bee27935e46eabd1/markdown` -> `200`