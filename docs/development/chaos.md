# Chaos Engineering Guide

Chaos tools live under `scripts/chaos/` and are used to validate MTTD and MTTR behavior.

## Components

- `injector.py`: primitives for failure injection
- `runner.py`: scenario orchestration and report generation
- `scoring.py`: MTTD/MTTR scoring
- `scenarios/*.py`: scenario definitions

## Available Scenarios

- `memory_leak`
- `cpu_spike`
- `network_partition`
- `db_overload`

## Run Commands

Dry run:

```bash
python scripts/chaos/runner.py --dry-run
```

Single scenario:

```bash
python scripts/chaos/runner.py --scenario memory_leak
```

All scenarios:

```bash
python scripts/chaos/runner.py
```

Custom cooldown:

```bash
python scripts/chaos/runner.py --cooldown 30
```

## Output

The runner writes a Markdown report to:

- `scripts/chaos/report_<timestamp>.md`

The report contains:

- scenario outcome
- MTTD and MTTR values
- score grade per scenario

## Recommended Procedure

1. Start full stack (`make up`).
2. Confirm health (`make health`).
3. Run chaos scenario(s).
4. Review dashboard timelines and generated report.
5. Capture findings in postmortem or runbook updates.
