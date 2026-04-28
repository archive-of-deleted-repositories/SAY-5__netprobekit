from __future__ import annotations

from netprobe.probes import firmware


def test_version_is_semver(transport):
    info = firmware.info(transport)
    assert firmware.is_semver(info.version), f"not semver: {info.version!r}"


def test_expected_version_pinned(transport):
    info = firmware.info(transport)
    # The framework pins an expected firmware version per build slot;
    # this test is the canary for accidentally-flashed wrong builds.
    assert info.version == "1.4.2", (
        f"target reports firmware {info.version!r}, expected 1.4.2"
    )


def test_flash_region_returns_crc(transport):
    ok, crc = firmware.flash_region_ok(transport, addr=0x1000, length=128)
    assert ok
    assert crc != 0
