"""Pluggable E2E. Default profile is AUTOSAR Profile 1 / 11A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

def _build_crc8_sae_j1850_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x1D) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        table.append(crc)
    return table


_CRC8_SAE_J1850_TABLE = _build_crc8_sae_j1850_table()


def crc8_sae_j1850(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc = _CRC8_SAE_J1850_TABLE[crc ^ byte]
    return crc ^ 0xFF


@dataclass
class E2EState:
    profile: str
    counter: int = 0
    last_ok: bool = True
    fault_crc: bool = False
    fault_freeze_counter: bool = False
    fault_skip_counter: bool = False


class E2EProfile(Protocol):
    name: str

    def protect(self, payload: bytearray, data_id: int, state: E2EState) -> bytes: ...

    def check(self, payload: bytes, data_id: int, last_counter: int | None) -> tuple[bool, int]: ...


class Profile11A:
    """AUTOSAR E2E Profile 1 (11A).

    Layout assumed for this tool:
      byte 0     = CRC-8 SAE J1850
      byte 1     = counter in low nibble (0..14, 0xF reserved)
      bytes 2..  = application payload

    CRC covers DataId high, DataId low, then payload[1:].
    """

    name = "11A"
    COUNTER_MAX = 14

    def protect(self, payload: bytearray, data_id: int, state: E2EState) -> bytes:
        if len(payload) < 2:
            raise ValueError("E2E 11A needs at least 2 bytes")
        if not state.fault_freeze_counter:
            step = 2 if state.fault_skip_counter else 1
            state.counter = (state.counter + step) % (self.COUNTER_MAX + 1)
        payload[1] = (payload[1] & 0xF0) | (state.counter & 0x0F)
        crc = self._crc(payload, data_id)
        if state.fault_crc:
            crc ^= 0xFF
        payload[0] = crc
        return bytes(payload)

    def check(self, payload: bytes, data_id: int, last_counter: int | None) -> tuple[bool, int]:
        if len(payload) < 2:
            return False, 0
        got = payload[0]
        expect = self._crc(payload, data_id)
        counter = payload[1] & 0x0F
        crc_ok = got == expect
        counter_ok = True
        if last_counter is not None:
            nxt = (last_counter + 1) % (self.COUNTER_MAX + 1)
            counter_ok = counter == nxt
        return crc_ok and counter_ok, counter

    def _crc(self, payload: bytes, data_id: int) -> int:
        body = bytes([(data_id >> 8) & 0xFF, data_id & 0xFF]) + bytes(payload[1:])
        return crc8_sae_j1850(body)


class ProfilePassthrough:
    name = "none"

    def protect(self, payload: bytearray, data_id: int, state: E2EState) -> bytes:
        return bytes(payload)

    def check(self, payload: bytes, data_id: int, last_counter: int | None) -> tuple[bool, int]:
        return True, 0


_REGISTRY: dict[str, E2EProfile] = {
    "11A": Profile11A(),
    "P01": Profile11A(),
    "profile1": Profile11A(),
    "none": ProfilePassthrough(),
}


def get_profile(name: str | None) -> E2EProfile:
    if not name:
        return _REGISTRY["11A"]
    key = name.strip()
    if key not in _REGISTRY:
        raise KeyError(f"Unknown E2E profile {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def register_profile(profile: E2EProfile) -> None:
    _REGISTRY[profile.name] = profile
