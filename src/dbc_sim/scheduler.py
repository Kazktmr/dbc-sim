"""Cyclic and event transmitters that speak CAN and CAN FD on independent channels."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from dbc_sim.dbc.model import Database, Message
from dbc_sim.e2e import E2EState, get_profile
from dbc_sim.frames import BusKind, CanFrame, ChannelConfig
from dbc_sim.hardware import Bus, BusError
from dbc_sim.status import MessageStatus

log = logging.getLogger(__name__)


@dataclass
class TxJob:
    message: Message
    values: dict[str, float]
    cyclic: bool = True
    period_s: float = 0.01
    next_due_s: float = 0.0
    e2e: E2EState = field(default_factory=lambda: E2EState(profile="11A"))
    enabled: bool = True


class ChannelRuntime:
    def __init__(self, config: ChannelConfig, db: Database, bus: Bus) -> None:
        self.config = config
        self.db = db
        self.bus = bus
        self.jobs: dict[str, TxJob] = {}
        self.status: dict[str, MessageStatus] = {
            m.name: MessageStatus(name=m.name, frame_id=m.frame_id, channel=config.name)
            for m in db.messages
        }
        self._now = 0.0

    def add_cyclic(self, message_name: str, values: dict[str, float] | None = None) -> TxJob:
        msg = self.db.message_by_name(message_name)
        period_ms = msg.cycle_time_ms or 10
        job = TxJob(
            message=msg,
            values=dict(values or {}),
            cyclic=True,
            period_s=period_ms / 1000.0,
            e2e=E2EState(profile=msg.e2e_profile or "11A"),
        )
        self.jobs[message_name] = job
        return job

    def set_signal(self, message_name: str, signal_name: str, value: float) -> None:
        self.jobs[message_name].values[signal_name] = value

    def send_event(self, message_name: str) -> CanFrame:
        job = self.jobs.get(message_name)
        if job is None:
            job = self.add_cyclic(message_name)
            job.cyclic = False
        return self._transmit(job)

    def tick(self, now_s: float) -> list[CanFrame]:
        self._now = now_s
        sent: list[CanFrame] = []
        for job in self.jobs.values():
            if not job.enabled or not job.cyclic:
                continue
            if now_s + 1e-9 >= job.next_due_s:
                frame = self._transmit(job)
                if frame is not None:
                    sent.append(frame)
                job.next_due_s = now_s + job.period_s
        self._drain_rx(now_s)
        return sent

    def _transmit(self, job: TxJob) -> CanFrame | None:
        raw = bytearray(job.message.encode(job.values))
        profile = get_profile(job.e2e.profile)
        protected = profile.protect(raw, job.message.e2e_data_id, job.e2e)
        is_fd = job.message.is_fd or self.config.kind is BusKind.CANFD
        if self.config.kind is BusKind.CAN:
            is_fd = False
        frame = CanFrame(
            arbitration_id=job.message.frame_id,
            data=protected,
            is_extended_id=job.message.is_extended_id,
            is_fd=is_fd,
            bitrate_switch=is_fd,
            channel=self.config.name,
            timestamp=self._now,
        )
        try:
            self.bus.send(frame)
        except BusError as exc:
            st = self.status[job.message.name]
            st.last_error = str(exc)
            log.warning("TX failed on %s %s: %s", self.config.name, job.message.name, exc)
            return None
        st = self.status[job.message.name]
        st.tx_count += 1
        st.last_tx_s = self._now
        st.last_error = None
        return frame

    def _drain_rx(self, now_s: float) -> None:
        while True:
            frame = self.bus.recv(timeout=0.0)
            if frame is None:
                break
            try:
                msg = self.db.message_by_id(frame.arbitration_id)
            except KeyError:
                continue
            st = self.status[msg.name]
            st.rx_count += 1
            st.last_rx_s = now_s
            if msg.e2e_profile and msg.e2e_profile != "none":
                profile = get_profile(msg.e2e_profile)
                last = None
                job = self.jobs.get(msg.name)
                if job is not None:
                    last = (job.e2e.counter - 1) % 15
                ok, _ = profile.check(frame.data, msg.e2e_data_id, last)
                st.e2e_ok = ok
                if not ok:
                    st.last_error = "e2e"
            cycle = msg.cycle_time_ms or 0
            if cycle and st.last_rx_s is not None and st.last_tx_s is not None:
                pass
