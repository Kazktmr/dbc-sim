from pathlib import Path

from dbc_sim.config import Scenario
from dbc_sim.frames import BusKind, CanFrame, ChannelConfig
from dbc_sim.log_asc import AscLogger
from dbc_sim.session import Session
from dbc_sim.uds import did_sweep_frames, read_did_request


def test_scenario_roundtrip(tmp_path: Path, demo_dbc_path: Path):
    scenario = Scenario(
        channels=[
            ChannelConfig(name="powertrain", kind=BusKind.CAN, dbc_paths=[str(demo_dbc_path)]),
            ChannelConfig(name="chassis", kind=BusKind.CANFD, dbc_paths=[str(demo_dbc_path)]),
        ],
        signal_overrides={"EngineData": {"EngineSpeed": 2400.0}},
        logging_enabled=False,
        backend="null",
    )
    path = tmp_path / "scene.json"
    scenario.save(path)
    loaded = Scenario.load(path)
    assert loaded.channels[0].kind is BusKind.CAN
    assert loaded.channels[1].kind is BusKind.CANFD
    assert loaded.signal_overrides["EngineData"]["EngineSpeed"] == 2400.0


def test_session_from_scenario_ticks_both_kinds(tmp_path: Path, demo_dbc_path: Path):
    scenario = Scenario(
        channels=[
            ChannelConfig(name="powertrain", kind=BusKind.CAN, dbc_paths=[str(demo_dbc_path)]),
            ChannelConfig(name="chassis", kind=BusKind.CANFD, dbc_paths=[str(demo_dbc_path)]),
        ],
        cyclic_enabled={"EngineData": True, "ChassisStatus": True},
        signal_overrides={"EngineData": {"EngineSpeed": 1200.0}},
        backend="null",
    )
    session = Session.from_scenario(scenario)
    session.tick(0.0)
    assert session.runtimes["powertrain"].status["EngineData"].tx_count == 1
    assert session.runtimes["chassis"].status["ChassisStatus"].tx_count == 1
    assert session.runtimes["powertrain"].status["EngineData"].color in {"green", "yellow", "red", "gray"}


def test_asc_logs_can_and_canfd(tmp_path: Path):
    path = tmp_path / "trace.asc"
    log = AscLogger(path)
    log.write(CanFrame(arbitration_id=0x100, data=bytes(8), is_fd=False, channel="1", timestamp=0.01), "Tx")
    log.write(
        CanFrame(arbitration_id=0x300, data=bytes(16), is_fd=True, bitrate_switch=True, channel="2", timestamp=0.02),
        "Rx",
    )
    log.close()
    text = path.read_text(encoding="utf-8")
    assert "100" in text
    assert "300" in text
    assert "BRS=" in text


def test_uds_read_did_sweep():
    assert read_did_request(0xF190) == bytes([0x22, 0xF1, 0x90])
    frames = did_sweep_frames([0xF190, 0xF187], request_id=0x7E0)
    assert len(frames) == 2
    assert frames[0].data[0] == 3
    assert frames[0].data[1:4] == bytes([0x22, 0xF1, 0x90])
    assert frames[0].arbitration_id == 0x7E0
