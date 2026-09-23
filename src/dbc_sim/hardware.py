"""Swappable physical bus. Tests use NullBus; PCAN/Vector plug in later via python-can."""

from __future__ import annotations

import time
from typing import Protocol

from dbc_sim.frames import BusKind, CanFrame, ChannelConfig


class BusError(RuntimeError):
    pass


_TRANSIENT_TX = ("queue", "full", "buffer", "xmtfull", "qxmtfull", "no buffer space")


def _is_transient_tx_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in _TRANSIENT_TX)


class Bus(Protocol):
    name: str
    kind: BusKind

    def open(self) -> None: ...

    def close(self) -> None: ...

    def send(self, frame: CanFrame) -> None: ...

    def recv(self, timeout: float = 0.0) -> CanFrame | None: ...


class NullBus:
    """In-process loopback used by unit tests and dry runs."""

    def __init__(self, config: ChannelConfig) -> None:
        self.config = config
        self.name = config.name
        self.kind = config.kind
        self.tx: list[CanFrame] = []
        self._rx: list[CanFrame] = []
        self.opened = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def send(self, frame: CanFrame) -> None:
        if not self.opened:
            raise BusError(f"channel {self.name} is closed")
        if self.kind is BusKind.CAN and frame.is_fd:
            raise BusError(f"channel {self.name} is classic CAN; refused FD frame 0x{frame.arbitration_id:X}")
        if self.kind is BusKind.CAN and len(frame.data) > 8:
            raise BusError("classic CAN payload too long")
        self.tx.append(frame)
        self._rx.append(frame)

    def recv(self, timeout: float = 0.0) -> CanFrame | None:
        if not self._rx:
            return None
        return self._rx.pop(0)

    def inject(self, frame: CanFrame) -> None:
        self._rx.append(frame)


def open_bus(config: ChannelConfig, backend: str = "null") -> Bus:
    backend = backend.lower()
    if backend in {"null", "loopback", "dry-run"}:
        bus = NullBus(config)
        bus.open()
        return bus
    if backend in {"pcan", "vector", "socketcan"}:
        return _open_python_can(config, backend)
    raise BusError(f"unknown backend {backend!r}")


def _open_python_can(config: ChannelConfig, backend: str) -> Bus:
    try:
        import can  # type: ignore
    except ImportError as exc:
        raise BusError("python-can is not installed. pip install -e .") from exc

    kwargs: dict = {
        "interface": backend,
        "channel": config.channel,
        "bitrate": config.bitrate,
        "fd": config.kind is BusKind.CANFD,
    }
    if config.kind is BusKind.CANFD and config.data_bitrate:
        kwargs["data_bitrate"] = config.data_bitrate
    try:
        bus = can.Bus(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise BusError(
            f"could not open {backend} {config.channel}. "
            "Install the vendor driver and confirm the interface name."
        ) from exc
    return PythonCanBus(config, bus)


class PythonCanBus:
    """python-can wrapper with TX retry on a full hardware queue."""

    def __init__(self, config: ChannelConfig, inner) -> None:
        self.config = config
        self.name = config.name
        self.kind = config.kind
        self._inner = inner
        self.tx_retries = 0
        self.tx_dropped = 0

    def open(self) -> None:
        return None

    def close(self) -> None:
        try:
            self._inner.shutdown()
        except Exception as exc:  # noqa: BLE001
            raise BusError(f"failed to close {self.name}: {exc}") from exc

    def send(self, frame: CanFrame) -> None:
        import can

        msg = can.Message(
            arbitration_id=frame.arbitration_id,
            data=frame.data,
            is_extended_id=frame.is_extended_id,
            is_fd=frame.is_fd,
            bitrate_switch=frame.bitrate_switch,
            is_remote_frame=frame.is_remote_frame,
        )
        last_exc: Exception | None = None
        for attempt in range(8):
            try:
                self._inner.send(msg)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not _is_transient_tx_error(exc):
                    raise BusError(str(exc)) from exc
                self.tx_retries += 1
                time.sleep(0.002 * (attempt + 1))
        self.tx_dropped += 1
        raise BusError(
            f"transmission queue full on {self.name} after retries; "
            f"dropped frame 0x{frame.arbitration_id:X}"
        ) from last_exc

    def recv(self, timeout: float = 0.0) -> CanFrame | None:
        try:
            msg = self._inner.recv(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise BusError(f"recv failed on {self.name}: {exc}") from exc
        if msg is None:
            return None
        return CanFrame(
            arbitration_id=msg.arbitration_id,
            data=bytes(msg.data),
            is_extended_id=msg.is_extended_id,
            is_fd=bool(getattr(msg, "is_fd", False)),
            bitrate_switch=bool(getattr(msg, "bitrate_switch", False)),
            is_remote_frame=msg.is_remote_frame,
            channel=self.name,
            timestamp=getattr(msg, "timestamp", None),
        )
