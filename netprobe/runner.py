"""CLI runner: orchestrate a test session, emit a structured report."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from netprobe.probes import can, ethernet, firmware, sensor
from netprobe.transport import Transport


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_session(target_bin: Path, out_dir: Path) -> dict:
    """Spawn the target, run all probes once, write report.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    proc = subprocess.Popen([str(target_bin), str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # Wait for ready.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        t = Transport(host="127.0.0.1", port=port, timeout=2.0)
        report = _run_probes(t)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()

    report["session"] = {
        "started_at": datetime.now(UTC).isoformat(),
        "target_port": port,
    }
    out = out_dir / f"report-{int(time.time())}.json"
    out.write_text(json.dumps(report, indent=2))
    return report


def _run_probes(t: Transport) -> dict:
    fw = firmware.info(t)
    eth_ping = ethernet.ping(t)
    eth_thr = ethernet.throughput(t, n_bytes=128_000)
    eth_int = ethernet.integrity(t, n_bytes=4096, seed=0xA5A5A5A5)
    can_read = can.read_frames(t, n=8)
    can_validations = [(f, *can.validate_frame(f)) for f in can_read.frames]

    sensors = []
    for sid in ("tempC0", "tempC1", "vbat", "imu_g"):
        rd = sensor.read(t, sid)
        h = sensor.history(t, sid)
        sensors.append({
            "id": rd.id, "value": rd.value, "in_range": sensor.in_range(rd),
            "history_count": h.count, "history_mean": h.mean,
            "history_stddev": h.stddev,
        })

    return {
        "firmware": {"version": fw.version, "crc": fw.crc, "is_semver": firmware.is_semver(fw.version)},
        "ethernet": {
            "ping": {"ok": eth_ping.ok, "latency_ms": round(eth_ping.latency_ms, 3)},
            "throughput": {"ok": eth_thr.ok, "bytes": eth_thr.bytes, "mb_per_sec": round(eth_thr.mb_per_sec, 2)},
            "integrity": {
                "ok": eth_int.ok, "bytes": eth_int.bytes,
                "expected_crc": f"0x{eth_int.expected_crc:08x}",
                "target_crc":   f"0x{eth_int.target_crc:08x}",
            },
        },
        "can": {
            "frames": [{"id": f.id, "dlc": f.dlc, "data": f.data, "valid": ok, "why": why}
                       for (f, ok, why) in can_validations],
        },
        "sensors": sensors,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    target_bin = Path(args[0]) if args else Path("./target/target")
    out = Path("./runs")
    report = run_session(target_bin, out)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
