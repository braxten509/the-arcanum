"""Language-neutral runtime protocol, registry, and compatibility functions."""
from __future__ import annotations

import os
from functools import lru_cache

from .command_runtime import CommandRuntime
from .config import DEFAULT_RUNTIME, RuntimeConfigRepository
from .protocol import Runtime
from .registry import RuntimeRegistry

@lru_cache(maxsize=1)
def default_registry() -> RuntimeRegistry:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return RuntimeRegistry.from_root(root)


def lang_config(name):
    try:
        return default_registry().configs.load_defaults(name)
    except ValueError:
        return {}


def resolve_config(config):
    return default_registry().configs.resolve(config).to_dict()


def for_config(config):
    return default_registry().for_config(config)


def snippet_config(config):
    runtime = default_registry()
    values = dict(config or {})
    values.setdefault("name", DEFAULT_RUNTIME)
    defaults = runtime.configs.load_defaults(values["name"])
    if values.get("scaffoldCommand") != [] or not defaults.get("scaffoldCommand"):
        return values
    return {key: value for key, value in values.items()
            if key == "name" or key in {"validationDependencies",
                                        "validationProjectPackageCommand",
                                        "validationPackageCommand", "validationEnv"}}


def for_snippets(config):
    return default_registry().for_snippets(config)


def get(name):
    return default_registry().get(name)


def names():
    return list(default_registry().names())


__all__ = ["CommandRuntime", "Runtime", "RuntimeConfigRepository", "RuntimeRegistry",
           "default_registry", "for_config", "for_snippets", "get", "lang_config",
           "names", "resolve_config", "snippet_config"]
