"""One process, many channels: classic CAN and CAN FD at the same time."""

from __future__ import annotations

from pathlib import Path

from dbc_sim.config import Scenario
from dbc_sim.dbc.loader import load_dbc
from dbc_sim.dbc.model import Database, Message
from dbc_sim.frames import BusKind, ChannelConfig
from dbc_sim.hardware import Bus, open_bus
from dbc_sim.log_asc import AscLogger
from dbc_sim.scheduler import ChannelRuntime


def _fits_channel(msg: Message, kind: BusKind) -> bool:
    if kind is BusKind.CAN:
        return not msg.is_fd and msg.length <= 8
    return True


class Session:
    def __init__(self, backend: str = "null") -> None:
        self.backend = backend
        self.runtimes: dict[str, ChannelRuntime] = {}
        self.logger: AscLogger | None = None

    def add_channel(self, config: ChannelConfig, db: Database | None = None, bus: Bus | None = None) -> ChannelRuntime:
        if db is None:
            if not config.dbc_paths:
                raise ValueError(f"channel {config.name} has no DBC")
            db = load_dbc(config.dbc_paths[0])
            for extra in config.dbc_paths[1:]:
                other = load_dbc(extra)
                overlap = db.ids() & other.ids()
                if overlap:
                    raise ValueError(f"ID collision on {config.name}: {sorted(hex(i) for i in overlap)}")
                db.messages.extend(other.messages)
        if bus is None:
            bus = open_bus(config, self.backend)
        rt = ChannelRuntime(config, db, bus)
        self.runtimes[config.name] = rt
        return rt

    def tick(self, now_s: float) -> None:
        for rt in self.runtimes.values():
            frames = rt.tick(now_s)
            if self.logger:
                for frame in frames:
                    self.logger.write(frame, "Tx")

    def enable_logging(self, path: str | Path) -> None:
        self.logger = AscLogger(path)

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> Session:
        session = cls(backend=scenario.backend)
        for ch in scenario.channels:
            rt = session.add_channel(ch)
            known = {m.name: m for m in rt.db.messages}

            def ensure_job(name: str, runtime=rt, channel=ch) -> None:
                msg = known.get(name)
                if msg is None or not _fits_channel(msg, channel.kind):
                    return
                if name not in runtime.jobs:
                    runtime.add_cyclic(name)

            for msg_name, values in scenario.signal_overrides.items():
                ensure_job(msg_name)
                if msg_name in rt.jobs:
                    for sig, val in values.items():
                        rt.set_signal(msg_name, sig, val)
            for msg_name, enabled in scenario.cyclic_enabled.items():
                ensure_job(msg_name)
                if msg_name in rt.jobs:
                    rt.jobs[msg_name].enabled = enabled
            for msg_name, faults in scenario.e2e_faults.items():
                if msg_name in rt.jobs:
                    for key, val in faults.items():
                        setattr(rt.jobs[msg_name].e2e, key, val)
        if scenario.logging_enabled:
            session.enable_logging(scenario.log_path)
        return session
