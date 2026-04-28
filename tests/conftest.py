"""Pytest fixtures: spawn the C target, expose `transport` to tests."""

from __future__ import annotations

import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from netprobe.transport import Transport

ROOT = Path(__file__).resolve().parent.parent
TARGET_BIN = ROOT / "target" / "target"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def target_proc() -> Iterator[tuple[subprocess.Popen, int]]:
    """Builds the C target if missing, spawns it on a free port, tears
    it down at session end."""
    if not TARGET_BIN.exists():
        # Best-effort: tell the operator to run `make`.
        subprocess.check_call(["make"], cwd=ROOT / "target")
    port = _free_port()
    proc = subprocess.Popen(
        [str(TARGET_BIN), str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    # Wait for the target to be ready.
    deadline = time.time() + 3.0
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError as e:
            last_err = e
            time.sleep(0.05)
    else:
        proc.kill()
        raise RuntimeError(f"target never came up on :{port}: {last_err!r}")

    yield proc, port

    proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def transport(target_proc) -> Transport:
    _, port = target_proc
    return Transport(host="127.0.0.1", port=port, timeout=2.0)
