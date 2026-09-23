"""Classic CAN and CAN FD frame models used everywhere in the tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BusKind(str, Enum):
    CAN = "can"
    CANFD = "canfd"


@dataclass(frozen=True)
class CanFrame:
    arbitration_id: int
    data: bytes
    is_extended_id: bool = False
    is_fd: bool = False
    bitrate_switch: bool = False
    is_remote_frame: bool = False
    channel: str = ""
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if self.is_fd:
            if len(self.data) > 64:
                raise ValueError("CAN FD payload cannot exceed 64 bytes")
        elif len(self.data) > 8:
            raise ValueError("Classic CAN payload cannot exceed 8 bytes")

    @property
    def dlc_hint(self) -> int:
        return len(self.data)

    def hex_data(self) -> str:
        return self.data.hex(" ").upper()


@dataclass
class ChannelConfig:
    name: str
    kind: BusKind
    interface: str = "pcan"
    channel: str = "PCAN_USBBUS1"
    bitrate: int = 500_000
    data_bitrate: int | None = 2_000_000
    fd_iso: bool = True
    dbc_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind is BusKind.CAN:
            self.data_bitrate = None
        elif self.data_bitrate is None:
            self.data_bitrate = 2_000_000
