# DBC Simulator — Product Specification

Physical CAN + CAN FD DBC simulator. Clone-and-run on Windows/macOS. Python 3.10+.

## Purpose

Load raw `.dbc` files and transmit/receive on real hardware (PCAN-USB or Vector). Not virtual-only.

## v1 scope

- Classic CAN and CAN FD in one process, independent channels
- Cyclic + event TX, RX status, signal edits
- E2E default **11A / AUTOSAR Profile 1**, pluggable profiles, CRC/counter/timeout faults
- Optional ASC logging, JSON scenario persistence
- Minimal UDS Read-DID sweep only
- Terminal color status (green/yellow/red) and later sparklines
- Local browser live view on `dbc-sim run --live` (status + last-N decode + TX edits)
- `pyproject.toml` pinned deps so clone-and-run matches across machines

## Non-goals (v1)

Cross-channel triggers, full UDS, packaged desktop GUI window, pip registry publish.
A local browser live view is in scope; a standalone GUI app is not.

## Hardware

Swappable bus interface. Backends: `null` (tests), `pcan`, `vector`. Missing adapter fails clearly.

## Sample network

`examples/powertrain_demo.dbc` — ECM/BCM/Gateway, EngineData @ 0x100 with E2E 11A, ChassisStatus as CAN FD.

## Tests

```
pytest
python tools/render_report.py
```
