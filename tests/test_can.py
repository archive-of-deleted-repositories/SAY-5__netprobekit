from __future__ import annotations

from netprobe.probes import can


def test_read_returns_requested_count(transport):
    r = can.read_frames(transport, n=5)
    assert r.ok
    assert len(r.frames) == 5


def test_every_frame_validates(transport):
    r = can.read_frames(transport, n=8)
    for f in r.frames:
        ok, why = can.validate_frame(f)
        assert ok, f"frame {f} invalid: {why}"


def test_tx_frame_acked(transport):
    assert can.tx(transport, can_id=0x123) is True


def test_invalid_frame_rejected_by_validator():
    """The validator itself is the test target for this one — a frame
    we hand-craft with bad shape must be rejected."""
    bad = can.CANFrame(id=0x999, dlc=4, data=[1, 2, 3])  # dlc/data mismatch
    ok, _why = can.validate_frame(bad)
    assert not ok
