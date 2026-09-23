"""Optional Vector-style ASC logger. Default format when logging is on."""

from __future__ import annotations

from pathlib import Path

from dbc_sim.frames import CanFrame


class AscLogger:
    def __init__(self, path: str | Path, date_line: str = "Tue Sep 22 05:31:00 pm 2026") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self._fh.write(f"date {date_line}\n")
        self._fh.write("base hex  timestamps absolute\n")
        self._fh.write("no internal events logged\n")
        self._fh.write("// version 7.5.0\n")

    def write(self, frame: CanFrame, direction: str = "Tx") -> None:
        ts = 0.0 if frame.timestamp is None else frame.timestamp
        ch = frame.channel or "1"
        ident = f"{frame.arbitration_id:X}x" if frame.is_extended_id else f"{frame.arbitration_id:X}"
        dlc = len(frame.data)
        payload = frame.hex_data()
        if frame.is_fd:
            brs = "1" if frame.bitrate_switch else "0"
            line = f"{ts:10.6f} {ch}  {ident}             {direction}   d {dlc} {payload}  BRS={brs}  ESI=0\n"
        else:
            line = f"{ts:10.6f} {ch}  {ident}             {direction}   d {dlc} {payload}\n"
        self._fh.write(line)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
