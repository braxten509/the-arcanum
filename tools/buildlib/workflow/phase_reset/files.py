"""Id validation and the atomic file moves every rewind step is built from."""
from __future__ import annotations

import json
import os
import re
import shutil


ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _valid_id(value):
    value = str(value or "")
    if not ID_RE.fullmatch(value):
        raise ValueError(f"invalid tome/build id {value!r}")
    return value


def _atomic_text(path, text):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, path)


def _atomic_json(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _copy_item(source, target):
    if os.path.isdir(source) and not os.path.islink(source):
        shutil.copytree(source, target)
    else:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
