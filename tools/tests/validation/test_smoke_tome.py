#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Focused regression test for the deterministic live tome smoke client."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.config import jobs
from arcanum.authoring.grader import start_grader_smoke
from smoke_tome import smoke_tome


class _Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - stdlib handler contract
        if self.path.startswith("/api/tome?"):
            return self._json({"sections": [{
                "id": "s01", "lessons": [{
                    "id": "s01-l01", "body": "A real rendered lesson",
                    "exercises": [{"id": "w1", "type": "write",
                                   "solution": "print('OK')", "expect": "OK"}],
                }], "freestyle": {"rubric": [{"criterion": "Works", "weight": 100}]},
            }]})
        if self.path.startswith("/api/grade/status?"):
            return self._json({"status": "done", "result": {"smoke": True}})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/api/runsnippet?"):
            assert body["code"] == "print('OK')"
            return self._json({"ok": True, "output": "OK\n"})
        if self.path.startswith("/api/grade?"):
            assert body == {"tome": "demo", "smoke": True, "sectionId": "s01"}
            return self._json({"ok": True, "jobId": "job-1", "smoke": True})
        return self._json({"error": "not found"}, 404)

    def log_message(self, _format, *_args):
        pass


def main():
    assembled = {"sections": [{"id": "s01", "freestyle": {
        "rubric": [{"criterion": "Works", "weight": 100}]}}]}
    with patch("arcanum.authoring.grader.assemble_tome", return_value=assembled):
        response, status = start_grader_smoke("demo", {"sectionId": "s01"})
    assert status == 200 and response["ok"]
    job = jobs.pop(response["jobId"])
    assert job["status"] == "done" and job["result"]["smoke"] is True

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        checks = smoke_tome(
            "demo", f"http://127.0.0.1:{server.server_address[1]}", timeout=2,
            poll_interval=0.01)
        assert len(checks) == 4
        assert any("/api/runsnippet" in check for check in checks)
        assert checks[-1].endswith("`done`")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("ok live smoke: loader + runtime + grader done lifecycle")


if __name__ == "__main__":
    main()
