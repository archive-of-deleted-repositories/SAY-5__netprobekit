"""CAN error-injection scenarios. Each fault is requested from the
target and asserted to be classified correctly by the probe-side
controller logic. Bus-state confinement is exercised by injecting
faults until the bus reports `bus_off`."""

from __future__ import annotations

import pytest

from netprobe.probes import can


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("crc",   "crc_mismatch"),
        ("stuff", "stuff_bit_violation"),
        ("form",  "form_error"),
        ("ack",   "ack_missing"),
    ],
)
def test_each_fault_classified(transport, kind, expected):
    can.bus_reset(transport)
    ff = can.inject_fault(transport, kind)
    got = can.classify_fault(ff)
    assert got == expected, (
        f"fault={kind} target_err={ff.err!r} got_classification={got!r}"
    )


def test_error_count_bumps_on_each_injection(transport):
    can.bus_reset(transport)
    state0, count0 = can.bus_state(transport)
    assert state0 == "error_active"
    assert count0 == 0
    can.inject_fault(transport, "crc")
    state1, count1 = can.bus_state(transport)
    assert count1 == count0 + 1
    assert state1 in {"error_active", "error_passive"}


def test_bus_off_after_threshold_faults(transport):
    can.bus_reset(transport)
    # Threshold is 5 in target.c.
    for _ in range(5):
        can.inject_fault(transport, "crc")
    state, count = can.bus_state(transport)
    assert state == "bus_off"
    assert count >= 5


def test_bus_state_flows_active_passive_off(transport):
    """Walk the standard CAN 2.0B fault-confinement state machine:
    error_active → error_passive (≥3 errors) → bus_off (≥5 errors)."""
    can.bus_reset(transport)
    # 0..2 errors: still active.
    for _ in range(2):
        can.inject_fault(transport, "form")
    s, _ = can.bus_state(transport)
    assert s == "error_active"
    # 3..4 errors: passive.
    can.inject_fault(transport, "form")
    s, _ = can.bus_state(transport)
    assert s == "error_passive"
    # 5+: bus-off.
    can.inject_fault(transport, "form")
    can.inject_fault(transport, "form")
    s, _ = can.bus_state(transport)
    assert s == "bus_off"


def test_bus_reset_returns_to_active(transport):
    can.bus_reset(transport)
    for _ in range(5):
        can.inject_fault(transport, "crc")
    assert can.bus_state(transport)[0] == "bus_off"
    can.bus_reset(transport)
    assert can.bus_state(transport)[0] == "error_active"
    assert can.bus_state(transport)[1] == 0
