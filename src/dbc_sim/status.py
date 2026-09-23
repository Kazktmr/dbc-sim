"""Per-message send/receive status and the color language used in the UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Health(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    FAULT = "fault"
    IDLE = "idle"


COLOR = {
    Health.HEALTHY: "green",
    Health.WARNING: "yellow",
    Health.FAULT: "red",
    Health.IDLE: "gray",
}


@dataclass
class MessageStatus:
    name: str
    frame_id: int
    channel: str
    tx_count: int = 0
    rx_count: int = 0
    last_tx_s: float | None = None
    last_rx_s: float | None = None
    e2e_ok: bool = True
    timed_out: bool = False
    last_error: str = ""

    @property
    def health(self) -> Health:
        if self.last_error or self.timed_out or not self.e2e_ok:
            return Health.FAULT
        if self.tx_count == 0 and self.rx_count == 0:
            return Health.IDLE
        return Health.HEALTHY

    @property
    def color(self) -> str:
        return COLOR[self.health]


def signal_health(value: float, minimum: float | None, maximum: float | None) -> Health:
    if minimum is None or maximum is None:
        return Health.HEALTHY
    if value < minimum or value > maximum:
        return Health.FAULT
    span = maximum - minimum
    if span <= 0:
        return Health.HEALTHY
    if value <= minimum + 0.02 * span or value >= maximum - 0.02 * span:
        return Health.WARNING
    return Health.HEALTHY
