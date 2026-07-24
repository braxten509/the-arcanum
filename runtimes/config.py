"""Validated runtime-profile repository and immutable configuration values."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import tomllib
from types import MappingProxyType
from typing import Mapping


DEFAULT_RUNTIME = "dotnet"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_ARGV_KEYS = (
    "command", "runCommand", "snippetRunCommand", "buildCommand", "checkCommand",
    "scaffoldCommand", "packageCommand", "validationPackageCommand",
    "validationProjectPackageCommand", "deliveryCreateCommand",
    "deliveryResolveCommand", "deliveryInstallCommand", "deliveryBuildCommand",
)
_LIST_KEYS = (
    "validationDependencies", "excludeDirs", "codeExt", "capabilities",
    "commandTargetTools",
)
_TRUSTED_ASSESSMENT_KEYS = ("assessmentReadPaths", "assessmentEnvironment")


class RuntimeConfigurationError(ValueError):
    pass


def find_runtime_profile(directory: str, name: str) -> str:
    """Resolve one named profile across the categorized runtime tree."""
    if not name or not _ID.fullmatch(str(name)):
        return ""
    filename = str(name) + ".toml"
    matches = []
    for base, directories, files in os.walk(directory):
        directories[:] = sorted(
            child for child in directories if not child.startswith("."))
        if filename in files:
            matches.append(os.path.join(base, filename))
    if len(matches) > 1:
        relative = [os.path.relpath(path, directory) for path in matches]
        raise RuntimeConfigurationError(
            f"runtime {name!r} has duplicate profiles: {', '.join(relative)}")
    return matches[0] if matches else ""


@dataclass(frozen=True)
class RuntimeConfig:
    values: Mapping[str, object]

    @classmethod
    def parse(cls, source: Mapping[str, object]) -> "RuntimeConfig":
        values = dict(source)
        name = str(values.get("name") or "custom")
        if not _ID.fullmatch(name):
            raise RuntimeConfigurationError(f"invalid runtime name {name!r}")
        values["name"] = name
        # Ad-hoc legacy tome runtimes predate registry metadata. Keep them loadable behind
        # an explicit compatibility capability; checked-in profiles declare both fields.
        values.setdefault("version", 1)
        values.setdefault("capabilities", ("legacy-runtime",))
        if not isinstance(values.get("version"), int) or values["version"] < 1:
            raise RuntimeConfigurationError(f"runtime {name!r} needs a positive version")
        for key in _ARGV_KEYS:
            if key not in values:
                continue
            argv = values[key]
            if not isinstance(argv, (list, tuple)) or not all(
                    isinstance(item, str) and item and "\x00" not in item for item in argv):
                raise RuntimeConfigurationError(f"runtime {name!r} {key} must be an argv array")
            values[key] = tuple(argv)
        for key in _LIST_KEYS:
            if key in values:
                value = values[key]
                if not isinstance(value, (list, tuple)) or not all(
                        isinstance(item, str) for item in value):
                    raise RuntimeConfigurationError(
                        f"runtime {name!r} {key} must be a string array")
                values[key] = tuple(value)
        if not values.get("capabilities") or any(not item for item in values["capabilities"]):
            raise RuntimeConfigurationError(f"runtime {name!r} needs capabilities")
        assessment = values.get("assessmentCommands") or {}
        if not isinstance(assessment, dict):
            raise RuntimeConfigurationError(
                f"runtime {name!r} assessmentCommands must be a table")
        normalized_assessment = {}
        for command_id, argv in assessment.items():
            if not isinstance(argv, (list, tuple)) or not all(
                    isinstance(item, str) and item and "\x00" not in item for item in argv):
                raise RuntimeConfigurationError(
                    f"runtime {name!r} assessment command {command_id!r} must be argv")
            normalized_assessment[str(command_id)] = tuple(argv)
        values["assessmentCommands"] = MappingProxyType(normalized_assessment)
        read_paths = values.get("assessmentReadPaths") or ()
        if (not isinstance(read_paths, (list, tuple))
                or not all(isinstance(path, str) and path and "\x00" not in path
                           for path in read_paths)):
            raise RuntimeConfigurationError(
                f"runtime {name!r} assessmentReadPaths must be a string array")
        values["assessmentReadPaths"] = tuple(read_paths)
        assessment_environment = values.get("assessmentEnvironment") or {}
        if (not isinstance(assessment_environment, dict)
                or any(not isinstance(key, str) or not key
                       or not isinstance(value, str) or "\x00" in value
                       for key, value in assessment_environment.items())):
            raise RuntimeConfigurationError(
                f"runtime {name!r} assessmentEnvironment must be a string table")
        values["assessmentEnvironment"] = MappingProxyType(dict(assessment_environment))
        artifact = values.get("artifactPath")
        if artifact is not None:
            artifact_parts = artifact.split("/") if isinstance(artifact, str) else ()
            if (not isinstance(artifact, str) or not artifact.strip()
                    or "\x00" in artifact or artifact.startswith(("/", "\\"))
                    or "\\" in artifact
                    or any(part in ("", ".", "..") for part in artifact_parts)):
                raise RuntimeConfigurationError(
                    f"runtime {name!r} artifactPath must stay inside the project")
            values["artifactPath"] = artifact.strip()
        for key in ("buildTimeout", "runTimeout"):
            if key in values and (not isinstance(values[key], int) or values[key] < 1):
                raise RuntimeConfigurationError(f"runtime {name!r} {key} must be positive")
        return cls(MappingProxyType(values))

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def to_dict(self) -> dict:
        output = {}
        for key, value in self.values.items():
            if isinstance(value, Mapping):
                output[key] = {name: list(argv) if isinstance(argv, tuple) else argv
                               for name, argv in value.items()}
            elif isinstance(value, tuple):
                output[key] = list(value)
            else:
                output[key] = value
        return output


class RuntimeConfigRepository:
    def __init__(self, directory: str) -> None:
        self.directory = os.path.realpath(directory)

    @classmethod
    def from_root(cls, root: str) -> "RuntimeConfigRepository":
        return cls(os.path.join(root, "global-configs", "runtimes"))

    def load_defaults(self, name: str) -> dict:
        if not name or not _ID.fullmatch(str(name)):
            raise RuntimeConfigurationError(f"invalid runtime name {name!r}")
        path = find_runtime_profile(self.directory, str(name))
        if not path:
            return {}
        try:
            with open(path, "rb") as handle:
                value = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeConfigurationError(f"cannot load runtime {name!r}: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeConfigurationError(f"runtime {name!r} must be a TOML table")
        return value

    def resolve(self, override: Mapping[str, object] | None) -> RuntimeConfig:
        values = dict(override or {})
        values.setdefault("name", DEFAULT_RUNTIME)
        defaults = self.load_defaults(str(values["name"]))
        forbidden = sorted(key for key in _TRUSTED_ASSESSMENT_KEYS if key in values)
        if forbidden:
            raise RuntimeConfigurationError(
                "tome runtime overrides cannot grant assessment host access: "
                + ", ".join(forbidden))
        return RuntimeConfig.parse({**defaults, **values})

    def names(self) -> tuple[str, ...]:
        names = []
        for _base, directories, files in os.walk(self.directory):
            directories[:] = sorted(
                child for child in directories if not child.startswith("."))
            names.extend(name[:-5] for name in files
                         if name.endswith(".toml") and _ID.fullmatch(name[:-5]))
        return tuple(sorted(names))
