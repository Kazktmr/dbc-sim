import json
from urllib.request import Request, urlopen

from dbc_sim.frames import BusKind, ChannelConfig
from dbc_sim.live import LiveEngine
from dbc_sim.session import Session
from dbc_sim.web import LiveServer


def _session(demo_dbc_path, names=("powertrain",)) -> Session:
    session = Session(backend="null")
    specs = {
        "powertrain": ChannelConfig(name="powertrain", kind=BusKind.CAN, dbc_paths=[str(demo_dbc_path)]),
        "chassis": ChannelConfig(name="chassis", kind=BusKind.CANFD, dbc_paths=[str(demo_dbc_path)]),
    }
    for name in names:
        rt = session.add_channel(specs[name])
        for msg in rt.db.messages:
            if name == "powertrain" and not msg.is_fd:
                rt.add_cyclic(msg.name)
            elif name == "chassis" and msg.is_fd:
                rt.add_cyclic(msg.name)
    return session


def test_live_engine_records_decoded_frames(demo_dbc_path):
    engine = LiveEngine(_session(demo_dbc_path), seconds=0.03, step_s=0.001)
    engine.start()
    engine._thread.join(timeout=2)
    snap = engine.snapshot()
    assert snap["available_channels"] == ["powertrain"]
    assert snap["frames"], "expected rolling history"
    engine_frames = [f for f in snap["frames"] if f["name"] == "EngineData"]
    assert engine_frames
    last = engine_frames[-1]
    assert last["hex"]
    assert "EngineSpeed" in last["signals"]
    status = snap["channels"][0]["messages"]
    engine_row = next(m for m in status if m["name"] == "EngineData")
    assert engine_row["tx_count"] > 0
    assert engine_row["color"] in {"green", "yellow", "red", "gray"}


def test_live_pause_stops_tx(demo_dbc_path):
    engine = LiveEngine(_session(demo_dbc_path), seconds=None)
    engine.pause()
    rt = engine.session.runtimes["powertrain"]
    before = rt.status["EngineData"].tx_count
    engine.start()
    import time

    time.sleep(0.08)
    engine.stop()
    assert rt.status["EngineData"].tx_count == before


def test_live_signal_and_e2e_edit(demo_dbc_path):
    engine = LiveEngine(_session(demo_dbc_path))
    engine.set_signal("powertrain", "EngineData", "EngineSpeed", 2400.0)
    engine.set_e2e("powertrain", "EngineData", fault_crc=True)
    engine.set_cyclic("powertrain", "VehicleSpeed", False)
    job = engine.session.runtimes["powertrain"].jobs["EngineData"]
    assert job.values["EngineSpeed"] == 2400.0
    assert job.e2e.fault_crc is True
    assert engine.session.runtimes["powertrain"].jobs["VehicleSpeed"].enabled is False
    snap = engine.snapshot()
    row = next(m for m in snap["channels"][0]["messages"] if m["name"] == "EngineData")
    speed = next(s for s in row["signals"] if s["name"] == "EngineSpeed")
    assert speed["value"] == 2400.0
    assert row["e2e"]["fault_crc"] is True


def test_http_state_and_signal_edit(demo_dbc_path):
    engine = LiveEngine(_session(demo_dbc_path))
    server = LiveServer(engine, host="127.0.0.1", port=0)
    port = server.httpd.server_address[1]
    server.serve_in_thread()
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/state") as resp:
            snap = json.loads(resp.read().decode())
        assert snap["available_channels"] == ["powertrain"]
        payload = json.dumps(
            {"channel": "powertrain", "message": "EngineData", "signal": "EngineSpeed", "value": 1800}
        ).encode()
        req = Request(
            f"http://127.0.0.1:{port}/api/signal",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            edited = json.loads(resp.read().decode())
        row = next(m for m in edited["channels"][0]["messages"] if m["name"] == "EngineData")
        speed = next(s for s in row["signals"] if s["name"] == "EngineSpeed")
        assert speed["value"] == 1800.0
    finally:
        server.shutdown()
        engine.stop()


def test_cli_run_help_mentions_live():
    from dbc_sim.app import build_parser

    parser = build_parser()
    run = parser._subparsers._group_actions[0].choices["run"]
    help_text = run.format_help()
    assert "--live" in help_text
    assert "--channel" in help_text
