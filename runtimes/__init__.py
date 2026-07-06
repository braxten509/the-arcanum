"""Runtime registry. A tome names its runtime (`[runtime] name = "..."`) and the server
dispatches compile/run/diagnostics/package ops to it.

Every language is pure TOML config, executed by the one config-driven engine in
generic.py (commands + placeholders + regex diagnostics — see its docstring for the
full key reference). Adding a language never requires Python: drop a
`global-configs/runtimes/<name>.toml` describing the commands and any tome can use
it with `[runtime] name = "<name>"`. Keys in the language toml are defaults; the
tome's [runtime] table overrides them."""
import os
import re
import tomllib

from . import generic

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "global-configs", "runtimes")
DEFAULT = "dotnet"  # tomes that name no runtime get this (back-compat)


def lang_config(name):
    """Defaults from global-configs/runtimes/<name>.toml, or {} if there is no such file."""
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return {}
    try:
        with open(os.path.join(_DIR, name + ".toml"), "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def resolve_config(cfg):
    """A tome's [runtime] table merged over its language-toml defaults."""
    cfg = dict(cfg or {})
    cfg.setdefault("name", DEFAULT)
    return {**lang_config(cfg["name"]), **cfg}


def for_config(cfg):
    """The runtime for a tome's [runtime] table: one config-driven engine, any language."""
    return generic.CommandRuntime(resolve_config(cfg))


def get(name):
    """Runtime by language-toml name (used by /api/health)."""
    return for_config({"name": name or DEFAULT})


def names():
    try:
        return sorted(f[:-5] for f in os.listdir(_DIR) if f.endswith(".toml"))
    except OSError:
        return []
