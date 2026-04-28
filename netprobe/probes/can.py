"""CAN bus probes — read frames, transmit, validate."""

from __future__ import annotations

from dataclasses import dataclass

from netprobe.transport import Transport


@dataclass
class CANFrame:
    id: int
    dlc: int
    data: list[int]


@dataclass
class ReadResult:
    ok: bool
    frames: list[CANFrame]


def read_frames(t: Transport, n: int = 4) -> ReadResult:
    r = t.request("can_read_frames", n=n)
    frames = [CANFrame(id=int(f["id"]), dlc=int(f["dlc"]), data=list(f["data"]))
              for f in r.get("frames", [])]
    return ReadResult(ok=bool(r.get("ok")), frames=frames)


def validate_frame(f: CANFrame) -> tuple[bool, str]:
    """Check a single frame against the bus's invariants."""
    if not (0 <= f.id <= 0x7FF):
        return False, f"id 0x{f.id:x} out of 11-bit range"
    if not (0 <= f.dlc <= 8):
        return False, f"dlc {f.dlc} out of 0..8"
    if len(f.data) != f.dlc:
        return False, f"dlc/data mismatch: dlc={f.dlc} len(data)={len(f.data)}"
    if any(b < 0 or b > 255 for b in f.data):
        return False, "data byte out of range"
    return True, ""


def tx(t: Transport, can_id: int) -> bool:
    r = t.request("can_tx", id=can_id)
    return bool(r.get("ok")) and bool(r.get("acked"))
