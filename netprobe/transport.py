"""JSON-line TCP client to the target daemon."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any


class TransportError(RuntimeError):
    """Raised when the target is unreachable or replies non-JSON."""


@dataclass
class Transport:
    host: str = "127.0.0.1"
    port: int = 9999
    timeout: float = 2.0

    def request(self, op: str, **kwargs: Any) -> dict:
        """One-shot RPC: open socket, send envelope, read reply, close."""
        payload: dict[str, Any] = {"op": op}
        payload.update(kwargs)
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.settimeout(self.timeout)
                s.sendall(line.encode("utf-8"))
                # The target writes one line per response. Read until newline
                # so multi-MB throughput payloads work.
                buf = bytearray()
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf.extend(chunk)
        except OSError as e:
            raise TransportError(f"transport failure for {op}: {e}") from e
        # The target ends payloads with \n; throughput puts the body on the
        # same line then \n.
        text = buf.decode("utf-8", errors="replace").rstrip("\n")
        # Sometimes multiple lines (e.g. throughput's body line) — concat.
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise TransportError(f"bad json from target for {op}: {e!r} payload={text[:120]!r}") from e

    def wait_ready(self, attempts: int = 10, sleep: float = 0.1) -> None:
        """Block until the target answers a ping; raise if it never does."""
        for _ in range(attempts):
            try:
                r = self.request("ping")
                if r.get("ok"):
                    return
            except TransportError:
                pass
            time.sleep(sleep)
        raise TransportError(f"target not ready after {attempts} attempts on {self.host}:{self.port}")
