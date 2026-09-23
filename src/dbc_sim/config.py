"""Scenario persistence. JSON so a coworker can reload the same session."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dbc_sim.frames import BusKind, ChannelConfig


@dataclass
class Scenario:
    channels: list[ChannelConfig] = field(default_factory=list)
    signal_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    cyclic_enabled: dict[str, bool] = field(default_factory=dict)
    e2e_faults: dict[str, dict[str, bool]] = field(default_factory=dict)
    logging_enabled: bool = False
    log_path: str = "traces/session.asc"
    backend: str = "null"

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "channels": [_channel_to_dict(ch) for ch in self.channels],
            "signal_overrides": self.signal_overrides,
            "cyclic_enabled": self.cyclic_enabled,
            "e2e_faults": self.e2e_faults,
            "logging_enabled": self.logging_enabled,
            "log_path": self.log_path,
            "backend": self.backend,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        channels = [_channel_from_dict(item) for item in data.get("channels", [])]
        return cls(
            channels=channels,
            signal_overrides=data.get("signal_overrides", {}),
            cyclic_enabled=data.get("cyclic_enabled", {}),
            e2e_faults=data.get("e2e_faults", {}),
            logging_enabled=data.get("logging_enabled", False),
            log_path=data.get("log_path", "traces/session.asc"),
            backend=data.get("backend", "null"),
        )


def _channel_to_dict(ch: ChannelConfig) -> dict:
    d = asdict(ch)
    d["kind"] = ch.kind.value
    return d


def _channel_from_dict(d: dict) -> ChannelConfig:
    kind = d.get("kind", "can")
    return ChannelConfig(
        name=d["name"],
        kind=BusKind(kind),
        interface=d.get("interface", "pcan"),
        channel=d.get("channel", "PCAN_USBBUS1"),
        bitrate=int(d.get("bitrate", 500_000)),
        data_bitrate=d.get("data_bitrate"),
        fd_iso=bool(d.get("fd_iso", True)),
        dbc_paths=list(d.get("dbc_paths", [])),
    )
