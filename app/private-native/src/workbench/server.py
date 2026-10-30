"""Strict loopback allowlist. No owner routes, proxy routes, shell or file browser."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import time
from . import VERSION


def make_server(service, static_root, port=8777, *, runtime_revision=None, offline_review=False, campaign_views=None):
    token = secrets.token_urlsafe(32)
    static_root = Path(static_root)
    static = {"/": ("index.html", "text/html; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
              "/styles.css": ("styles.css", "text/css; charset=utf-8"),
              "/workbench.css": ("workbench.css", "text/css; charset=utf-8")}
    # Serve immutable startup asset bytes, never a mixture of changed files.
    static_bytes={route:(static_root/name).read_bytes() for route,(name,kind) in static.items()}
    import hashlib
    static_hashes={route:hashlib.sha256(raw).hexdigest() for route,raw in static_bytes.items()}
    views=dict(campaign_views or {})

    def revision():
        value=runtime_revision.public() if runtime_revision is not None else {
            'schema':'se6-frozen-runtime-revision-v1','source_manifest_sha256':None,
            'disk_matches_loaded':None,'scope':'Legacy process has no frozen-source attestation.'}
        changed=[]
        for route,(name,kind) in static.items():
            try:current=hashlib.sha256((static_root/name).read_bytes()).hexdigest()
            except OSError:current=None
            if current!=static_hashes[route]:changed.append(route)
        return {**value,'static_manifest':dict(static_hashes),'changed_disk_assets':changed,
                'static_disk_matches_loaded':not changed,'static_scope':'Exact immutable bytes captured when this server was constructed.'}

    def config():
        value=service.configuration()
        value['runtime_revision']=revision();value['offline_review']=bool(offline_review)
        if views:
            value['components']={**value['components'],'campaign_review':{
                'endpoint':'/api/campaigns','read_only':True,'contract':'se6-campaign-review-v1'}}
        return value

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            pass

        def respond(self, status, data, kind="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            for key, value in {"Content-Type": kind, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                               "Connection": "close",
                               "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                               "Cross-Origin-Resource-Policy": "same-origin",
                               "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                               "X-SE6-Workbench-Version": VERSION}.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def reject(self, status, data):
            """Deny without dispatch; discard only a small, explicitly framed body.

            Closing with unread POST bytes can reset the connection before the
            peer reads our denial. Consume a bounded valid Content-Length body
            without parsing it, under a total time limit. Malformed, oversized,
            chunked and Expect bodies are not drained or interpreted.
            """
            self.close_connection = True
            lengths = self.headers.get_all("Content-Length", [])
            if (not self.headers.get("Transfer-Encoding") and
                    not self.headers.get("Expect") and len(lengths) == 1 and
                    re.fullmatch(r"[0-9]{1,6}", lengths[0].strip())):
                remaining = int(lengths[0])
                if 0 < remaining <= 400000:
                    previous_timeout = self.connection.gettimeout()
                    deadline = time.monotonic() + 1.0
                    try:
                        while remaining:
                            available = deadline - time.monotonic()
                            if available <= 0:
                                break
                            self.connection.settimeout(available)
                            chunk = self.rfile.read1(min(remaining, 65536))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    except (OSError, ValueError):
                        # Failure to discard is still denial, never dispatch.
                        pass
                    finally:
                        try:
                            self.connection.settimeout(previous_timeout)
                        except OSError:
                            pass
            return self.respond(status, data)

        def valid_host(self):
            host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            # Opening the displayed URL from another site is a navigation, not
            # an API read/write. Permit only an explicit user navigation to the
            # root document; retain the exact Host/Origin and API/CSRF guards.
            root_navigation = (self.command == "GET" and self.path == "/" and origin is None and
                               self.headers.get("Sec-Fetch-Mode") == "navigate" and
                               self.headers.get("Sec-Fetch-Dest") == "document" and
                               self.headers.get("Sec-Fetch-User") == "?1")
            return (self.headers.get("Host") == host and
                    (origin is None or origin == "http://" + host) and
                    (self.headers.get("Sec-Fetch-Site") != "cross-site" or root_navigation))

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "Use the displayed loopback URL."})
            try:
                if self.path in static:
                    name, kind = static[self.path]
                    return self.respond(200, static_bytes[self.path], kind)
                if self.path == "/api/version":
                    return self.respond(200, {"version": VERSION, "executable_se6": service.configuration()["components"]["executable_se6"], 'runtime_revision':revision(),'offline_review':bool(offline_review)})
                if self.path == "/api/config":
                    return self.respond(200, {**config(), "csrf_token": token})
                if self.path == '/api/campaigns' and views:
                    return self.respond(200, {'schema':'se6-campaign-review-v1','campaigns':[view() for ident,view in sorted(views.items())]})
                if self.path == "/api/tasks":
                    return self.respond(200, {"tasks": service.list_tasks()})
                match = re.fullmatch(r"/api/tasks/([0-9a-f]{32})", self.path)
                if match:
                    return self.respond(200, service.get(match.group(1)))
                return self.respond(404, {"error": "Not found."})
            except KeyError:
                return self.respond(404, {"error": "Unknown task."})
            except (ValueError, OSError):
                return self.respond(503, {"error": "Local configuration or storage could not be read. No model request was made by this GET."})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if (not self.valid_host() or self.headers.get("Origin") != origin or
                    not secrets.compare_digest(self.headers.get("X-Comparison-Token", ""), token)):
                return self.reject(403, {"error": "Write action requires this local page and its token."})
            action = re.fullmatch(r"/api/tasks/([0-9a-f]{32})/(continue|cancel)", self.path)
            if self.path not in ("/api/tasks", "/api/settings", "/api/dispatch", "/api/plan", "/api/solve") and not action:
                return self.reject(404, {"error": "Not found."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reject(415, {"error": "JSON required."})
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Transfer encoding is not accepted.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 400000:
                    raise ValueError("Invalid request size.")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request; no submission.")
                value = json.loads(raw)
                if self.path == "/api/plan":
                    return self.respond(200, service.plan(value))
                if self.path == "/api/solve":
                    return self.respond(200, {"id": service.solve_native(value)})
                if self.path == "/api/settings":
                    return self.respond(200, service.update_settings(value))
                if self.path == "/api/dispatch":
                    if not isinstance(value, dict) or set(value) != {"paused"}:
                        raise ValueError("Provide only paused.")
                    return self.respond(200, service.pause(value["paused"]))
                if action:
                    task_id, operation = action.groups()
                    if operation == "cancel":
                        if value != {}:
                            raise ValueError("Cancellation takes an empty object.")
                        return self.respond(200, service.cancel(task_id))
                    return self.respond(202, {"id": service.continue_task(task_id, value)})
                return self.respond(202, {"id": service.create(value)})
            except KeyError:
                return self.respond(404, {"error": "Unknown task."})
            except (ValueError, TypeError, UnicodeError) as exc:
                return self.respond(400, {"error": str(exc)})
            except OSError:
                return self.respond(503, {"error": "State could not be saved. Check task status; do not automatically repeat a submission."})
            except Exception:
                return self.respond(500, {"error": "Local operation failed. Check task status before any new submission."})

    server=ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.revision_snapshot=revision
    return server
