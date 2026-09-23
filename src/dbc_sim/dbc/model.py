"""DBC message and signal model plus pack/unpack."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signal:
    name: str
    start_bit: int
    length: int
    is_little_endian: bool
    is_signed: bool
    scale: float = 1.0
    offset: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""
    receivers: tuple[str, ...] = ()

    def physical_to_raw(self, physical: float) -> int:
        raw = int(round((physical - self.offset) / self.scale))
        max_unsigned = (1 << self.length) - 1
        if self.is_signed:
            min_s = -(1 << (self.length - 1))
            max_s = (1 << (self.length - 1)) - 1
            return max(min_s, min(max_s, raw))
        return max(0, min(max_unsigned, raw))

    def raw_to_physical(self, raw: int) -> float:
        if self.is_signed and raw >= (1 << (self.length - 1)):
            raw -= 1 << self.length
        return raw * self.scale + self.offset


@dataclass
class Message:
    name: str
    frame_id: int
    length: int
    sender: str = "Vector__XXX"
    cycle_time_ms: int | None = None
    is_extended_id: bool = False
    is_fd: bool = False
    comment: str = ""
    signals: list[Signal] = field(default_factory=list)
    e2e_profile: str = "11A"
    e2e_data_id: int = 0

    def signal(self, name: str) -> Signal:
        for sig in self.signals:
            if sig.name == name:
                return sig
        raise KeyError(name)

    def encode(self, values: dict[str, float]) -> bytes:
        raw_map: dict[str, int] = {}
        for sig in self.signals:
            if sig.name in values:
                raw_map[sig.name] = sig.physical_to_raw(values[sig.name])
            else:
                raw_map[sig.name] = 0
        return pack_signals(self.length, self.signals, raw_map)

    def decode(self, data: bytes) -> dict[str, float]:
        raw_map = unpack_signals(data, self.signals)
        return {name: self.signal(name).raw_to_physical(raw) for name, raw in raw_map.items()}


@dataclass
class Database:
    version: str = ""
    nodes: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    source_path: str = ""

    def message_by_name(self, name: str) -> Message:
        for msg in self.messages:
            if msg.name == name:
                return msg
        raise KeyError(name)

    def message_by_id(self, frame_id: int) -> Message:
        for msg in self.messages:
            if msg.frame_id == frame_id:
                return msg
        raise KeyError(frame_id)

    def ids(self) -> set[int]:
        return {m.frame_id for m in self.messages}


def pack_signals(length: int, signals: list[Signal], raw_values: dict[str, int]) -> bytes:
    buf = bytearray(length)
    for sig in signals:
        raw = raw_values.get(sig.name, 0)
        mask = (1 << sig.length) - 1
        raw &= mask
        if sig.is_little_endian:
            _insert_intel(buf, sig.start_bit, sig.length, raw)
        else:
            _insert_motorola(buf, sig.start_bit, sig.length, raw)
    return bytes(buf)


def unpack_signals(data: bytes, signals: list[Signal]) -> dict[str, int]:
    out: dict[str, int] = {}
    for sig in signals:
        if sig.is_little_endian:
            raw = _extract_intel(data, sig.start_bit, sig.length)
        else:
            raw = _extract_motorola(data, sig.start_bit, sig.length)
        out[sig.name] = raw
    return out


def _insert_intel(buf: bytearray, start: int, length: int, value: int) -> None:
    for i in range(length):
        if value & (1 << i):
            bit = start + i
            buf[bit // 8] |= 1 << (bit % 8)


def _extract_intel(data: bytes, start: int, length: int) -> int:
    value = 0
    for i in range(length):
        bit = start + i
        if bit // 8 >= len(data):
            break
        if data[bit // 8] & (1 << (bit % 8)):
            value |= 1 << i
    return value


def _insert_motorola(buf: bytearray, start: int, length: int, value: int) -> None:
    bit = start
    for i in range(length - 1, -1, -1):
        if value & (1 << i):
            buf[bit // 8] |= 1 << (bit % 8)
        if bit % 8 == 0:
            bit += 15
        else:
            bit -= 1


def _extract_motorola(data: bytes, start: int, length: int) -> int:
    value = 0
    bit = start
    for i in range(length - 1, -1, -1):
        if bit // 8 < len(data) and data[bit // 8] & (1 << (bit % 8)):
            value |= 1 << i
        if bit % 8 == 0:
            bit += 15
        else:
            bit -= 1
    return value
