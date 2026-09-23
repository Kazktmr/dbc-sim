"""Minimal UDS: Read DID (0x22) request builder and a sweep helper."""

from __future__ import annotations

from dbc_sim.frames import CanFrame


def read_did_request(did: int, functional: bool = False) -> bytes:
    if not 0 <= did <= 0xFFFF:
        raise ValueError("DID must be 0x0000-0xFFFF")
    return bytes([0x22, (did >> 8) & 0xFF, did & 0xFF])


def wrap_iso_tp_single(payload: bytes) -> bytes:
    if len(payload) > 7:
        raise ValueError("v1 sweep uses ISO-TP single frames only (payload <= 7)")
    return bytes([len(payload)]) + payload + bytes(8 - 1 - len(payload))


def did_sweep_frames(
    dids: list[int],
    request_id: int = 0x7E0,
    channel: str = "diag",
    is_fd: bool = False,
) -> list[CanFrame]:
    frames: list[CanFrame] = []
    for did in dids:
        payload = wrap_iso_tp_single(read_did_request(did))
        frames.append(
            CanFrame(
                arbitration_id=request_id,
                data=payload,
                is_fd=is_fd,
                bitrate_switch=is_fd,
                channel=channel,
            )
        )
    return frames
