from dbc_sim.dbc.loader import load_dbc
from dbc_sim.frames import BusKind, CanFrame, ChannelConfig


def test_sample_dbc_loads_automotive_layout(demo_dbc_path):
    db = load_dbc(demo_dbc_path)
    names = {m.name for m in db.messages}
    assert {"EngineData", "VehicleSpeed", "ChassisStatus", "LampCommand", "DiagRequest", "DiagResponse"} <= names
    engine = db.message_by_name("EngineData")
    assert engine.frame_id == 0x100
    assert engine.length == 8
    assert engine.cycle_time_ms == 10
    assert engine.e2e_profile == "11A"
    assert engine.e2e_data_id == 291
    chassis = db.message_by_name("ChassisStatus")
    assert chassis.is_fd
    assert chassis.length == 16
    assert db.message_by_name("LampCommand").cycle_time_ms is None


def test_engine_speed_roundtrip(demo_dbc_path):
    engine = load_dbc(demo_dbc_path).message_by_name("EngineData")
    payload = engine.encode({"EngineSpeed": 2400.0, "CoolantTemp": 90.0, "AcceleratorPedal": 20.0, "EngineRunning": 1})
    decoded = engine.decode(payload)
    assert decoded["EngineSpeed"] == 2400.0
    assert decoded["CoolantTemp"] == 90.0
    assert decoded["EngineRunning"] == 1.0


def test_classic_and_fd_frame_limits():
    CanFrame(arbitration_id=0x100, data=b"\x00" * 8, is_fd=False)
    CanFrame(arbitration_id=0x300, data=b"\x00" * 16, is_fd=True)
    try:
        CanFrame(arbitration_id=0x100, data=b"\x00" * 16, is_fd=False)
        raise AssertionError("classic CAN should reject 16-byte payload")
    except ValueError:
        pass


def test_channel_kind_clears_data_bitrate_on_classic():
    ch = ChannelConfig(name="pt", kind=BusKind.CAN, data_bitrate=2_000_000)
    assert ch.data_bitrate is None
    fd = ChannelConfig(name="ch", kind=BusKind.CANFD)
    assert fd.data_bitrate == 2_000_000
