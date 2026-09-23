"""CLI entry. Hardware TX comes online once a dongle is present; --backend null always works."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dbc_sim import __version__
from dbc_sim.dbc.loader import load_dbc
from dbc_sim.frames import BusKind, ChannelConfig
from dbc_sim.session import Session


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dbc-sim", description="Physical CAN / CAN-FD DBC simulator")
    p.add_argument("--version", action="version", version=f"dbc-sim {__version__}")
    sub = p.add_subparsers(dest="cmd")

    show = sub.add_parser("show-dbc", help="Print messages from a raw .dbc")
    show.add_argument("dbc", type=Path)

    run = sub.add_parser("run", help="Run a two-channel demo (classic CAN + CAN FD) on the null bus")
    run.add_argument("dbc", type=Path)
    run.add_argument("--seconds", type=float, default=0.05)
    run.add_argument("--backend", default="null")
    run.add_argument("--log", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "show-dbc":
        db = load_dbc(args.dbc)
        print(f"{args.dbc}  messages={len(db.messages)}  nodes={', '.join(db.nodes)}")
        for msg in db.messages:
            kind = "FD" if msg.is_fd else "CAN"
            cycle = f"{msg.cycle_time_ms}ms" if msg.cycle_time_ms else "event"
            print(f"  0x{msg.frame_id:03X}  {msg.name:20s}  {kind:3s}  {msg.length:2d}B  {cycle}  e2e={msg.e2e_profile}")
        return 0
    if args.cmd == "run":
        session = Session(backend=args.backend)
        can_ch = ChannelConfig(name="powertrain", kind=BusKind.CAN, dbc_paths=[str(args.dbc)])
        fd_ch = ChannelConfig(name="chassis", kind=BusKind.CANFD, dbc_paths=[str(args.dbc)])
        pt = session.add_channel(can_ch)
        ch = session.add_channel(fd_ch)
        for msg in pt.db.messages:
            if not msg.is_fd:
                pt.add_cyclic(msg.name)
        for msg in ch.db.messages:
            if msg.is_fd:
                ch.add_cyclic(msg.name)
        if args.log:
            session.enable_logging(args.log)
        t = 0.0
        step = 0.001
        while t < args.seconds:
            session.tick(t)
            t += step
        print(f"ran {args.seconds}s  channels={list(session.runtimes)}")
        return 0
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
