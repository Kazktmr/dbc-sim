# dbc-sim

Physical **CAN + CAN FD** DBC simulator for laptops (Windows / macOS).

Load one or more raw `.dbc` files, send and receive on a **PCAN-USB** or **Vector** adapter, edit signals, inject E2E faults, log ASC, and keep a scenario file so a coworker can clone and run the same setup.

This is the first cut: core models, a sample automotive DBC, unit tests, and a test-report template. Hardware TX/RX lands next; the bus interface is already swappable.

## Clone and run

```bash
git clone https://github.com/Kazktmr/dbc-sim.git
cd dbc-sim
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
dbc-sim --help
pytest
```

Pinned versions live in `pyproject.toml` so machines do not drift.

## What v0.1 already does (no dongle required)

- Parse a standard-style automotive `.dbc` (and `cantools` when installed)
- Pack / unpack Intel and Motorola signals
- Build classic CAN and CAN FD frames in the same session
- AUTOSAR E2E Profile 1 / **11A** (CRC-8 SAE J1850 + 4-bit counter) with fault injection
- Cyclic + event scheduling against a null bus (tests) or a future hardware bus
- Optional ASC logger
- Scenario JSON save / load
- UDS Read-DID (`0x22`) request builder
- Color status model (green / yellow / red)

## Tests and report

```bash
pytest
# reports/junit.xml          machine-readable
# reports/index.html         human report rendered from templates/test_report.html
python tools/render_report.py
```

The sample network is `examples/powertrain_demo.dbc` — a small powertrain + chassis mix with classic CAN and CAN FD messages and E2E on `EngineData`.

## Spec

See [SPEC.md](SPEC.md).
