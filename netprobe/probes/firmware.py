"""Firmware probes — version match, flash region CRC."""

from __future__ import annotations

import re
from dataclasses import dataclass

from netprobe.transport import Transport

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")


@dataclass
class FirmwareInfo:
    version: str
    crc: str


def info(t: Transport) -> FirmwareInfo:
    r = t.request("firmware_version")
    return FirmwareInfo(version=str(r.get("version", "")), crc=str(r.get("crc", "")))


def is_semver(v: str) -> bool:
    return bool(SEMVER_RE.match(v))


def flash_region_ok(t: Transport, addr: int, length: int) -> tuple[bool, int]:
    r = t.request("flash_region", addr=addr, len=length)
    return bool(r.get("ok")), int(r.get("crc", 0))
