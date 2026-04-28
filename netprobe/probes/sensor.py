"""Sensor probes — read, history, statistical sanity."""

from __future__ import annotations

import math
from dataclasses import dataclass

from netprobe.transport import Transport


@dataclass
class SensorReading:
    id: str
    value: float
    unit: str


@dataclass
class HistoryResult:
    id: str
    count: int
    mean: float
    stddev: float


# Expected operating ranges per sensor. Defined here so tests assert
# the same numbers the field deployment would.
EXPECTED: dict[str, tuple[float, float]] = {
    "tempC0": (5.0, 40.0),
    "tempC1": (5.0, 40.0),
    "vbat":   (11.0, 13.5),
    "imu_g":  (9.7,  9.9),
}


def read(t: Transport, sensor_id: str) -> SensorReading:
    r = t.request("sensor_read", id=sensor_id)
    if not r.get("ok"):
        raise RuntimeError(f"sensor {sensor_id} read failed: {r.get('err')}")
    return SensorReading(id=str(r["id"]), value=float(r["value"]), unit=str(r.get("unit", "")))


def in_range(s: SensorReading) -> bool:
    lo, hi = EXPECTED.get(s.id, (-math.inf, math.inf))
    return lo <= s.value <= hi


def history(t: Transport, sensor_id: str) -> HistoryResult:
    r = t.request("sensor_history", id=sensor_id)
    vs = [float(x) for x in r.get("values", [])]
    if not vs:
        return HistoryResult(id=sensor_id, count=0, mean=0.0, stddev=0.0)
    mean = sum(vs) / len(vs)
    var = sum((v - mean) ** 2 for v in vs) / len(vs)
    return HistoryResult(id=sensor_id, count=len(vs), mean=mean, stddev=math.sqrt(var))
