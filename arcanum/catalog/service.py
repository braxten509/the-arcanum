"""Installed tome catalog and public assembly application service."""
from __future__ import annotations

import glob
import json
import os

from runtimes import for_config, for_snippets

from .assembly import assemble_public_tome
from .build_ids import resolve_working_id
from .filesystem import ManifestRepository
from .paths import TomePaths


class TomeCatalogService:
    def __init__(self, paths: TomePaths, manifests: ManifestRepository):
        self.paths = paths
        self.manifests = manifests

    def resolve_working_id(self, plan_id: str, text: str) -> str:
        return resolve_working_id(plan_id, text, self.paths.settings.tomes_root)

    def _draft_ids(self) -> set[str]:
        out = set()
        for plan_path in glob.glob(os.path.join(self.paths.settings.build_root, "*.plan.md")):
            plan_id = os.path.basename(plan_path)[:-len(".plan.md")]
            try:
                with open(plan_path, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                continue
            try:
                with open(os.path.join(self.paths.settings.build_root,
                                       f"{plan_id}.result.json"), encoding="utf-8") as handle:
                    result = json.load(handle)
            except FileNotFoundError:
                result = {}
            except (OSError, json.JSONDecodeError):
                continue
            if result.get("status") == "done":
                continue
            if result.get("status") in {"error", "cancelled"} or "Harness ground truth" not in text:
                out.add(self.resolve_working_id(plan_id, text))
        return out

    def list(self) -> list[dict]:
        try:
            drafts = self._draft_ids()
        except Exception:
            drafts = set()
        out = []
        for path in sorted(glob.glob(os.path.join(self.paths.settings.tomes_root,
                                                  "*", "tome.toml"))):
            tome_id = os.path.basename(os.path.dirname(path))
            try:
                manifest = self.manifests.load(tome_id)
            except Exception:
                continue
            meta = dict(manifest.get("meta") or {})
            meta["id"] = tome_id
            meta["runtime"] = (manifest.get("runtime") or {}).get("name", "custom")
            meta["sectionCount"] = len((manifest.get("content") or {}).get("sections", []))
            meta["draft"] = tome_id in drafts
            out.append(meta)
        return out

    def resolve(self, hint: str | None) -> str:
        try:
            if hint and os.path.isfile(self.paths.manifest(hint)):
                return str(hint)
        except ValueError:
            pass
        installed = self.list()
        return installed[0]["id"] if installed else "verisearch"

    def manifest(self, tome_id: str) -> dict:
        return self.manifests.load(tome_id)

    def assemble(self, tome_id: str) -> dict:
        return assemble_public_tome(self.manifest(tome_id), self.paths.tome(tome_id),
                                    self.paths.settings.skins_root)

    def runtime(self, tome_id: str):
        return for_config((self.manifest(tome_id).get("runtime") or {}))

    def snippet_runtime(self, tome_id: str):
        return for_snippets((self.manifest(tome_id).get("runtime") or {}))

    def project_name(self, tome_id: str) -> str:
        return (self.manifest(tome_id).get("runtime") or {}).get("project", "Project")
