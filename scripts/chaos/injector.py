#!/usr/bin/env python3
"""
Chaos Injector Primitives
=========================
Core building blocks for simulating failure conditions inside the running
Docker Compose environment.  Wraps ``docker`` SDK calls to operate on
containers by name or label.

Exported functions:
  - kill_container(name)         → Sends SIGKILL to the container
  - pause_container(name)        → Freezes the container (SIGSTOP)
  - resume_container(name)       → Thaws the container (SIGCONT)
  - stress_cpu(name, cores, secs) → Spawns stress-ng inside the container
  - stress_memory(name, mb, secs) → Allocates `mb` MiB of RAM inside container
  - add_network_latency(name, ms, jitter_ms) → tc netem latency
  - clear_network_latency(name)  → Removes tc netem rules
  - fill_disk(name, mb)          → Writes a temporary file inside the container
"""

from __future__ import annotations

import logging
import shlex
import time
from typing import Optional

import docker
from docker.errors import NotFound, APIError

logger = logging.getLogger(__name__)
_client = docker.from_env()


def _get_container(name: str):
    """Retrieve a Docker container object by name, raising if not found."""
    try:
        return _client.containers.get(name)
    except NotFound:
        raise ValueError(f"Container '{name}' not found. Is the stack running?")


def _exec(container, cmd: str, *, detach: bool = False) -> Optional[str]:
    """Execute a shell command inside a container and return stdout."""
    result = container.exec_run(cmd=shlex.split(cmd), detach=detach)
    if not detach:
        return result.output.decode(errors="replace").strip()
    return None


# ─── Container lifecycle ─────────────────────────────────────────────────────────

def kill_container(name: str, signal: str = "SIGKILL") -> None:
    """
    Send a signal to a running container, simulating a crash.

    Args:
        name:   Container name (as defined in docker-compose.yml).
        signal: POSIX signal string, default SIGKILL.
    """
    c = _get_container(name)
    c.kill(signal=signal)
    logger.warning("[CHAOS] Killed container '%s' with %s", name, signal)


def pause_container(name: str) -> None:
    """Pause (freeze) a container — simulates a hung process."""
    c = _get_container(name)
    c.pause()
    logger.warning("[CHAOS] Paused container '%s'", name)


def resume_container(name: str) -> None:
    """Resume a paused container."""
    c = _get_container(name)
    c.unpause()
    logger.info("[CHAOS] Resumed container '%s'", name)


def restart_container(name: str) -> None:
    """Restart a container — used by recovery scripts."""
    c = _get_container(name)
    c.restart()
    logger.info("[CHAOS] Restarted container '%s'", name)


# ─── CPU / Memory stress ─────────────────────────────────────────────────────────

def stress_cpu(name: str, cores: int = 2, duration_seconds: int = 60) -> None:
    """
    Spawn ``stress-ng`` inside the container to saturate CPU cores.

    Requires ``stress-ng`` to be installed in the container image.
    For minimal images use the fallback pure-Python busy loop.
    """
    c = _get_container(name)
    cmd = f"stress-ng --cpu {cores} --timeout {duration_seconds}s --metrics-brief"
    try:
        _exec(c, cmd, detach=True)
        logger.warning("[CHAOS] CPU stress started on '%s' (%d cores, %ds)", name, cores, duration_seconds)
    except Exception:
        # Fallback: endless Python computation in background
        fallback = (
            f"python3 -c \"import time; end=time.time()+{duration_seconds}; "
            f"[sum(i*i for i in range(10000)) for _ in iter(lambda: time.time()<end, False)]\""
        )
        _exec(c, fallback, detach=True)
        logger.warning("[CHAOS] CPU stress (python fallback) started on '%s'", name)


def stress_memory(name: str, mb: int = 512, duration_seconds: int = 60) -> None:
    """
    Allocate a large byte array inside the container to simulate a memory leak.
    """
    c = _get_container(name)
    cmd = (
        f"python3 -c \""
        f"import time; x = bytearray({mb * 1024 * 1024}); time.sleep({duration_seconds})"
        f"\""
    )
    _exec(c, cmd, detach=True)
    logger.warning("[CHAOS] Memory stress started on '%s' (%d MiB, %ds)", name, mb, duration_seconds)


# ─── Network disruption ───────────────────────────────────────────────────────────

def add_network_latency(name: str, latency_ms: int = 200, jitter_ms: int = 50) -> None:
    """
    Add artificial network latency via ``tc netem`` inside the container.

    Requires ``iproute2`` in the container image.
    """
    c = _get_container(name)
    # Clear any existing rules first
    _exec(c, "tc qdisc del dev eth0 root", detach=False)
    cmd = f"tc qdisc add dev eth0 root netem delay {latency_ms}ms {jitter_ms}ms"
    _exec(c, cmd)
    logger.warning("[CHAOS] Network latency %dms±%dms added to '%s'", latency_ms, jitter_ms, name)


def clear_network_latency(name: str) -> None:
    """Remove tc netem rules from a container's network interface."""
    c = _get_container(name)
    _exec(c, "tc qdisc del dev eth0 root")
    logger.info("[CHAOS] Network latency cleared on '%s'", name)


def drop_network_packets(name: str, loss_percent: int = 30) -> None:
    """Introduce packet loss to simulate a flaky network."""
    c = _get_container(name)
    _exec(c, "tc qdisc del dev eth0 root")
    cmd = f"tc qdisc add dev eth0 root netem loss {loss_percent}%"
    _exec(c, cmd)
    logger.warning("[CHAOS] Packet loss %d%% added to '%s'", loss_percent, name)


# ─── Disk pressure ────────────────────────────────────────────────────────────────

def fill_disk(name: str, mb: int = 1024, path: str = "/tmp/chaos_fill") -> None:
    """
    Write a large file inside the container to consume disk space.
    """
    c = _get_container(name)
    cmd = f"dd if=/dev/urandom of={path} bs=1M count={mb} status=none"
    _exec(c, cmd, detach=True)
    logger.warning("[CHAOS] Disk fill started on '%s' (%d MiB at %s)", name, mb, path)


def clear_disk_fill(name: str, path: str = "/tmp/chaos_fill") -> None:
    """Remove the disk-fill file to free space."""
    c = _get_container(name)
    _exec(c, f"rm -f {path}")
    logger.info("[CHAOS] Disk fill cleared on '%s'", name)
