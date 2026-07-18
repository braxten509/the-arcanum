"""Verified offline variant bank and persist-before-display assignments."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone

from runtimes.common import atomic_write


class VariantUnavailable(ValueError):
    pass


def _tree_hash(root: str) -> str:
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in {"hidden", "reference", "mutations"})
        for name in sorted(filenames):
            if name == "manifest.json":
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise VariantUnavailable("variant package contains a symlink")
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            digest.update(relative.encode("utf-8") + b"\0")
            with open(full, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


class VariantRepository:
    def __init__(self, tome_root: str, save_root: str):
        self.bank = os.path.join(tome_root, "generated", "mastery-labs")
        self.assignment_path = os.path.join(save_root, "variant-assignments.json")

    def _assignments(self) -> dict:
        try:
            with open(self.assignment_path, encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _variants(self, family_id: str) -> list[dict]:
        family = os.path.realpath(os.path.join(self.bank, family_id))
        if os.path.dirname(family) != os.path.realpath(self.bank):
            raise VariantUnavailable("invalid variant family id")
        variants = []
        try:
            names = sorted(os.listdir(family))
        except OSError:
            names = []
        for name in names:
            root = os.path.join(family, name)
            try:
                with open(os.path.join(root, "manifest.json"), encoding="utf-8") as handle:
                    manifest = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            if (manifest.get("version") != 1 or manifest.get("familyId") != family_id
                    or manifest.get("variantId") != name or manifest.get("verified") is not True):
                continue
            actual = _tree_hash(root)
            if manifest.get("contentHash") != actual:
                continue
            variants.append({"root": root, "manifest": manifest})
        return variants

    def assignment(self, family_id: str) -> dict | None:
        current = self._assignments().get(family_id)
        return current if isinstance(current, dict) and not current.get("abandoned") else None

    def assign(self, family_id: str, *, exclude: tuple[str, ...] = ()) -> dict:
        current = self.assignment(family_id)
        if current:
            return current
        candidates = [item for item in self._variants(family_id)
                      if item["manifest"]["variantId"] not in set(exclude)]
        if not candidates:
            raise VariantUnavailable(f"no verified variants are available for {family_id!r}")
        seed = secrets.token_hex(32)
        chosen = candidates[int.from_bytes(bytes.fromhex(seed), "big") % len(candidates)]["manifest"]
        assignments = self._assignments()
        previous = assignments.get(family_id) or {}
        value = {
            "familyId": family_id, "variantId": chosen["variantId"],
            "variantHash": chosen["contentHash"], "seed": seed,
            "assignedAt": datetime.now(timezone.utc).isoformat(),
            "attempt": int(previous.get("attempt") or 0) + 1, "abandoned": False,
        }
        assignments[family_id] = value
        atomic_write(self.assignment_path, json.dumps(assignments, indent=2, sort_keys=True) + "\n")
        return value

    def abandon(self, family_id: str) -> dict:
        assignments = self._assignments()
        current = assignments.get(family_id)
        if not isinstance(current, dict) or current.get("abandoned"):
            raise VariantUnavailable("there is no active variant to abandon")
        current["abandoned"] = True
        current["abandonedAt"] = datetime.now(timezone.utc).isoformat()
        assignments[family_id] = current
        atomic_write(self.assignment_path, json.dumps(assignments, indent=2, sort_keys=True) + "\n")
        return current

    def public_package(self, family_id: str, variant_id: str) -> dict:
        item = next((row for row in self._variants(family_id)
                     if row["manifest"]["variantId"] == variant_id), None)
        if not item:
            raise VariantUnavailable("assigned verified variant is unavailable")
        manifest, root = item["manifest"], item["root"]
        files = []
        public = os.path.join(root, "public")
        for dirpath, dirnames, filenames in os.walk(public):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, public).replace(os.sep, "/")
                with open(full, encoding="utf-8", errors="replace") as handle:
                    files.append({"path": relative, "content": handle.read(500_000)})
        return {"version": 1, "familyId": family_id, "variantId": variant_id,
                "variantHash": manifest["contentHash"], "title": manifest.get("title", ""),
                "brief": manifest.get("brief", ""), "requirements": manifest.get("requirements", []),
                "axes": manifest.get("axes", {}), "files": files}
