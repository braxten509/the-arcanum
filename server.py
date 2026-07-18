#!/usr/bin/env python3
"""ARCANUM server — stdlib only. Serves the game, discovers/assembles Tomes,
persists per-tome state, runs code via pluggable runtimes, grades via claude CLI.
All logic lives in the arcanum/ package (see arcanum/__init__.py for the module
map); this file is just the HTTP shell and the entry point."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from arcanum.app import create_app_services
from arcanum.config import PORT, ROOT
from arcanum.http.composition import build_router
from arcanum.http.static import StaticFileServer


SERVICES = create_app_services()
ROUTER = build_router(SERVICES)
STATIC = StaticFileServer(SERVICES.settings)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/api/state" not in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not ROUTER.dispatch(self, "GET"):
            if self.path.split("?", 1)[0].startswith("/api/"):
                self.send_json({"error": "not found"}, 404)
            else:
                STATIC.serve(self)

    def do_POST(self):
        if not ROUTER.dispatch(self, "POST"):
            self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    try:  # mirror locally-pulled ollama models into opencode's config so new ones are runnable
        subprocess.run([sys.executable, os.path.join(
            ROOT, "tools", "maintenance", "sync_ollama.py")], timeout=30)
    except Exception as e:  # never let a config-sync hiccup block the server
        print(f"sync-ollama: skipped ({e})")
    for tome in SERVICES.catalog.list():
        SERVICES.workspaces.ensure_save(tome["id"])  # regenerate deleted save/ → fresh course
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"The candle is lit → {url}")
    if os.environ.get("ARCANUM_NO_OPEN") != "1":  # cross-platform auto-open; set =1 to suppress
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
