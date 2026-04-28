from __future__ import annotations

import pytest

from netprobe.probes import sensor


@pytest.mark.parametrize("sid", ["tempC0", "tempC1", "vbat", "imu_g"])
def test_each_sensor_reads_in_range(transport, sid):
    s = sensor.read(transport, sid)
    assert sensor.in_range(s), (
        f"sensor {s.id} value {s.value} outside expected range "
        f"{sensor.EXPECTED[s.id]}"
    )


def test_history_has_full_window(transport):
    h = sensor.history(transport, "tempC0")
    assert h.count == 100
    # The simulated sensor has tight jitter; the std dev should be
    # small but non-zero. Tolerance is generous to keep the test
    # flake-free on noisy CI.
    assert 0.0 < h.stddev < 1.0


def test_unknown_sensor_raises(transport):
    with pytest.raises(RuntimeError):
        sensor.read(transport, "no-such-sensor")
