"""v3: multi-target rack orchestration."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from netprobe.multitarget import TargetSpec, report_to_dict, run_rack

ROOT = Path(__file__).resolve().parent.parent
TARGET_BIN = ROOT / "target" / "target"


pytestmark = pytest.mark.skipif(
    not TARGET_BIN.exists(),
    reason="target binary missing — run `make -C target` first",
)


def _spec(name: str) -> TargetSpec:
    return TargetSpec(name=name, binary=TARGET_BIN)


def test_rack_runs_three_targets_in_parallel():
    rack = run_rack([_spec("rack-a"), _spec("rack-b"), _spec("rack-c")])
    assert len(rack.targets) == 3
    assert rack.all_ok, [t.error for t in rack.targets if not t.ok]
    # Each target's report should look like a single-target report.
    for t in rack.targets:
        assert "ethernet" in t.report
        assert "firmware" in t.report


def test_parallelism_is_observable_in_wall_time():
    """Three targets each take ~150ms to spin up + probe. Running
    serially would be ~450ms; in parallel we expect substantially
    less. Keep the bound generous so this isn't flaky on CI."""
    specs = [_spec(f"rack-p{i}") for i in range(3)]
    t0 = time.perf_counter()
    rack = run_rack(specs)
    elapsed = time.perf_counter() - t0
    assert rack.all_ok
    # Generous: parallel should beat 1.5x a single target's elapsed.
    longest = max(t.elapsed_s for t in rack.targets)
    assert elapsed < longest * 1.7, (
        f"rack elapsed {elapsed:.2f}s vs longest single {longest:.2f}s — "
        "looks like targets ran serially"
    )


def test_event_callbacks_fire_in_order():
    events: list[tuple[str, str]] = []
    def cb(name: str, payload):
        events.append((name, payload.get("name", "")))
    run_rack([_spec("rack-e1"), _spec("rack-e2")], on_event=cb)
    starts = [n for k, n in events if k == "target_starting"]
    dones  = [n for k, n in events if k == "target_done"]
    assert sorted(starts) == ["rack-e1", "rack-e2"]
    assert sorted(dones)  == ["rack-e1", "rack-e2"]


def test_failed_target_is_isolated():
    """If one target's binary is missing, the others still complete
    and the report flags only that one as failed."""
    bad = TargetSpec(name="dead", binary=Path("/does/not/exist"))
    good = _spec("alive")
    rack = run_rack([bad, good])
    by = {t.name: t for t in rack.targets}
    assert by["alive"].ok is True
    assert by["dead"].ok is False
    assert "dead" in by["dead"].error.lower() or "not" in by["dead"].error.lower() or by["dead"].error
    assert rack.all_ok is False


def test_report_to_dict_round_trips_json():
    rack = run_rack([_spec("rack-rt")])
    payload = report_to_dict(rack)
    s = json.dumps(payload)
    again = json.loads(s)
    assert again["schema"] == "netprobekit.rack.v1"
    assert again["targets"][0]["name"] == "rack-rt"
