"""Constrained static-file delivery, separate from API routing."""
from __future__ import annotations

import os
import urllib.parse

from arcanum.config import MIME


class StaticFileServer:
    _SHARED_PREFIXES = ("monaco/", "skins/", "sounds/", "global-configs/")
    _PRIVATE_TOME_PARTS = frozenset(
        {"assessment", "hidden", "reference", "mutations", "blueprints"})

    def __init__(self, settings) -> None:
        self.settings = settings
        self.allowed_roots = tuple(os.path.realpath(path) for path in (
            settings.web_root,
            settings.tomes_root,
            os.path.join(settings.root, "monaco"),
            settings.skins_root,
            os.path.join(settings.root, "sounds"),
            os.path.join(settings.root, "global-configs"),
        ))

    @staticmethod
    def _within(path: str, root: str) -> bool:
        return path == root or path.startswith(root + os.sep)

    def _resolve(self, request_path: str) -> str | None:
        path = urllib.parse.unquote(request_path)
        if path == "/":
            path = "/index.html"
        relative = path.lstrip("/")
        if relative.startswith("tomes/"):
            base = self.settings.tomes_root
            relative = relative[len("tomes/"):]
        elif relative.startswith(self._SHARED_PREFIXES):
            base = self.settings.root
        else:
            base = self.settings.web_root
        full = os.path.realpath(os.path.join(base, relative))
        tome_root = os.path.realpath(self.settings.tomes_root)
        if self._within(full, tome_root):
            parts = full[len(tome_root):].lstrip(os.sep).split(os.sep)
            if len(parts) > 1 and parts[1] == "save":
                return None
            authored = parts[1:]
            if (len(authored) >= 2 and authored[0] == "generated"
                    and authored[1] == "mastery-labs"):
                return None
            if any(part in self._PRIVATE_TOME_PARTS for part in authored):
                return None
            if "sections" in authored and full.endswith(".toml"):
                return None
        if not any(self._within(full, root) for root in self.allowed_roots):
            return None
        return full if os.path.isfile(full) else None

    def serve(self, handler) -> None:
        parsed = urllib.parse.urlparse(handler.path)
        full = self._resolve(parsed.path)
        if not full:
            handler.send_json({"error": "not found"}, 404)
            return
        with open(full, "rb") as handle:
            body = handle.read()
        extension = os.path.splitext(full)[1]
        handler.send_response(200)
        handler.send_header("Content-Type", MIME.get(extension, "application/octet-stream"))
        handler.send_header("Content-Length", str(len(body)))
        cache = "no-cache" if extension in (".html", ".js", ".css", ".mp3") else "max-age=86400"
        handler.send_header("Cache-Control", cache)
        handler.end_headers()
        handler.wfile.write(body)
