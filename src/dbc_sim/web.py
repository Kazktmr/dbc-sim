"""Local HTTP front-end for LiveEngine. Stdlib only — no extra deps."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dbc_sim.live import LiveEngine


def _template_path() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2] / "templates" / "live.html"


class LiveServer:
    def __init__(self, engine: LiveEngine, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.engine = engine
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        handler = _make_handler(engine)
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def serve_forever(self) -> None:
        assert self.httpd is not None
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()

    def serve_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="dbc-sim-http", daemon=True)
        thread.start()
        return thread


def _make_handler(engine: LiveEngine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            if self.path.startswith("/api/"):
                return
            super().log_message(fmt, *args)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send_html()
                return
            if path == "/api/state":
                self._send_json(engine.snapshot())
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                body = self._read_json()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            try:
                if path == "/api/pause":
                    engine.pause()
                elif path == "/api/resume":
                    engine.resume()
                elif path == "/api/signal":
                    engine.set_signal(
                        str(body["channel"]),
                        str(body["message"]),
                        str(body["signal"]),
                        float(body["value"]),
                    )
                elif path == "/api/e2e":
                    faults = {
                        key: bool(body[key])
                        for key in ("fault_crc", "fault_freeze_counter", "fault_skip_counter")
                        if key in body
                    }
                    engine.set_e2e(str(body["channel"]), str(body["message"]), **faults)
                elif path == "/api/cyclic":
                    engine.set_cyclic(str(body["channel"]), str(body["message"]), bool(body["enabled"]))
                elif path == "/api/channel":
                    names = body.get("channels") or [body["channel"]]
                    engine.set_active_channels([str(n) for n in names])
                elif path == "/api/send":
                    engine.send_once(str(body["channel"]), str(body["message"]))
                else:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
            except (KeyError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(engine.snapshot())

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            blob = json.dumps(payload).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def _send_html(self) -> None:
            path = _template_path()
            if not path.is_file():
                self._send_json({"error": f"missing template {path}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            blob = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    return Handler
