"""Ethernet probes — link, throughput, integrity."""

from __future__ import annotations

import time
import zlib
from dataclasses import dataclass

from netprobe.transport import Transport


@dataclass
class PingResult:
    ok: bool
    latency_ms: float
    pong: str


def ping(t: Transport) -> PingResult:
    t0 = time.perf_counter()
    r = t.request("ping")
    elapsed = (time.perf_counter() - t0) * 1000.0
    return PingResult(ok=bool(r.get("ok")), latency_ms=elapsed, pong=r.get("pong", ""))


@dataclass
class ThroughputResult:
    ok: bool
    bytes: int
    elapsed_ms: float
    mb_per_sec: float


def throughput(t: Transport, n_bytes: int = 256_000, seed: int = 0xDEADBEEF) -> ThroughputResult:
    t0 = time.perf_counter()
    r = t.request("throughput", n=n_bytes, seed=seed)
    elapsed = (time.perf_counter() - t0) * 1000.0
    payload = r.get("payload", "")
    mbps = (len(payload) / 1_000_000.0) / max(elapsed / 1000.0, 1e-6)
    return ThroughputResult(
        ok=bool(r.get("ok")) and len(payload) >= n_bytes,
        bytes=len(payload),
        elapsed_ms=elapsed,
        mb_per_sec=mbps,
    )


@dataclass
class IntegrityResult:
    ok: bool
    bytes: int
    expected_crc: int
    target_crc: int


def integrity(t: Transport, n_bytes: int = 4096, seed: int = 0xA5A5A5A5) -> IntegrityResult:
    """Asks the target to compute a CRC on a deterministic byte stream
    derived from `seed`. The probe computes the same stream client-side
    and asserts the CRCs match."""
    r = t.request("integrity", n=n_bytes, seed=seed)
    expected = _expected_crc(seed, n_bytes)
    target_crc = int(r.get("crc", 0))
    return IntegrityResult(
        ok=bool(r.get("ok")) and expected == target_crc,
        bytes=int(r.get("bytes", 0)),
        expected_crc=expected,
        target_crc=target_crc,
    )


def _expected_crc(seed: int, n: int) -> int:
    # Mirror the LCG the target uses, then standard CRC-32 (zlib).
    s = seed & 0xFFFFFFFFFFFFFFFF
    out = bytearray(n)
    for i in range(n):
        s = (s * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        out[i] = (s >> 33) & 0xFF
    return zlib.crc32(out) & 0xFFFFFFFF
