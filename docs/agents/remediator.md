# Remediator Agent

The remediator converts diagnosis output into executable actions.

## Main Module

- `agents/remediator/src/main.py`

## Core Components

- `runbook_engine.py`: match diagnosis to runbook YAML
- `action_executor.py`: execute selected action
- `verification_engine.py`: post-action verification checks
- `rollback_manager.py`: rollback on failed verification

## Runbooks

Runbooks live under `agents/remediator/runbooks/`.
Current examples:

- `memory_leak.yml`
- `network_partition.yml`
- `database_overload.yml`

## Message Flow

- Input: `agents.diagnoser.results`
- Proposal output: `agents.safety.reviews`
- Decision input: `agents.safety.decisions`
- Execution output: `agents.remediator.executions`

## Behavior Summary

1. Receive diagnosis.
2. Find first matching runbook by category and confidence threshold.
3. Render action parameters from diagnosis context.
4. Request safety review.
5. Execute if approved.
6. Verify result and rollback if needed.
7. Notify orchestrator with execution status.
