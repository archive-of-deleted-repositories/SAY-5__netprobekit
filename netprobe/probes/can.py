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


# ----------------------------- error injection ---------------------------

@dataclass
class FaultedFrame:
    """A frame from a fault-injection scenario plus the bus-state the
    target reports after the injection. Probes assert the validator
    catches the right kind of fault — same shape as a real CAN
    controller that would abort the frame mid-bus."""

    fault: str           # "crc" | "stuff" | "ack" | "form"
    err: str             # human-readable error from the target
    frame: CANFrame
    crc_actual: int
    crc_expected: int
    bus_state: str       # "error_active" | "error_passive" | "bus_off"
    error_count: int


def inject_fault(t: Transport, fault: str) -> FaultedFrame:
    """Ask the target to emit a frame with `fault` corruption."""
    r = t.request("can_inject_fault", id=fault)
    f = r.get("frame", {})
    return FaultedFrame(
        fault=str(r.get("fault", "")),
        err=str(r.get("err", "")),
        frame=CANFrame(
            id=int(f.get("id", 0)), dlc=int(f.get("dlc", 0)),
            data=list(f.get("data", [])),
        ),
        crc_actual=int(f.get("crc_actual", 0)),
        crc_expected=int(f.get("crc_expected", 0)),
        bus_state=str(r.get("bus_state", "error_active")),
        error_count=int(r.get("error_count", 0)),
    )


def bus_state(t: Transport) -> tuple[str, int]:
    r = t.request("can_bus_state")
    return str(r.get("bus_state", "error_active")), int(r.get("error_count", 0))


def bus_reset(t: Transport) -> str:
    r = t.request("can_bus_reset")
    return str(r.get("bus_state", "error_active"))


def classify_fault(ff: FaultedFrame) -> str:
    """Probe-side controller logic. Given a faulted frame, return the
    kind of error a real driver would raise at this layer."""
    if ff.crc_actual != ff.crc_expected:
        return "crc_mismatch"
    if ff.frame.dlc < 0 or ff.frame.dlc > 8:
        return "stuff_bit_violation"
    if not (0 <= ff.frame.id <= 0x7FF):
        return "form_error"
    if ff.fault == "ack":
        return "ack_missing"
    return "ok"
