"""v4 tests: TCP connect probe.

We test against a temporary server we spin up in-process so the
test doesn't depend on the network. Closed ports + DNS failures
are tested separately."""

from __future__ import annotations

import socket
import threading

from netprobe.probes.tcp import tcp_probe, tcp_probe_batch


def _start_listener() -> tuple[socket.socket, int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    def _accept():
        try:
            conn, _ = s.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_accept, daemon=True)
    t.start()
    return s, port


def test_open_port_returns_success() -> None:
    server, port = _start_listener()
    try:
        result = tcp_probe("127.0.0.1", port, timeout_s=1.0)
        assert result.success
        assert result.latency_ms >= 0
        assert result.error == ""
    finally:
        server.close()


def test_closed_port_returns_failure() -> None:
    # Pick a port that almost certainly isn't listening.
    result = tcp_probe("127.0.0.1", 1, timeout_s=0.2)
    assert not result.success
    assert "refused" in result.error.lower() or "denied" in result.error.lower() \
        or "timed out" in result.error.lower()


def test_unresolvable_host_returns_failure() -> None:
    result = tcp_probe("does-not-exist-no-really.invalid", 80, timeout_s=0.5)
    assert not result.success
    assert result.error != ""


def test_batch_returns_one_per_target() -> None:
    server, port = _start_listener()
    try:
        results = tcp_probe_batch([
            ("127.0.0.1", port),
            ("127.0.0.1", 1),
        ], timeout_s=0.5)
        assert len(results) == 2
        assert results[0].success
        assert not results[1].success
    finally:
        server.close()
