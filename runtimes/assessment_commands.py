"""Trusted runtime command-reference resolution for learner assessment."""
from __future__ import annotations


def _sub(argv, **subs):
    out = []
    for argument in argv:
        for key, value in subs.items():
            argument = argument.replace("{" + key + "}", value)
        out.append(argument)
    return out


def resolve(runtime, command_ref, project_dir, args=()):
    if command_ref == "build":
        argv = list(runtime.build_cmd)
        if not argv and runtime.check_cmd:
            raise ValueError("per-file check runtimes need a declared assessment build command")
    elif command_ref == "run":
        return runtime.project_command(project_dir, args)
    else:
        argv = list(runtime.assessment_commands.get(command_ref) or [])
    if not argv:
        raise ValueError(f"runtime has no registered assessment command {command_ref!r}")
    safe_args = []
    for argument in args or ():
        if not isinstance(argument, str) or any(ord(char) < 32 for char in argument):
            raise ValueError(f"invalid assessment argument {argument!r}")
        safe_args.append(argument)
    return [*_sub(argv, dir=project_dir, entry=runtime.entry), *safe_args]
