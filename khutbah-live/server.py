#!/usr/bin/env python3
"""Khutbah Live control server. Run on the Mac Studio:  python3 server.py

Open http://<mac-address>:8080 on a phone to set the title and go live / end.
Buttons and shortcuts can call /api/start, /api/stop or /api/toggle with ?key=<accessKey>.
"""

import hmac
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import BASE_DIR, load_config
from controller import Controller

CFG = load_config()
ACCESS_KEY = str(CFG.get("accessKey", ""))
if len(ACCESS_KEY) < 6 or ACCESS_KEY == "change-me":
    raise SystemExit("Set a real accessKey (at least 6 characters) in config.json first.")
CTRL = Controller(CFG)
INDEX = os.path.join(BASE_DIR, "static", "index.html")


class Handler(BaseHTTPRequestHandler):
    server_version = "KhutbahLive"

    def log_message(self, fmt, *args):
        pass  # keep the console for the controller's own log

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, query):
        supplied = self.headers.get("X-Access-Key") or query.get("key", [""])[0]
        return hmac.compare_digest(supplied.encode(), ACCESS_KEY.encode())

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        path = url.path.rstrip("/") or "/"

        if path == "/" and method == "GET":
            with open(INDEX, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._authorized(query):
            return self._send(401, {"error": "wrong or missing access key"})

        source = query.get("source", ["button" if method == "GET" else "web"])[0][:30]
        if path == "/api/status":
            return self._send(200, CTRL.snapshot())
        if path in ("/api/start", "/api/stop", "/api/toggle"):
            action = {"/api/start": CTRL.start, "/api/stop": CTRL.stop, "/api/toggle": CTRL.toggle}[path]
            ok, msg = action(source)
            return self._send(200 if ok else 409, {"ok": ok, "message": msg, "status": CTRL.status})
        if path == "/api/next" and method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(min(length, 100_000)) or b"{}")
            except ValueError:
                return self._send(400, {"error": "invalid JSON"})
            CTRL.set_next_details(body)
            return self._send(200, CTRL.snapshot())
        return self._send(404, {"error": "not found"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def main():
    host = CFG.get("listenHost", "0.0.0.0")
    port = int(CFG.get("listenPort", 8080))
    mode = " (DRY RUN - nothing goes to YouTube/Facebook)" if CTRL.dry_run else ""
    CTRL.log(f"Khutbah Live control page on http://{host}:{port}{mode}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
