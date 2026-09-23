# Test reports

`pytest` writes `reports/junit.xml`.

```bash
pytest
python tools/render_report.py
```

That fills `templates/test_report.html` into `reports/index.html`.

The sample cases are built on `examples/powertrain_demo.dbc` (ECM / BCM / Gateway, classic CAN + CAN FD, E2E 11A on `EngineData`).
