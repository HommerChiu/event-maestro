"""Tiny stdlib HTTP server: serves the pixel-art site and the ``/collect`` endpoint."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .collector import CollectError, Collector
from .content import catalog
from .sink import JsonlSink

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
MAX_BODY_BYTES = 1_000_000


def make_handler(collector: Collector, web_root: Path = WEB_ROOT):
    web_root = web_root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "EventMaestro/0.1"

        def log_message(self, fmt, *args):  # quieter than the default
            if not self.path.startswith("/collect"):
                super().log_message(fmt, *args)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/api/articles":
                return self._json(catalog())
            if url.path == "/api/recent":
                limit = int(parse_qs(url.query).get("limit", ["50"])[0])
                return self._json({"rows": collector.recent_rows(min(limit, 200))})
            return self._static(url.path)

        def do_POST(self):
            if urlparse(self.path).path != "/collect":
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                return self._json({"error": "bad body size"}, HTTPStatus.BAD_REQUEST)
            try:
                payload = json.loads(self.rfile.read(length))
                rows = collector.collect(payload, self.headers.get("User-Agent", ""))
            except (json.JSONDecodeError, CollectError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return self._json({"accepted": len(rows)})

        def _static(self, path: str):
            relative = path.lstrip("/") or "index.html"
            target = (web_root / relative).resolve()
            if web_root not in target.parents and target != web_root:
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            if not target.is_file():
                if "." in Path(relative).name:
                    return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                target = web_root / "index.html"  # client-side routes
            body = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype == "application/javascript":
                ctype += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: HTTPStatus = HTTPStatus.OK):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, output_dir: str | None = None) -> None:
    sink = JsonlSink(output_dir, file_stem="collector")
    collector = Collector(sink)
    httpd = ThreadingHTTPServer((host, port), make_handler(collector))
    print(f"Pixel Notes running at http://{host}:{port}")
    print(f"Events land in {sink.output_dir.resolve()}/raw/ga4_events/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        sink.close()
