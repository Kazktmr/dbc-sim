# Generated example reports

This folder holds the **latest generated** human-readable report from the sample automotive DBC.

- `index.html` — filled from `templates/test_report.html` using `reports/junit.xml`
- `junit.xml` — machine-readable pytest output

## How it stays fresh

On every push to `main`, the CI workflow:

1. runs `pytest` against `examples/powertrain_demo.dbc`
2. renders `reports/index.html`
3. commits the updated report back to `main`

So the report in this folder always reflects the current tool + sample DBC, without manual work.

Locally:

```bash
pytest
python tools/render_report.py
```

The sample network is `examples/powertrain_demo.dbc` — ECM / BCM / Gateway, classic CAN + CAN FD, E2E 11A on `EngineData`.
