"""Loopback-only comparison UI; model dispatch requires an explicit POST."""
from __future__ import annotations

from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets


def make_server(service, static_root: Path, port=8777):
    token = secrets.token_urlsafe(32)
    static = {"/": ("index.html", "text/html; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
              "/styles.css": ("styles.css", "text/css; charset=utf-8"),
              "/model-settings.js": ("model-settings.js", "text/javascript; charset=utf-8"),
              "/model-settings.css": ("model-settings.css", "text/css; charset=utf-8")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # Do not log problem strings, outputs, tokens or credentials.
            pass

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "Use the displayed loopback URL."})
            if self.path in static:
                name, kind = static[self.path]
                return self.respond(200, (static_root / name).read_bytes(), kind)
            if self.path == "/api/config":
                return self.respond(200, {**service.configuration(), "csrf_token": token})
            match = re.fullmatch(r"/api/runs/([0-9a-f]{32})", self.path)
            if match:
                try:
                    return self.respond(200, service.get(match.group(1)))
                except KeyError:
                    return self.respond(404, {"error": "Unknown comparison."})
            return self.respond(404, {"error": "Not found."})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            supplied = self.headers.get("X-Comparison-Token", "")
            if (not self.valid_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(supplied, token)):
                return self.respond(403, {"error": "Comparison must be started from this local page."})
            if self.path not in ("/api/run", "/api/settings"):
                return self.respond(404, {"error": "Not found."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond(415, {"error": "JSON required."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 400000:
                    raise ValueError("Invalid request size.")
                value = json.loads(self.rfile.read(length))
                if self.path == "/api/settings":
                    return self.respond(200, service.update_settings(value))
                if not isinstance(value, dict) or set(value) != {"problem"}:
                    raise ValueError("Only the shared problem may be submitted.")
                run = service.start(value["problem"])
            except (ValueError, UnicodeError) as exc:
                return self.respond(400, {"error": str(exc)})
            return self.respond(202, {"id": run})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
