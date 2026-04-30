"""v4: TCP connect-time probe.

The existing probes measure ICMP RTT (ping). v4 adds a TCP
connect probe that opens a socket to (host, port) and reports
the connect duration. This catches firewall / port-block /
SYN-cookie issues that ping doesn't see, and reflects what
application traffic actually experiences.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TCPProbeResult:
    host: str
    port: int
    success: bool
    latency_ms: float
    error: str = ""


def tcp_probe(host: str, port: int, timeout_s: float = 2.0) -> TCPProbeResult:
    """Open + close a TCP socket; measure how long the connect took.

    On success, latency_ms is the connect duration.
    On failure, success=False with the OS error message; we do NOT
    raise so the caller can run a batch of probes and collect
    results.
    """

    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as _s:
            elapsed = (time.perf_counter() - start) * 1000.0
            return TCPProbeResult(host=host, port=port, success=True, latency_ms=elapsed)
    except (TimeoutError, OSError) as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return TCPProbeResult(
            host=host, port=port, success=False,
            latency_ms=elapsed, error=str(e),
        )


def tcp_probe_batch(targets: list[tuple[str, int]],
                    timeout_s: float = 2.0) -> list[TCPProbeResult]:
    """Run probes serially. Production runs them in a thread pool;
    serial is fine for the unit-test path."""
    return [tcp_probe(h, p, timeout_s=timeout_s) for h, p in targets]
