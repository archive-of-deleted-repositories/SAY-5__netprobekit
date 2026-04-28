# NetProbeKit

A hardware diagnostic + on-target test automation framework. Python
orchestrates pytest-driven test suites; a small C target daemon
simulates an embedded device over a TCP control channel.

## What's interesting

- **Real C target.** ~400 lines of straight-line C, compiled with
  `cc -O2`. It speaks line-delimited JSON and answers the same RPCs
  the real probes would issue against a board: ping, throughput,
  integrity (CRC), CAN frame read/transmit, sensor reads + history,
  firmware version + flash region CRC.
- **Probes are pure Python.** `netprobe/probes/` has one module per
  subsystem. Each probe is a function over a `Transport`; nothing
  about the framework forces async, dataclasses, or magic.
- **Audit-trail-first.** Every probe round-trip emits structured
  data; the runner consolidates a single `report.json` per session.
  The web UI is a static report viewer — drop a JSON file on the
  page, it draws an instrument-panel visualization.
- **Failure-fast on configuration drift.** First action of every
  session is `firmware.version()`. A version mismatch fails one test
  with a single, actionable line — no cascading 200 timeouts.

## Quick start

```bash
make -C target               # builds the C target daemon
pip install -e ".[dev]"
pytest -q                    # spawns the target as a session-scoped fixture

# One-shot: run all probes, write a report, hand it to the UI
python -m netprobe.runner ./target/target > web/report.json
python -m http.server 8000 --directory web
# open http://localhost:8000/
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the framework writeup
(why JSON-line over TCP, how the production swap is shaped, the
failure model).

## Tests (17 green)

```
test_ethernet.py    ping returns pong with firmware
                    throughput meets floor (≥1 MB/s on loopback)
                    integrity CRC matches target's
                    different seeds yield different CRCs
test_can.py         read returns N requested frames
                    every frame validates (ID/dlc/data shape)
                    tx is acked
                    invalid frames rejected by validator
test_sensor.py      each sensor in expected range (parametrized 4×)
                    history has 100-sample window, plausible stddev
                    unknown sensor raises
test_firmware.py    version is semver
                    pinned version match (canary for wrong builds)
                    flash region returns CRC
```

## Companion projects

Part of an eleven-repo set under [github.com/SAY-5](https://github.com/SAY-5):
canvaslive, pluginforge, agentlab, payflow, queryflow, datachat,
distributedkv, jobagent, inferencegateway, ticketsearch, **netprobekit**,
releaseguard.

## License

MIT.
