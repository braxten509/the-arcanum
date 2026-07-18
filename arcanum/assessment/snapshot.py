"""Bounded, secret-aware immutable workspace snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import stat
import tempfile


EXCLUDED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".gradle", ".idea", ".vscode", "venv", ".venv",
    "bin", "obj", "build", "dist", "out", "target", "coverage",
})
SECRET_NAMES = frozenset({
    ".env", ".npmrc", ".pypirc", "credentials", "credentials.json", "secrets.json",
    "id_rsa", "id_ed25519", "known_hosts", "authorized_keys",
})
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
TEXT_SUFFIXES = frozenset({
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html", ".java",
    ".js", ".json", ".kt", ".kts", ".md", ".php", ".py", ".rb", ".rs", ".sh",
    ".sql", ".swift", ".toml", ".ts", ".txt", ".xml", ".yaml", ".yml",
})


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotLimits:
    max_files: int = 2_000
    max_file_bytes: int = 4_000_000
    max_total_bytes: int = 80_000_000
    max_ai_file_bytes: int = 200_000
    max_ai_total_bytes: int = 1_500_000


@dataclass
class WorkspaceSnapshot:
    root: str
    source: str
    work: str
    home: str
    workspace_hash: str
    manifest: tuple[dict, ...]
    limits: SnapshotLimits

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def safe_text_files(self) -> list[tuple[str, str]]:
        files, total = [], 0
        for row in self.manifest:
            rel = row["path"]
            if os.path.splitext(rel)[1].lower() not in TEXT_SUFFIXES:
                continue
            if row["size"] > self.limits.max_ai_file_bytes:
                continue
            try:
                data = open(os.path.join(self.source, *rel.split("/")), "rb").read()
            except OSError:
                continue
            if b"\0" in data or total + len(data) > self.limits.max_ai_total_bytes:
                continue
            text = data.decode("utf-8", errors="replace")
            files.append((rel, text))
            total += len(data)
        return files

    def __enter__(self) -> "WorkspaceSnapshot":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def _secret_name(name: str) -> bool:
    low = name.casefold()
    return (low in SECRET_NAMES or low.startswith(".env")
            or low.endswith(SECRET_SUFFIXES)
            or low.endswith((".secret", ".secrets", ".token", ".credentials")))


def _hash_manifest(manifest: list[dict]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_snapshot(workspace: str, *, parent: str | None = None,
                    limits: SnapshotLimits | None = None) -> WorkspaceSnapshot:
    limits = limits or SnapshotLimits()
    source_root = os.path.realpath(workspace)
    if not os.path.isdir(source_root):
        raise SnapshotError("learner workspace is not an existing directory")
    root = tempfile.mkdtemp(prefix="arcanum-assessment-", dir=parent)
    source, work = os.path.join(root, "source"), os.path.join(root, "work")
    home = os.path.join(root, "home")
    os.makedirs(source)
    os.makedirs(home, mode=0o700)
    manifest, total = [], 0
    try:
        for dirpath, dirnames, filenames in os.walk(source_root, followlinks=False):
            if os.path.islink(dirpath):
                raise SnapshotError("workspace contains an unsupported directory symlink")
            dirnames[:] = sorted(name for name in dirnames
                                  if name not in EXCLUDED_DIRS and not _secret_name(name))
            for filename in sorted(filenames):
                if _secret_name(filename):
                    continue
                original = os.path.join(dirpath, filename)
                if os.path.islink(original):
                    raise SnapshotError(f"workspace contains unsupported symlink {filename!r}")
                info = os.stat(original, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise SnapshotError(f"workspace contains unsupported non-file {filename!r}")
                if info.st_size > limits.max_file_bytes:
                    raise SnapshotError(f"workspace file {filename!r} exceeds the size limit")
                total += info.st_size
                if total > limits.max_total_bytes or len(manifest) >= limits.max_files:
                    raise SnapshotError("workspace exceeds assessment snapshot limits")
                relative = os.path.relpath(original, source_root).replace(os.sep, "/")
                target = os.path.join(source, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                digest = hashlib.sha256()
                with open(original, "rb") as incoming, open(target, "wb") as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        digest.update(chunk)
                        outgoing.write(chunk)
                manifest.append({"path": relative, "size": info.st_size, "sha256": digest.hexdigest()})
        manifest.sort(key=lambda row: row["path"])
        shutil.copytree(source, work)
        for dirpath, dirnames, filenames in os.walk(source):
            for name in filenames:
                os.chmod(os.path.join(dirpath, name), 0o444)
            for name in dirnames:
                os.chmod(os.path.join(dirpath, name), 0o555)
        os.chmod(source, 0o555)
        with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
        return WorkspaceSnapshot(
            root, source, work, home, _hash_manifest(manifest), tuple(manifest), limits)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
