"""Multi-target orchestration: run probes against N DUTs in parallel.

A real lab runs racks of devices, not one-at-a-time. v3 lets the
runner spin up multiple target binaries on free ports, fan probes
across them in parallel via a thread pool, and aggregate results
into a single report keyed by target id.

The framework treats each target as opaque — same C ``target``
binary, same JSON-line wire protocol, just a different port. The
report shape mirrors the single-target one with an extra ``target``
field so the dashboard can collapse / pivot across the rack.
"""

from __future__ import annotations

import concurrent.futures
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from netprobe.runner import _run_probes
from netprobe.transport import Transport


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class TargetSpec:
    """One DUT in the rack. `binary` is the path to the target
    executable; `args` is anything you want to pass after the port."""

    name: str
    binary: Path
    args: tuple[str, ...] = ()


@dataclass
class TargetReport:
    name: str
    port: int
    ok: bool
    error: str = ""
    started_at: float = 0.0
    elapsed_s: float = 0.0
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class RackReport:
    started_at: str
    elapsed_s: float
    targets: list[TargetReport]

    @property
    def all_ok(self) -> bool:
        return all(t.ok for t in self.targets)


def run_rack(
    specs: list[TargetSpec],
    *,
    max_workers: int | None = None,
    boot_timeout_s: float = 3.0,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> RackReport:
    """Spawn each spec on a free port concurrently, run the full probe
    suite against each, and aggregate. The thread pool defaults to
    `len(specs)` because each target's probe round-trip is mostly
    blocked on the target's TCP write, so threading suffices."""
    if not specs:
        return RackReport(
            started_at=_iso_now(), elapsed_s=0.0, targets=[],
        )
    workers = max_workers or len(specs)
    started = time.perf_counter()
    started_at = _iso_now()

    def _drive(spec: TargetSpec) -> TargetReport:
        port = _free_port()
        if on_event is not None:
            on_event("target_starting", {"name": spec.name, "port": port})
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(
                [str(spec.binary), str(port), *spec.args],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            tr = TargetReport(
                name=spec.name, port=port, ok=False,
                error=f"spawn failed: {e}",
                started_at=t0, elapsed_s=time.perf_counter() - t0,
            )
            if on_event is not None:
                on_event("target_done", {
                    "name": spec.name, "ok": False, "elapsed_s": tr.elapsed_s,
                })
            return tr
        try:
            _wait_ready(port, boot_timeout_s)
            t = Transport(host="127.0.0.1", port=port, timeout=2.0)
            payload = _run_probes(t)
            tr = TargetReport(
                name=spec.name, port=port, ok=True,
                started_at=t0, elapsed_s=time.perf_counter() - t0,
                report=payload,
            )
        except Exception as e:  # noqa: BLE001
            tr = TargetReport(
                name=spec.name, port=port, ok=False, error=str(e),
                started_at=t0, elapsed_s=time.perf_counter() - t0,
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        if on_event is not None:
            on_event("target_done", {
                "name": spec.name, "ok": tr.ok, "elapsed_s": tr.elapsed_s,
            })
        return tr

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        target_reports = list(pool.map(_drive, specs))

    return RackReport(
        started_at=started_at,
        elapsed_s=time.perf_counter() - started,
        targets=target_reports,
    )


def _wait_ready(port: int, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError as e:
            last = e
            time.sleep(0.05)
    raise RuntimeError(f"target on :{port} never came up within {timeout_s}s: {last!r}")


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def report_to_dict(r: RackReport) -> dict[str, Any]:
    """JSON-serializable shape; mirrors the single-target report layout
    so the existing web/ viewer renders it with minimal changes."""
    return {
        "schema": "netprobekit.rack.v1",
        "started_at": r.started_at,
        "elapsed_s": round(r.elapsed_s, 3),
        "all_ok": r.all_ok,
        "targets": [
            {
                "name": t.name,
                "port": t.port,
                "ok": t.ok,
                "error": t.error,
                "elapsed_s": round(t.elapsed_s, 3),
                "report": t.report,
            }
            for t in r.targets
        ],
    }
