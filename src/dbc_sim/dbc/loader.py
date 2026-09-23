"""Load raw .dbc text. Uses cantools when installed, else a focused subset parser."""

from __future__ import annotations

import re
from pathlib import Path

from dbc_sim.dbc.model import Database, Message, Signal

_BO = re.compile(
    r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)",
)
_SG = re.compile(
    r"^\s*SG_\s+(\w+)\s*(?:[mM]\d*)?\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*"
    r"\(([^,]+),([^)]+)\)\s*\[([^|]*)\|([^\]]*)\]\s*\"([^\"]*)\"\s*(.*)$"
)
_BA_CYCLE = re.compile(
    r'^BA_\s+"GenMsgCycleTime"\s+BO_\s+(\d+)\s+(\d+)\s*;'
)
_BA_FD = re.compile(
    r'^BA_\s+"VFrameFormat"\s+BO_\s+(\d+)\s+(\d+)\s*;'
)
_CM_BO = re.compile(r'^CM_\s+BO_\s+(\d+)\s+"([^"]*)"\s*;')
_VAL_E2E = re.compile(
    r'^BA_\s+"E2EProfile"\s+BO_\s+(\d+)\s+"([^"]+)"\s*;'
)
_VAL_DATA_ID = re.compile(
    r'^BA_\s+"E2EDataId"\s+BO_\s+(\d+)\s+(\d+)\s*;'
)


def load_dbc(path: str | Path) -> Database:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return _load_cantools(path, text)
    except Exception:
        return _load_subset(path, text)


def _load_cantools(path: Path, text: str) -> Database:
    import cantools

    raw = cantools.database.load_string(text)
    messages: list[Message] = []
    for msg in raw.messages:
        signals = [
            Signal(
                name=s.name,
                start_bit=s.start,
                length=s.length,
                is_little_endian=s.byte_order == "little_endian",
                is_signed=s.is_signed,
                scale=float(s.scale),
                offset=float(s.offset),
                minimum=s.minimum,
                maximum=s.maximum,
                unit=s.unit or "",
                receivers=tuple(s.receivers or ()),
            )
            for s in msg.signals
        ]
        cycle = None
        if msg.cycle_time is not None:
            cycle = int(msg.cycle_time)
        messages.append(
            Message(
                name=msg.name,
                frame_id=msg.frame_id,
                length=msg.length,
                sender=msg.senders[0] if msg.senders else "Vector__XXX",
                cycle_time_ms=cycle,
                is_extended_id=msg.is_extended_frame,
                is_fd=bool(getattr(msg, "is_fd", False)),
                comment=msg.comment or "",
                signals=signals,
            )
        )
    db = Database(
        version=getattr(raw, "version", "") or "",
        nodes=list(raw.nodes) if raw.nodes else [],
        messages=messages,
        source_path=str(path),
    )
    _apply_attributes(db, text)
    return db


def _load_subset(path: Path, text: str) -> Database:
    nodes: list[str] = []
    messages: list[Message] = []
    current: Message | None = None
    version = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("VERSION"):
            m = re.search(r'"([^"]*)"', line)
            version = m.group(1) if m else ""
            continue
        if line.startswith("BU_:"):
            nodes = [n for n in line[4:].split() if n]
            continue
        bo = _BO.match(line)
        if bo:
            if current:
                messages.append(current)
            frame_id = int(bo.group(1))
            current = Message(
                name=bo.group(2),
                frame_id=frame_id & 0x7FFFFFFF,
                length=int(bo.group(3)),
                sender=bo.group(4),
                is_extended_id=bool(frame_id & 0x80000000),
            )
            continue
        sg = _SG.match(raw_line)
        if sg and current is not None:
            receivers = tuple(s for s in sg.group(11).split() if s)
            current.signals.append(
                Signal(
                    name=sg.group(1),
                    start_bit=int(sg.group(2)),
                    length=int(sg.group(3)),
                    is_little_endian=sg.group(4) == "1",
                    is_signed=sg.group(5) == "-",
                    scale=float(sg.group(6)),
                    offset=float(sg.group(7)),
                    minimum=_opt_float(sg.group(8)),
                    maximum=_opt_float(sg.group(9)),
                    unit=sg.group(10),
                    receivers=receivers,
                )
            )
    if current:
        messages.append(current)

    db = Database(version=version, nodes=nodes, messages=messages, source_path=str(path))
    _apply_attributes(db, text)
    return db


def _apply_attributes(db: Database, text: str) -> None:
    by_id = {m.frame_id: m for m in db.messages}
    for line in text.splitlines():
        line = line.strip()
        m = _BA_CYCLE.match(line)
        if m and int(m.group(1)) in by_id:
            by_id[int(m.group(1))].cycle_time_ms = int(m.group(2))
        m = _BA_FD.match(line)
        if m and int(m.group(1)) in by_id:
            by_id[int(m.group(1))].is_fd = int(m.group(2)) >= 14
        m = _CM_BO.match(line)
        if m and int(m.group(1)) in by_id:
            by_id[int(m.group(1))].comment = m.group(2)
        m = _VAL_E2E.match(line)
        if m and int(m.group(1)) in by_id:
            by_id[int(m.group(1))].e2e_profile = m.group(2)
        m = _VAL_DATA_ID.match(line)
        if m and int(m.group(1)) in by_id:
            by_id[int(m.group(1))].e2e_data_id = int(m.group(2))


def _opt_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    return float(text)
