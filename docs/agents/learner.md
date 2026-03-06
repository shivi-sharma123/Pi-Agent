# Learner Agent

The learner captures incident outcomes and turns them into reusable operational memory.

## Main Module

- `agents/learner/src/main.py`

## Core Components

- `incident_vectorizer.py`: embeds incidents into ChromaDB
- `pattern_recognizer.py`: retrieves similar incidents and runbook candidates
- `runbook_optimizer.py`: tracks runbook success and MTTR stats in PostgreSQL

## Message Interfaces

- Feedback input: `agents.learning.feedback`
- Query input: `agents.learning.query` (request-reply)
- Query response: reply inbox message containing enrichment payload

## Enrichment Output

- similar historical incidents
- recommended runbook
- historical sample size

## Purpose

- improve diagnosis quality with historical evidence
- optimize runbook choice based on prior outcomes
- preserve incident memory beyond in-process state
