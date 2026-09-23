"""Realtime session runner: paced ticks, pause, edits, rolling decode history."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from dbc_sim.frames import CanFrame
from dbc_sim.scheduler import ChannelRuntime
from dbc_sim.session import Session
from dbc_sim.status import signal_health


def _round_value(value: float) -> float:
    if abs(value) >= 100:
        return round(value, 2)
    if abs(value) >= 1:
        return round(value, 3)
    return round(value, 5)


class LiveEngine:
    """Owns a Session and exposes a thread-safe snapshot for the browser."""

    def __init__(
        self,
        session: Session,
        history: int = 80,
        step_s: float = 0.001,
        seconds: float | None = None,
    ) -> None:
        self.session = session
        self.history = history
        self.step_s = step_s
        self.seconds = seconds
        self.paused = False
        self.running = False
        self.sim_s = 0.0
        self.frames: deque[dict[str, Any]] = deque(maxlen=history)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._seq = 0
        self.active_channels = list(session.runtimes)
        self.last_decode: dict[tuple[str, str], dict[str, float]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, name="dbc-sim-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def pause(self) -> None:
        with self._lock:
            self.paused = True

    def resume(self) -> None:
        with self._lock:
            self.paused = False

    def set_active_channels(self, names: list[str]) -> None:
        known = set(self.session.runtimes)
        picked = [n for n in names if n in known]
        if not picked:
            raise ValueError(f"no matching channels in {sorted(known)}")
        with self._lock:
            self.active_channels = picked

    def set_signal(self, channel: str, message: str, signal: str, value: float) -> None:
        rt = self._runtime(channel)
        job = rt.jobs.get(message)
        if job is None:
            job = rt.add_cyclic(message)
        msg = job.message
        sig = msg.signal(signal)
        job.values[signal] = float(value)
        if sig.minimum is not None and job.values[signal] < sig.minimum:
            job.values[signal] = sig.minimum
        if sig.maximum is not None and job.values[signal] > sig.maximum:
            job.values[signal] = sig.maximum

    def set_e2e(self, channel: str, message: str, **faults: bool) -> None:
        rt = self._runtime(channel)
        job = rt.jobs.get(message)
        if job is None:
            job = rt.add_cyclic(message)
        allowed = {"fault_crc", "fault_freeze_counter", "fault_skip_counter"}
        for key, val in faults.items():
            if key not in allowed:
                raise ValueError(f"unknown e2e field {key}")
            setattr(job.e2e, key, bool(val))

    def set_cyclic(self, channel: str, message: str, enabled: bool) -> None:
        rt = self._runtime(channel)
        job = rt.jobs.get(message)
        if job is None:
            job = rt.add_cyclic(message)
        job.enabled = bool(enabled)

    def send_once(self, channel: str, message: str) -> None:
        rt = self._runtime(channel)
        frame = rt.send_event(message)
        with self._lock:
            self._record(rt, frame)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            channels = [self._channel_view(name) for name in self.session.runtimes]
            frames = list(self.frames)
            return {
                "sim_s": round(self.sim_s, 3),
                "paused": self.paused,
                "running": self.running,
                "backend": self.session.backend,
                "active_channels": list(self.active_channels),
                "available_channels": list(self.session.runtimes),
                "channels": channels,
                "frames": frames,
                "seq": self._seq,
            }

    def _runtime(self, channel: str) -> ChannelRuntime:
        try:
            return self.session.runtimes[channel]
        except KeyError as exc:
            raise ValueError(f"unknown channel {channel!r}") from exc

    def _loop(self) -> None:
        origin = time.perf_counter()
        sim = 0.0
        while self.running:
            if self.seconds is not None and sim >= self.seconds:
                self.running = False
                break
            with self._lock:
                paused = self.paused
                active = list(self.active_channels)
            if not paused:
                frames_by_rt: list[tuple[ChannelRuntime, list[CanFrame]]] = []
                for name in active:
                    rt = self.session.runtimes.get(name)
                    if rt is None:
                        continue
                    sent = rt.tick(sim)
                    frames_by_rt.append((rt, sent))
                    if self.session.logger:
                        for frame in sent:
                            self.session.logger.write(frame, "Tx")
                with self._lock:
                    self.sim_s = sim
                    for rt, sent in frames_by_rt:
                        for frame in sent:
                            self._record(rt, frame)
                    self._trim_null_buses()
                sim += self.step_s
            target = origin + sim
            delay = target - time.perf_counter()
            if paused:
                time.sleep(0.05)
            elif delay > 0:
                time.sleep(min(delay, 0.05))
            elif delay < -0.25:
                origin = time.perf_counter() - sim

    def _record(self, rt: ChannelRuntime, frame: CanFrame) -> None:
        try:
            msg = rt.db.message_by_id(frame.arbitration_id)
            raw_decoded = msg.decode(frame.data)
            decoded = {name: _round_value(val) for name, val in raw_decoded.items()}
            name = msg.name
        except KeyError:
            decoded = {}
            name = f"0x{frame.arbitration_id:03X}"
        self._seq += 1
        row = {
            "seq": self._seq,
            "t": round(frame.timestamp or self.sim_s, 4),
            "channel": frame.channel or rt.config.name,
            "id": frame.arbitration_id,
            "id_hex": f"0x{frame.arbitration_id:03X}",
            "name": name,
            "hex": frame.hex_data(),
            "fd": frame.is_fd,
            "len": len(frame.data),
            "signals": decoded,
        }
        self.frames.append(row)
        self.last_decode[(rt.config.name, name)] = decoded

    def _trim_null_buses(self) -> None:
        for rt in self.session.runtimes.values():
            tx = getattr(rt.bus, "tx", None)
            if isinstance(tx, list) and len(tx) > 400:
                del tx[:-80]
            rx = getattr(rt.bus, "_rx", None)
            if isinstance(rx, list) and len(rx) > 80:
                del rx[:]

    def _channel_view(self, name: str) -> dict[str, Any]:
        rt = self.session.runtimes[name]
        messages = []
        for msg in rt.db.messages:
            st = rt.status[msg.name]
            job = rt.jobs.get(msg.name)
            values = dict(job.values) if job else {}
            last = self.last_decode.get((name, msg.name), {})
            signals = []
            for sig in msg.signals:
                current = values.get(sig.name, last.get(sig.name, 0.0))
                health = signal_health(current, sig.minimum, sig.maximum)
                signals.append(
                    {
                        "name": sig.name,
                        "value": _round_value(float(current)),
                        "unit": sig.unit,
                        "min": sig.minimum,
                        "max": sig.maximum,
                        "health": health.value,
                    }
                )
            e2e = {
                "profile": msg.e2e_profile,
                "fault_crc": bool(job.e2e.fault_crc) if job else False,
                "fault_freeze_counter": bool(job.e2e.fault_freeze_counter) if job else False,
                "fault_skip_counter": bool(job.e2e.fault_skip_counter) if job else False,
            }
            age = None
            if st.last_tx_s is not None:
                age = round(max(0.0, self.sim_s - st.last_tx_s), 3)
            messages.append(
                {
                    "name": msg.name,
                    "frame_id": msg.frame_id,
                    "id_hex": f"0x{msg.frame_id:03X}",
                    "fd": msg.is_fd,
                    "length": msg.length,
                    "cycle_ms": msg.cycle_time_ms,
                    "tx_count": st.tx_count,
                    "rx_count": st.rx_count,
                    "last_tx_s": st.last_tx_s,
                    "tx_age_s": age,
                    "e2e_ok": st.e2e_ok,
                    "health": st.health.value,
                    "color": st.color,
                    "last_error": st.last_error,
                    "cyclic": bool(job.enabled) if job else False,
                    "has_job": job is not None,
                    "e2e": e2e,
                    "signals": signals,
                }
            )
        return {
            "name": name,
            "kind": rt.config.kind.value,
            "active": name in self.active_channels,
            "messages": messages,
        }
