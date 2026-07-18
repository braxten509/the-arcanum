"""Explicit runtime profile registry and factory."""
from __future__ import annotations

from .command_runtime.runtime import CommandRuntime
from .config import DEFAULT_RUNTIME, RuntimeConfigRepository


class RuntimeRegistry:
    def __init__(self, configs: RuntimeConfigRepository, factory=CommandRuntime) -> None:
        self.configs, self.factory = configs, factory

    @classmethod
    def from_root(cls, root: str) -> "RuntimeRegistry":
        return cls(RuntimeConfigRepository.from_root(root))

    def for_config(self, config):
        return self.factory(self.configs.resolve(config))

    def for_snippets(self, config):
        values = dict(config or {})
        values.setdefault("name", DEFAULT_RUNTIME)
        defaults = self.configs.load_defaults(str(values["name"]))
        if values.get("scaffoldCommand") != [] or not defaults.get("scaffoldCommand"):
            return self.for_config(values)
        scratch = {"name": values["name"]}
        for key in ("validationDependencies", "validationProjectPackageCommand",
                    "validationPackageCommand", "validationEnv"):
            if key in values:
                scratch[key] = values[key]
        return self.for_config(scratch)

    def get(self, name: str):
        return self.for_config({"name": name or DEFAULT_RUNTIME})

    def names(self) -> tuple[str, ...]:
        return self.configs.names()
