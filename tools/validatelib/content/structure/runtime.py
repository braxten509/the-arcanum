"""The [runtime] table: named-runtime resolution and the executable schema."""
import os
import re
import shutil

from ... import ID_RE, RUNTIMES_DIR, err, load_toml, rel, runtime_resolves, warn


def check_runtime(m, tome_id, label):
    rt = m.get("runtime")
    if not isinstance(rt, dict):
        err(label, "[runtime] table is missing")
        return
    name = rt.get("name") or "custom"  # matches the engine's default (generic.py NAME) when name is omitted
    runtime_name = str(name)
    if not ID_RE.fullmatch(runtime_name):
        err(label, f"[runtime] name {name!r} must match [A-Za-z0-9_-]+")
    runtime_path = os.path.join(RUNTIMES_DIR, runtime_name + ".toml")
    runtime_data = {}
    if not runtime_resolves(runtime_name):
        err(label, f"[runtime] name {name!r} has no global-configs/runtimes/{name}.toml — "
                   "every tome ships on a NAMED runtime file, so the language is reusable "
                   "and reviewable. CREATE that file now (zero code — command, checkCommand, "
                   "diagRegex, starterCode…; read tome-authoring/5-runtimes.md and copy the "
                   "shape of any existing global-configs/runtimes/*.toml), keeping only "
                   "tome-specific tweaks in this table")
    else:
        runtime_data, runtime_error = load_toml(runtime_path)
        if runtime_error:
            err(rel(runtime_path), runtime_error)
            runtime_data = {}
    merged = {**(runtime_data or {}), **rt}

    def source_label(key):
        return label if key in rt else rel(runtime_path)

    # Phase 2 and Phase 8 may author this shared config. Validate the generic runtime's
    # executable schema here, before a malformed value reaches list(), re.compile(), or
    # os.path.join() inside the live engine.
    command_keys = ("command", "runCommand", "buildCommand", "checkCommand",
                    "scaffoldCommand", "packageCommand", "snippetRunCommand",
                    "validationCreateCommand", "validationPackageCommand",
                    "validationProjectPackageCommand", "deliveryCreateCommand",
                    "deliveryResolveCommand", "deliveryInstallCommand",
                    "deliveryBuildCommand")
    for key in command_keys:
        if key not in merged:
            continue
        value = merged[key]
        if (not isinstance(value, list)
                or any(not isinstance(arg, str) or not arg for arg in value)):
            err(source_label(key), f"[runtime] {key} must be an array of non-empty argv strings")
    for key in ("codeExt", "excludeDirs", "diagIgnore", "snippetFragmentIgnore",
                "commandTargetTools"):
        if key not in merged:
            continue
        value = merged[key]
        if (not isinstance(value, list)
                or any(not isinstance(item, str) or not item for item in value)):
            err(source_label(key), f"[runtime] {key} must be an array of non-empty strings")
    dependencies = merged.get("validationDependencies")
    if dependencies is not None:
        if (not isinstance(dependencies, list)
                or any(not isinstance(item, str) or not item.strip()
                       or item.lstrip().startswith("-")
                       or any(ord(ch) < 32 for ch in item) for item in dependencies)):
            err(source_label("validationDependencies"),
                "[runtime] validationDependencies must be an array of non-empty package strings")
        elif len(set(dependencies)) != len(dependencies):
            err(source_label("validationDependencies"),
                "[runtime] validationDependencies contains duplicate packages")
        elif dependencies and not (merged.get("validationPackageCommand")
                                   or merged.get("validationProjectPackageCommand")
                                   or merged.get("packageCommand")):
            err(label, "[runtime] validationDependencies are declared, but the named runtime "
                       "has no validationPackageCommand or scratch-project packageCommand")
    validation_env = merged.get("validationEnv")
    if (validation_env is not None
            and (not isinstance(validation_env, dict)
                 or any(not isinstance(key, str) or not key
                        or not isinstance(value, str)
                        for key, value in validation_env.items()))):
        err(source_label("validationEnv"),
            "[runtime] validationEnv must be a table of non-empty environment names to strings")
    for key in ("validationPackageCommand", "validationProjectPackageCommand"):
        value = merged.get(key)
        if (isinstance(value, list) and value and not any("{package}" in arg for arg in value)):
            err(source_label(key), f"[runtime] {key} must contain a {{package}} placeholder")
    for key, placeholder in (("deliveryCreateCommand", "{env}"),
                             ("deliveryResolveCommand", "{requirements}"),
                             ("deliveryInstallCommand", "{requirements}")):
        value = merged.get(key)
        if (isinstance(value, list) and value
                and not any(placeholder in arg for arg in value)):
            err(source_label(key), f"[runtime] {key} must contain a {placeholder} placeholder")
    for key in ("entryFile", "projectFile", "deliveryArtifact", "deliveryRequirements"):
        value = merged.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            err(source_label(key), f"[runtime] {key} must be a non-empty relative path")
            continue
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            err(source_label(key), f"[runtime] {key} must stay inside the learner project; "
                                   f"got {value!r}")
    has_delivery_artifact = "deliveryArtifact" in merged
    has_delivery_requirements = "deliveryRequirements" in merged
    if has_delivery_artifact != has_delivery_requirements:
        err(label, "[runtime] clean-staging declarations must provide both "
                   "deliveryArtifact and deliveryRequirements")
    if has_delivery_artifact and has_delivery_requirements:
        delivery_build = merged.get("deliveryBuildCommand") or []
        arguments = "\n".join(str(argument) for argument in delivery_build)
        missing = [placeholder for placeholder in ("{artifact}", "{env}")
                   if placeholder not in arguments]
        if missing:
            err(source_label("deliveryBuildCommand"),
                "[runtime] declares clean-location artifact staging, but "
                "deliveryBuildCommand does not consume " + " and ".join(missing))
    from buildlib.course.dependencies import delivery_build_cwd_problem
    delivery_cwd = delivery_build_cwd_problem(merged)
    if delivery_cwd:
        err(source_label("deliveryBuildCommand"), "[runtime] " + delivery_cwd)
    regex_keys = ("diagRegex", "snippetEntry", "snippetFragment", "snippetHoist",
                  "snippetFragmentSkip")
    for key in regex_keys:
        value = merged.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            err(source_label(key), f"[runtime] {key} must be a regex string")
            continue
        try:
            re.compile(value, re.M)
        except re.error as exc:
            err(source_label(key), f"[runtime] {key} is not a valid Python regex: {exc}")
    for key in ("diagIgnore", "snippetFragmentIgnore"):
        value = merged.get(key)
        if not isinstance(value, list):
            continue  # the list-shape error above is already specific
        for index, pattern in enumerate(value):
            if not isinstance(pattern, str):
                continue
            try:
                re.compile(pattern, re.M)
            except re.error as exc:
                err(source_label(key), f"[runtime] {key}[{index}] is not a valid Python "
                                       f"regex: {exc}")
    for key in ("buildTimeout", "runTimeout", "deliveryTimeout"):
        value = merged.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                  or value <= 0):
            err(source_label(key), f"[runtime] {key} must be a positive integer number of seconds")

    if not (merged.get("command") or merged.get("runCommand")):
        err(label, f"[runtime] {name!r} sets neither command nor runCommand — nothing can run")
    # The named toolchain must exist on THIS host: a runtime whose binary isn't installed
    # validates green and then every lab run dies in front of the student.
    extra = os.pathsep.join(os.path.expanduser(p) for p in
                            ("~/.local/bin", "~/.cargo/bin", "/usr/local/bin", "/usr/bin"))
    seen = set()
    for key in ("command", "runCommand", "buildCommand", "checkCommand", "scaffoldCommand",
                "validationCreateCommand", "validationPackageCommand",
                "validationProjectPackageCommand", "deliveryCreateCommand",
                "deliveryResolveCommand", "deliveryInstallCommand",
                "deliveryBuildCommand"):
        v = merged.get(key)
        exe = v[0] if isinstance(v, list) and v and isinstance(v[0], str) else None
        if not exe or exe in seen or "{" in exe:
            continue
        seen.add(exe)
        if not shutil.which(exe, path=os.environ.get("PATH", "") + os.pathsep + extra):
            err(label, f"[runtime] {key} runs {exe!r} but it is not installed on this host — "
                       "install the toolchain or point the runtime file at one that exists")
    if "workspaceDir" in rt:
        warn(label, "[runtime] workspaceDir is removed — a tome never hardwires the "
                    "project location. Use externalWorkspace = true to REQUIRE external "
                    "mode; the student always chooses the folder", phase=2)
    xw = rt.get("externalWorkspace")
    if xw is not None and not isinstance(xw, bool):
        err(label, "[runtime] externalWorkspace must be a boolean (true to require external mode)")
    if xw is True and not str(rt.get("projectFile", "")).strip():
        warn("content", "[runtime] externalWorkspace = true but no projectFile — the workbench's "
             "required-files panel falls back to the language default (e.g. a lone Main.java), "
             "misdescribing the real project; name its true build file (e.g. \"build.gradle\")",
             phase=2)
