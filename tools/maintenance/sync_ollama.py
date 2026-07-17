#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""sync_ollama.py — mirror locally-pulled ollama models into opencode's provider config.

The Bindery lists ollama models straight from `ollama list`, but opencode only ROUTES models
declared under its `ollama` provider in ~/.config/opencode/opencode.jsonc. Without the entry,
`opencode run -m ollama/<model>` fails with "Unexpected server error". This regenerates that
provider block from `ollama list` so a freshly-pulled model is runnable with no hand-editing.

Run standalone after `ollama pull`, or let the server run it on startup (it does). No-ops
(exit 0) when ollama or the opencode config is absent. Stdlib only.

    python3 tools/maintenance/sync_ollama.py            # sync
    python3 tools/maintenance/sync_ollama.py --selftest # check the string surgery
"""
import os
import re
import shutil
import subprocess
import sys

OPENCODE_CFG = os.path.expanduser("~/.config/opencode/opencode.jsonc")
OLLAMA_BASEURL = "http://127.0.0.1:11434/v1"


def ollama_models():
    """Locally-pulled model names (e.g. 'qwen3-coder:30b'), or None if ollama is unavailable."""
    exe = shutil.which("ollama")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    names = []
    for line in out.stdout.splitlines()[1:]:  # skip the NAME/ID/SIZE header
        line = line.strip()
        if line:
            names.append(line.split()[0])     # first column = NAME
    return names


def _title(name):
    """'qwen3-coder:30b' -> 'Qwen3 Coder 30B' — a best-effort display label."""
    base, _, tag = name.partition(":")
    label = " ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_]", base) if w)
    return (label + " " + tag.upper()).strip() if tag else label


def build_block(names, indent="    "):
    """The full `"ollama": { … }` provider entry, matching the file's 2-space nesting."""
    i2, i3 = indent + "  ", indent + "    "
    models = ",\n".join(f'{i3}"{n}": {{ "name": "{_title(n)}" }}' for n in names)
    return (f'{indent}"ollama": {{\n'
            f'{i2}"npm": "@ai-sdk/openai-compatible",\n'
            f'{i2}"name": "Ollama (local)",\n'
            f'{i2}"options": {{\n'
            f'{i3}"baseURL": "{OLLAMA_BASEURL}"\n'
            f'{i2}}},\n'
            f'{i2}"models": {{\n'
            f'{models}\n'
            f'{i2}}}\n'
            f'{indent}}}')


def _value_end(text, brace_pos):
    """Index just past the '}' that closes the object opening at brace_pos (brace-balanced).
    Safe here because no string value in this config contains a brace."""
    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def splice(text, block):
    """Return `text` with the `ollama` provider replaced by `block` (or inserted as the first
    provider entry if absent), or None if the config shape isn't recognized."""
    m = re.search(r'\n[ \t]*"ollama"\s*:\s*', text)
    if m:
        brace = text.find("{", m.end())
        end = _value_end(text, brace) if brace != -1 else None
        if end is None:
            return None
        # keep the rest verbatim — any trailing comma after '}' stays in text[end:]
        return text[:m.start()] + "\n" + block + text[end:]
    pm = re.search(r'"provider"\s*:\s*\{', text)
    if not pm:
        return None
    return text[:pm.end()] + "\n" + block + "," + text[pm.end():]


def sync(cfg=OPENCODE_CFG):
    names = ollama_models()
    if not names:
        print("sync-ollama: no ollama models (or ollama not installed) — skipped")
        return 0
    if not os.path.isfile(cfg):
        print("sync-ollama: no opencode.jsonc — skipped")
        return 0
    text = open(cfg, encoding="utf-8").read()
    new = splice(text, build_block(names))
    if new is None:
        print("sync-ollama: opencode.jsonc shape not recognized — left untouched")
        return 1
    if new == text:
        print(f"sync-ollama: already current ({len(names)} model(s))")
        return 0
    # integrity guard: braces must still balance (no string here holds a brace)
    if new.count("{") != new.count("}"):
        print("sync-ollama: edit would unbalance braces — aborted, config untouched")
        return 1
    shutil.copyfile(cfg, cfg + ".bak")           # one rescue copy before we write
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"sync-ollama: wrote {len(names)} ollama model(s) → {cfg}")
    return 0


def _selftest():
    assert _title("qwen3-coder:30b") == "Qwen3 Coder 30B", _title("qwen3-coder:30b")
    assert _title("llama3.1:8b") == "Llama3.1 8B", _title("llama3.1:8b")
    blk = build_block(["m:1", "n:2"])
    assert '"ollama": {' in blk and '"m:1"' in blk and blk.count("{") == blk.count("}")
    # replace an existing block
    cfg = ('{\n  "provider": {\n    "ollama": {\n      "old": true\n    },\n'
           '    "other": { "x": 1 }\n  }\n}\n')
    out = splice(cfg, build_block(["a:1"]))
    assert out is not None and '"a:1"' in out and '"old"' not in out
    assert '"other"' in out and out.count("{") == out.count("}"), out
    # the comma after the replaced block is preserved (ollama wasn't last)
    assert '},\n    "other"' in out, out
    # insert when absent
    cfg2 = '{\n  "provider": {\n    "other": { "x": 1 }\n  }\n}\n'
    out2 = splice(cfg2, build_block(["a:1"]))
    assert out2 is not None and '"ollama"' in out2 and out2.count("{") == out2.count("}")
    print("sync_ollama selftest: OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(sync())
