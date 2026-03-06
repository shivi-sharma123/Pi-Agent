# Safety Agent

The safety agent is the policy and approval gate for remediation actions.

## Main Module

- `agents/safety/src/main.py`

## Core Components

- `policy_engine.py`: allow/deny policy evaluation
- `blast_radius.py`: impact estimation from action target/type
- `rate_limiter.py`: loop prevention and cooldown limits
- `approval_gateway.py`: format payloads for human review

## Message Flow

- Input: `agents.safety.reviews`
- Output: `agents.safety.decisions`
- Escalation path: requests routed to `human.approvals`

## Decision Outcomes

- `approved`: action can execute automatically
- `rejected`: action blocked
- `pending_human_approval`: dashboard operator decision required

## Why It Exists

It prevents uncontrolled automation by combining risk policy, blast radius checks, and rate limiting before any action touches infrastructure.
