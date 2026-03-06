#!/usr/bin/env python3
"""
Chaos Runner
=============
Orchestrates chaos scenarios end-to-end:
  1. Runs a scenario (injects the failure)
  2. Waits for the SRE agent swarm to detect and remediate
  3. Records MTTD (time-to-detect) and MTTR (time-to-remediate) from the DB
  4. Cleans up after each scenario
  5. Generates a Markdown performance report

Usage::
    python scripts/chaos/runner.py                    # run all scenarios
    python scripts/chaos/runner.py --scenario memory_leak
    python scripts/chaos/runner.py --dry-run          # print plan only
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.chaos.scoring import fetch_incident_stats, score_scenario

logger = logging.getLogger(__name__)

# All available scenarios (module path relative to scripts/chaos/scenarios/)
ALL_SCENARIOS = [
    "memory_leak",
    "cpu_spike",
    "network_partition",
    "db_overload",
]

# How long to wait for agent swarm to detect + remediate before timing out (seconds)
DETECTION_TIMEOUT = 300
# How long to wait between scenarios (let the stack stabilise)
COOLDOWN_SECONDS = 60


def _load_scenario(name: str):
    module_path = f"scripts.chaos.scenarios.{name}"
    return importlib.import_module(module_path)


def run_scenario(name: str, dry_run: bool = False) -> dict:
    """Execute one chaos scenario and return a result dict."""
    mod = _load_scenario(name)
    logger.info("=" * 60)
    logger.info("Scenario: %s", name)
    logger.info("Description: %s", getattr(mod, "DESCRIPTION", "—"))

    if dry_run:
        logger.info("[DRY-RUN] Would inject %s — skipping.", name)
        return {
            "scenario": name,
            "dry_run": True,
            "injected_at": None,
            "mttd_seconds": None,
            "mttr_seconds": None,
            "outcome": "dry_run",
        }

    result = mod.run()
    injected_at: float = result["injected_at"]

    logger.info("Chaos injected — waiting up to %ds for agent swarm to respond…", DETECTION_TIMEOUT)

    # Poll the DB for a new incident that was created after injection
    mttd = None
    mttr = None
    deadline = time.time() + DETECTION_TIMEOUT
    while time.time() < deadline:
        stats = fetch_incident_stats(since_epoch=injected_at)
        if stats and stats.get("detected_at"):
            mttd = stats["detected_at"] - injected_at
            if stats.get("resolved_at"):
                mttr = stats["resolved_at"] - injected_at
                break
        time.sleep(10)

    if mttd is None:
        logger.error("No incident detected within %ds — agent swarm may not be running.", DETECTION_TIMEOUT)
        outcome = "undetected"
    elif mttr is None:
        logger.warning("Incident detected (MTTD=%.0fs) but not resolved within timeout.", mttd)
        outcome = "detected_not_resolved"
    else:
        logger.info("✅  Resolved! MTTD=%.0fs  MTTR=%.0fs", mttd, mttr)
        outcome = "resolved"

    # Cleanup regardless of outcome
    try:
        mod.cleanup()
    except Exception as e:
        logger.warning("Scenario cleanup raised: %s", e)

    return {
        "scenario": name,
        "dry_run": False,
        "injected_at": injected_at,
        "mttd_seconds": round(mttd, 1) if mttd else None,
        "mttr_seconds": round(mttr, 1) if mttr else None,
        "outcome": outcome,
        "score": score_scenario(mttd, mttr),
    }


def generate_report(results: list[dict], path: str | None = None) -> str:
    """Render results as a Markdown report and optionally write to disk."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# SRE Agent Chaos Engineering Report",
        f"",
        f"**Generated:** {now}",
        f"",
        f"## Results",
        f"",
        f"| Scenario | Outcome | MTTD (s) | MTTR (s) | Score |",
        f"|----------|---------|----------|----------|-------|",
    ]
    for r in results:
        mttd = r.get("mttd_seconds", "—") or "—"
        mttr = r.get("mttr_seconds", "—") or "—"
        score = r.get("score", "—") or "—"
        lines.append(
            f"| {r['scenario']} | {r['outcome']} | {mttd} | {mttr} | {score} |"
        )

    lines += [
        "",
        "## Score Legend",
        "",
        "| Score | Meaning |",
        "|-------|---------|",
        "| 💚 A (≥90) | MTTD < 60s, MTTR < 120s — excellent |",
        "| 🟡 B (≥70) | MTTD < 120s, MTTR < 300s — acceptable |",
        "| 🟠 C (≥50) | Detected but slow remediation |",
        "| 🔴 F (<50) | Undetected or timed out |",
    ]

    report = "\n".join(lines)

    if path:
        Path(path).write_text(report)
        logger.info("Report written to %s", path)

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="SRE Agent Chaos Runner")
    parser.add_argument("--scenario", choices=ALL_SCENARIOS, help="Run only this scenario")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without injecting")
    parser.add_argument("--cooldown", type=int, default=COOLDOWN_SECONDS,
                        help=f"Seconds to wait between scenarios (default {COOLDOWN_SECONDS})")
    args = parser.parse_args()

    scenarios = [args.scenario] if args.scenario else ALL_SCENARIOS
    results = []

    for i, name in enumerate(scenarios):
        result = run_scenario(name, dry_run=args.dry_run)
        results.append(result)
        if not args.dry_run and i < len(scenarios) - 1:
            logger.info("Cooling down for %ds before next scenario…", args.cooldown)
            time.sleep(args.cooldown)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"scripts/chaos/report_{timestamp}.md"
    report = generate_report(results, path=report_path)
    print("\n" + report)


if __name__ == "__main__":
    main()
