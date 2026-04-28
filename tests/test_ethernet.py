from __future__ import annotations

from netprobe.probes import ethernet


def test_ping_returns_pong_with_firmware(transport):
    r = ethernet.ping(transport)
    assert r.ok
    assert r.pong, "expected non-empty firmware version in pong"
    # On a quiet local target, p99-ish ping should be fast.
    assert r.latency_ms < 50, f"latency {r.latency_ms:.2f}ms too high"


def test_throughput_meets_floor(transport):
    r = ethernet.throughput(transport, n_bytes=128_000)
    assert r.ok
    # Local socket throughput should clear ~5 MB/s easily.
    assert r.mb_per_sec >= 1.0, f"throughput {r.mb_per_sec:.2f} MB/s too low"
    assert r.bytes >= 128_000


def test_integrity_checksum_matches_target(transport):
    """The target's CRC of a deterministic byte stream must match the
    CRC we compute client-side from the same seed. Any divergence
    indicates a wire-encoding or RNG mismatch."""
    r = ethernet.integrity(transport, n_bytes=4096, seed=0xA5A5A5A5)
    assert r.ok, (
        f"crc mismatch: target=0x{r.target_crc:08x} expected=0x{r.expected_crc:08x}"
    )


def test_integrity_with_different_seed(transport):
    # A different seed must produce a different CRC.
    r1 = ethernet.integrity(transport, n_bytes=4096, seed=1)
    r2 = ethernet.integrity(transport, n_bytes=4096, seed=2)
    assert r1.target_crc != r2.target_crc
