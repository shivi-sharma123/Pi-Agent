# Orchestrator Agent

The orchestrator is the control-plane coordinator for incident lifecycle management.

## Main Module

- `agents/orchestrator/src/orchestrator_agent.py`

## Key Components

- `incident_fsm.py`: valid states, transitions, timeouts, retries
- `agent_router.py`: heartbeat-backed routing and liveness checks
- `escalation_manager.py`: timeout retries and human escalation
- `timeline_builder.py`: timeline events and postmortem generation

## Subscribed Subjects

- `agents.observer.anomalies`
- `agents.diagnoser.results`
- `agents.safety.decisions`
- `agents.remediator.executions`
- `agents.heartbeat`
- `human.approvals.responses`

## Published Subjects

- `agents.diagnoser.requests`
- `agents.safety.reviews`
- `incidents.lifecycle`
- `human.approvals` (via escalation manager)

## Responsibilities

- create and update incident records
- enforce FSM transitions
- drive agent handoffs by subject routing
- handle retries, timeouts, and escalations
- maintain timeline/postmortem data for dashboard consumers
