# Incident Lifecycle and Workflow

Incident state progression is managed by `IncidentFSM` in `agents/orchestrator/src/incident_fsm.py`.

## FSM States

- `detecting`
- `diagnosing`
- `proposing_remediation`
- `safety_review`
- `executing`
- `verifying`
- `resolved`
- `closed`

## Allowed Transitions

- `detecting -> diagnosing`
- `diagnosing -> proposing_remediation`
- `proposing_remediation -> safety_review`
- `safety_review -> executing`
- `safety_review -> proposing_remediation` (rejection loop)
- `executing -> verifying`
- `executing -> proposing_remediation` (execution failure loop)
- `verifying -> resolved`
- `verifying -> executing` (verification failure loop)
- `resolved -> closed`

## Timeouts and Retries

Per-state timeout defaults:

- `detecting`: 120s
- `diagnosing`: 180s
- `proposing_remediation`: 120s
- `safety_review`: 300s
- `executing`: 180s
- `verifying`: 120s

Retry policy:

- Max retries per state: `2`
- On timeout with retries available: emit `state_retry` lifecycle event
- On retries exhausted: escalate to `human.approvals`

## Control-Plane Message Flow

1. Observer emits anomaly to `agents.observer.anomalies`.
2. Orchestrator creates incident and routes diagnosis request.
3. Diagnoser publishes RCA result to `agents.diagnoser.results`.
4. Remediator proposes action for safety review.
5. Safety returns decision (`approved`, `rejected`, or `pending_human_approval`).
6. If approved, remediator executes and emits execution result.
7. Orchestrator marks incident `resolved` or loops for retry/escalation.

## Human Approval Path

- Safety publishes approval requests to `human.approvals`.
- Dashboard operators approve/reject via API.
- Dashboard publishes responses to `human.approvals.responses`.
- Orchestrator consumes responses and transitions the FSM.

## Timeline and Postmortem

Orchestrator appends timeline events on key transitions using `timeline_builder.add_event()`.
After successful resolution it generates a structured postmortem payload via `generate_postmortem()` and persists it on the incident row.
