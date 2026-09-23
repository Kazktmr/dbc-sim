from dbc_sim.dbc.loader import load_dbc
from dbc_sim.e2e import E2EState, crc8_sae_j1850, get_profile
from dbc_sim.frames import BusKind, CanFrame, ChannelConfig
from dbc_sim.hardware import NullBus
from dbc_sim.scheduler import ChannelRuntime
from dbc_sim.status import Health, signal_health


def test_crc8_sae_j1850_check_vector():
    assert crc8_sae_j1850(b"123456789") == 0x4B


def test_profile_11a_protect_and_check():
    profile = get_profile("11A")
    state = E2EState(profile="11A")
    first = bytearray(8)
    out1 = profile.protect(first, data_id=291, state=state)
    ok, counter = profile.check(out1, 291, last_counter=None)
    assert ok
    assert counter == state.counter
    second = bytearray(8)
    out2 = profile.protect(second, data_id=291, state=state)
    ok2, counter2 = profile.check(out2, 291, last_counter=counter)
    assert ok2
    assert counter2 == (counter + 1) % 15


def test_crc_fault_is_detected():
    profile = get_profile("11A")
    state = E2EState(profile="11A", fault_crc=True)
    bad = profile.protect(bytearray(8), data_id=291, state=state)
    ok, _ = profile.check(bad, 291, last_counter=None)
    assert ok is False


def test_scheduler_sends_classic_and_fd_together(demo_dbc_path):
    db = load_dbc(demo_dbc_path)
    can_cfg = ChannelConfig(name="powertrain", kind=BusKind.CAN)
    fd_cfg = ChannelConfig(name="chassis", kind=BusKind.CANFD)
    can_bus = NullBus(can_cfg)
    fd_bus = NullBus(fd_cfg)
    can_bus.open()
    fd_bus.open()
    pt = ChannelRuntime(can_cfg, db, can_bus)
    ch = ChannelRuntime(fd_cfg, db, fd_bus)
    pt.add_cyclic("EngineData", {"EngineSpeed": 800.0, "EngineRunning": 1})
    ch.add_cyclic("ChassisStatus", {"WheelFL": 40.0})
    pt.tick(0.0)
    ch.tick(0.0)
    assert can_bus.tx[0].is_fd is False
    assert can_bus.tx[0].arbitration_id == 0x100
    assert len(can_bus.tx[0].data) == 8
    assert fd_bus.tx[0].is_fd is True
    assert fd_bus.tx[0].arbitration_id == 0x300
    assert len(fd_bus.tx[0].data) == 16


def test_classic_channel_rejects_fd_frame():
    cfg = ChannelConfig(name="pt", kind=BusKind.CAN)
    bus = NullBus(cfg)
    bus.open()
    try:
        bus.send(CanFrame(arbitration_id=1, data=b"\x00" * 8, is_fd=True))
        raise AssertionError("should refuse FD on classic channel")
    except Exception as exc:
        assert "classic CAN" in str(exc)


def test_signal_health_colors():
    assert signal_health(50, 0, 100) is Health.HEALTHY
    assert signal_health(1, 0, 100) is Health.WARNING
    assert signal_health(120, 0, 100) is Health.FAULT
