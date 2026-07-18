#!/usr/bin/env python3
"""Static delivery serves public assets and denies learner/private evidence data."""
from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.http.static import StaticFileServer
from arcanum.settings import load_settings


class Handler:
    def __init__(self, path: str):
        self.path = path
        self.wfile = io.BytesIO()
        self.status = None
        self.headers = {}
        self.json = None

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def send_json(self, body, status=200):
        self.json, self.status = body, status


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    (root / "web").mkdir()
    (root / "web" / "index.html").write_text("public", encoding="utf-8")
    public = root / "tomes" / "demo" / "assets"
    public.mkdir(parents=True)
    (public / "figure.svg").write_text("<svg/>", encoding="utf-8")
    private_paths = [
        root / "tomes" / "demo" / "save" / "state.json",
        root / "tomes" / "demo" / "assessment" / "contract.json",
        root / "tomes" / "demo" / "generated" / "mastery-labs" / "bank.json",
        root / "tomes" / "demo" / "sections" / "s01.toml",
    ]
    for path in private_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private", encoding="utf-8")
    server = StaticFileServer(load_settings(temp))

    index = Handler("/")
    server.serve(index)
    assert index.status == 200 and index.wfile.getvalue() == b"public"
    asset = Handler("/tomes/demo/assets/figure.svg")
    server.serve(asset)
    assert asset.status == 200 and asset.wfile.getvalue() == b"<svg/>"
    for path in (
        "/tomes/demo/save/state.json",
        "/tomes/demo/assessment/contract.json",
        "/tomes/demo/generated/mastery-labs/bank.json",
        "/tomes/demo/sections/s01.toml",
        "/../outside.txt",
    ):
        denied = Handler(path)
        server.serve(denied)
        assert denied.status == 404 and denied.json == {"error": "not found"}, path

print("static-file privacy boundary: OK")
