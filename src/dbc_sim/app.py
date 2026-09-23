"""CLI entry. Hardware TX comes online once a dongle is present; --backend null always works."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from dbc_sim import __version__
from dbc_sim.dbc.loader import load_dbc
from dbc_sim.frames import BusKind, ChannelConfig
from dbc_sim.live import LiveEngine
from dbc_sim.session import Session
from dbc_sim.web import LiveServer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dbc-sim", description="Physical CAN / CAN-FD DBC simulator")
    p.add_argument("--version", action="version", version=f"dbc-sim {__version__}")
    sub = p.add_subparsers(dest="cmd")

    show = sub.add_parser("show-dbc", help="Print messages from a raw .dbc")
    show.add_argument("dbc", type=Path)

    run = sub.add_parser("run", help="Run a DBC session on the null bus or a hardware adapter")
    run.add_argument("dbc", type=Path)
    run.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Sim duration. Default 0.05 without --live, forever with --live",
    )
    run.add_argument("--backend", default="null")
    run.add_argument("--log", type=Path, default=None)
    run.add_argument("--live", action="store_true", help="Open a local browser view and keep TX running")
    run.add_argument(
        "--channel",
        default=None,
        help="powertrain (classic CAN), chassis (CAN FD), or all. Default: all without --live, powertrain with --live",
    )
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    return p


def _wanted_channels(channel: str | None, live: bool) -> list[str]:
    raw = (channel or ("powertrain" if live else "all")).lower()
    if raw in {"all", "both"}:
        return ["powertrain", "chassis"]
    if raw in {"powertrain", "can", "pt"}:
        return ["powertrain"]
    if raw in {"chassis", "canfd", "fd"}:
        return ["chassis"]
    raise SystemExit(f"unknown --channel {channel!r} (use powertrain, chassis, or all)")


def _build_session(dbc: Path, backend: str, names: list[str]) -> Session:
    session = Session(backend=backend)
    specs = {
        "powertrain": ChannelConfig(name="powertrain", kind=BusKind.CAN, dbc_paths=[str(dbc)]),
        "chassis": ChannelConfig(name="chassis", kind=BusKind.CANFD, dbc_paths=[str(dbc)]),
    }
    for name in names:
        rt = session.add_channel(specs[name])
        for msg in rt.db.messages:
            if name == "powertrain" and not msg.is_fd:
                rt.add_cyclic(msg.name)
            elif name == "chassis" and msg.is_fd:
                rt.add_cyclic(msg.name)
    return session


def _run_batch(session: Session, seconds: float) -> int:
    t = 0.0
    step = 0.001
    while t < seconds:
        session.tick(t)
        t += step
    print(f"ran {seconds}s  channels={list(session.runtimes)}")
    return 0


def _run_live(session: Session, args: argparse.Namespace) -> int:
    engine = LiveEngine(session, seconds=args.seconds)
    engine.start()
    server = LiveServer(engine, host=args.host, port=args.port)
    print(f"live view  {server.url}  channels={list(session.runtimes)}  backend={session.backend}")
    print("Pause / edit signals / inject E2E faults in the browser. Ctrl+C stops TX.")
    if not args.no_browser:
        try:
            webbrowser.open(server.url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        engine.stop()
        server.shutdown()
    return 0


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
        names = _wanted_channels(args.channel, args.live)
        session = _build_session(args.dbc, args.backend, names)
        if args.log:
            session.enable_logging(args.log)
        if args.live:
            return _run_live(session, args)
        seconds = 0.05 if args.seconds is None else args.seconds
        return _run_batch(session, seconds)
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
