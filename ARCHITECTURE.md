# NetProbeKit — Architecture

> A hardware-diagnostic test framework. Python orchestrates pytest-
> driven test suites; a C target daemon simulates an embedded device
> over a TCP control channel. The point of building it this way is
> to have an artifact that looks and feels like the real on-target
> validation you do before system integration — without needing real
> hardware in CI.

## What "the target" means

In a real hardware lab, the target is a board: an Ethernet PHY, a CAN
controller, a few I²C sensors, a flash region with versioned firmware.
For a portfolio repo without hardware, we replace the board with a
small C daemon (`target/`) that answers the same control-plane RPCs
the real probes would issue:

```
PROBE             RPC                           CHECK
─────             ───                           ─────
ethernet          PING                          link up; latency p99 < 5 ms
ethernet          THROUGHPUT bytes              echoes payload; throughput ≥ 10 MB/s
ethernet          INTEGRITY bytes seed          payload + crc32; checksum matches
can               READ_FRAMES n                 returns N frames; ID, DLC, data valid
can               TX_FRAME id data              echoes; assert no bus errors
sensor            READ id                       float reading in expected range
sensor            HISTORY id                    last 100 readings; std dev within tolerance
firmware          VERSION                       semver; matches expected
firmware          REGION addr len               flash region readable; CRC matches
```

The daemon is intentionally small (~400 lines of C) and speaks
line-delimited JSON over TCP. The same probe code, pointed at a real
test fixture, would issue raw socket / SocketCAN / linux-i2c-tools
calls instead — the abstraction is at the probe layer in Python.

## Layout

```
netprobekit/
├── target/                     # the simulated DUT
│   ├── target.c
│   └── Makefile
├── netprobe/                   # Python framework
│   ├── transport.py            # the JSON-line TCP client
│   ├── probes/
│   │   ├── ethernet.py
│   │   ├── can.py
│   │   ├── sensor.py
│   │   └── firmware.py
│   ├── runner.py               # pytest plugin / report aggregator
│   └── report.py               # JSON + JUnit XML emission
├── tests/
│   ├── conftest.py             # fixture: spawn target, expose `probe`
│   ├── test_ethernet.py
│   ├── test_can.py
│   ├── test_sensor.py
│   └── test_firmware.py
├── web/                        # test-bench UI (industrial aesthetic)
│   └── ...
└── cmd/netprobe                # CLI: run suite, print report
```

## Why JSON-line over TCP

Three properties that matter:

1. **Cross-language readable.** A C target written by an embedded
   engineer who's never touched Python, and a Python harness written
   by someone who's never touched C, can talk via `printf("{...}\n")`
   and `socket.recv().decode().splitlines()`.
2. **Trivially debuggable.** `nc 127.0.0.1 9999` and you can issue
   probes by hand. No protobuf/gRPC tooling required to see what's
   on the wire.
3. **Cheap to log.** Every probe round-trip is one append to a
   `runs/<timestamp>/wire.jsonl` file; replay during failure
   investigation is `cat`.

The "we'd use a real protocol in production" caveat: when this
framework moves on-target you'd swap `transport.py` for the actual
linux-tools backends. The probes don't change.

## Test reporting

We pipe pytest results through a small reporter (`netprobe/report.py`)
that produces:

- **JUnit XML** — for CI ingestion (GitHub Actions, etc.)
- **`runs/<timestamp>/report.json`** — structured, includes per-test
  metadata (target version, probe parameters, raw response, timing)
- **`runs/<timestamp>/index.html`** — the test-bench UI we ship in
  `web/`, point it at the JSON report and you have a static viewer
  with no server.

## Failure model

Hardware tests have a different failure character than software:

- **Flaky** — environmental noise. We retry-and-tighten: each probe
  has a `tolerance` parameter; the runner can re-execute and
  aggregate, but the reporter flags any test that needed a retry.
- **Catastrophic** — link down, board unresponsive. The fixture
  detects target-not-ready up front (`probe.ping()` 3× before any
  test runs); if the target is dead, the entire suite skips with
  a clear "target down" message instead of cascading 200 timeouts.
- **Configuration drift** — wrong firmware version on the board.
  The first action of every test session is `firmware.version()`,
  written into the report header. A version mismatch fails fast
  with a single, actionable line.

## Performance / scope

This is a test framework, not a high-throughput service. The
performance bar is "exhausts the suite in <30 s on a CI runner" so
nobody disables it.

## Non-goals

- **Real hardware drivers.** Out of scope for a portfolio repo;
  documented as the swap point.
- **GUI for live debugging.** The web UI is a static report viewer,
  not a live console. (`watch curl localhost:9999/health` is the
  live console.)
- **Multi-DUT orchestration.** One target at a time. Real labs have
  Jenkins matrices that fan out; that layer is out of scope.
