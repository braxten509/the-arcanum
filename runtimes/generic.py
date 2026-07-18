"""The ONE runtime engine. Every language is declared entirely in TOML —
global-configs/runtimes/<name>.toml holds the language's defaults, and a tome's
[runtime] table overrides any key. No per-language .py modules exist; commands,
placeholders, and regex diagnostics cover interpreted AND compiled languages.

Config keys (every key is optional unless marked REQUIRED):

  name = "python"             # runtime id; also names the snippet scratch dir
  language = "Python"         # display name, used in grader/oracle prompts
  command = ["python3"]       # runs ONE file. REQUIRED unless runCommand is set.
                              # The file is appended, or use a "{file}" placeholder
                              # for languages with trailing flags:
                              #   ["odin", "run", "{file}", "-file"]
  entryFile = "main.py"       # the file command runs / the default scaffold writes
  starterCode = "..."         # entry-file contents written by the default scaffold
  newFileExt = ".py"          # default extension for the NEW FILE button
  editorLang = "python"       # Monaco language id (any id — unknown ids get a
                              # generated tokenizer, see web/editor.js)
  codeExt = [".py", ".md"]    # extensions collected for grading/the editor
  excludeDirs = ["vendor"]    # extra dirs skipped while collecting (dot-dirs and
                              # common build/dependency dirs are always skipped)

  # --- syntax checking / editor squiggles (use one; omit both = no squiggles)
  checkCommand = ["..."]      # per-FILE check; file appended or "{file}"; exit 0 = clean
  buildCommand = ["..."]      # whole-PROJECT compile/check, run with cwd = project dir
  diagRegex = '...'           # named groups (?P<file>) (?P<line>) (?P<col>) (?P<sev>)
                              # (?P<code>) (?P<msg>) pulled from check/build output via
                              # re.finditer(..., re.M); every group is optional

  # --- projects (the workbench); the defaults cover interpreted languages
  runCommand = ["..."]        # run the whole project, cwd = project dir; "{dir}" and
                              # "{entry}" substituted. Default: command + entryFile
  scaffoldCommand = ["..."]   # create a project; "{project}" and "{dir}" substituted.
                              # Default: write entryFile containing starterCode
  projectFile = "..."         # file that marks a scaffolded project ("{project}"
                              # substituted, e.g. "{project}.csproj"). Default: entryFile
  packageCommand = ["..."]    # install a package; "{dir}" and "{package}" substituted.
                              # Default: package installs unsupported
  validationDependencies = [] # tome-only packages required to validate authored code
  validationProjectPackageCommand = ["..."]
                              # optional per-scratch-project installer; defaults to
                              # packageCommand when validationPackageCommand is absent
  validationCreateCommand = ["..."]
  validationPackageCommand = ["..."]
  validationEnv = { PATH = "{dir}/bin:{PATH}" }
                              # shared harness-only environment provisioning; these
                              # keys never alter the learner project or host runtime
  deliveryCreateCommand = ["..."]
  deliveryResolveCommand = ["..."] # optional fast dependency compatibility check
  deliveryInstallCommand = ["..."] # may use {cache} for reusable downloads/builds
  deliveryBuildCommand = ["..."]
                              # final package proof: fresh environment, exact requirements,
                              # then real packager argv. See runtimes/delivery.py.
  snippetRunCommand = ["..."] # run a snippet after buildCommand (e.g. dotnet's
                              # --no-build). Default: command + entryFile, else runCommand

  buildTimeout = 180          # s, for buildCommand / scaffoldCommand
  runTimeout = 60             # s, for project runs (snippets are capped separately)
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

from . import common, launch_probe

SNIPPET_MAX = 20000
RUN_TIMEOUT = 60
MAX_FILES = 400  # collect_code cap — keeps external workspaces from flooding the grader

# always skipped while collecting code, on top of dot-dirs and [runtime] excludeDirs
EXCLUDE_DIRS = {"node_modules", "__pycache__", "venv", "bin", "obj", "build", "out", "target"}


def _sub(argv, **subs):
    """Substitute {key} placeholders through an argv."""
    out = []
    for a in argv:
        for k, v in subs.items():
            a = a.replace("{" + k + "}", v)
        out.append(a)
    return out


def _file_argv(argv, path):
    """Substitute a {file} placeholder anywhere in the argv, else append the path."""
    if any("{file}" in a for a in argv):
        return [a.replace("{file}", path) for a in argv]
    return [*argv, path]


class CommandRuntime:
    def __init__(self, cfg):
        self.NAME = cfg.get("name") or "custom"
        self.LANGUAGE = cfg.get("language") or self.NAME
        self.cmd = list(cfg.get("command") or [])
        self.run_cmd = list(cfg.get("runCommand") or [])
        self.snippet_run_cmd = list(cfg.get("snippetRunCommand") or [])
        self.build_cmd = list(cfg.get("buildCommand") or [])
        self.check_cmd = list(cfg.get("checkCommand") or [])
        self.scaffold_cmd = list(cfg.get("scaffoldCommand") or [])
        self.package_cmd = list(cfg.get("packageCommand") or [])
        self.validation_dependencies = list(cfg.get("validationDependencies") or [])
        self.validation_shared_environment = bool(cfg.get("validationPackageCommand"))
        project_package = cfg.get("validationProjectPackageCommand") or []
        if not project_package and not cfg.get("validationPackageCommand"):
            project_package = self.package_cmd
        self.validation_project_package_cmd = list(project_package)
        self.diag_re = cfg.get("diagRegex") or ""
        self.entry = cfg.get("entryFile") or "main.txt"
        self.starter = cfg.get("starterCode") or ""
        self.project_file_tpl = cfg.get("projectFile") or self.entry
        self.exclude_dirs = set(cfg.get("excludeDirs") or [])
        self.build_timeout = cfg.get("buildTimeout") or 180
        self.run_timeout = cfg.get("runTimeout") or RUN_TIMEOUT
        ext = cfg.get("newFileExt") or os.path.splitext(self.entry)[1] or ".txt"
        self.CODE_EXT = tuple(cfg.get("codeExt") or (ext, ".md", ".txt", ".json"))

    def _exe(self):
        for argv in (self.cmd, self.run_cmd, self.build_cmd):
            if argv:
                return argv[0]
        return None

    def available(self):
        exe = self._exe()
        return bool(exe and shutil.which(exe))

    # ------------------------------------------------------------- project
    def project_file(self, project_name):
        return self.project_file_tpl.replace("{project}", project_name)

    def scaffold(self, project_dir, project_name):
        if os.path.isfile(os.path.join(project_dir, self.project_file(project_name))):
            return "already exists"
        os.makedirs(project_dir, exist_ok=True)
        if self.scaffold_cmd:
            p = subprocess.run(_sub(self.scaffold_cmd, project=project_name, dir=project_dir),
                               capture_output=True, text=True, timeout=self.build_timeout)
            if p.returncode != 0:
                raise RuntimeError(p.stdout + p.stderr)
            return "created"
        common.atomic_write(os.path.join(project_dir, self.entry), self.starter)
        return "created"

    def required_files(self, project_name):
        """The minimum files a fresh project of this runtime needs — the markers the
        scaffold would place. Used to seed a student's own folder and to list what a
        project must contain. entryFile always; the project marker (e.g. a .csproj)
        when it differs from the entry file."""
        files = [self.entry]
        pf = self.project_file(project_name)
        if pf != self.entry and pf not in files:
            files.append(pf)
        return files

    def _scaffold_to(self, target_dir, project_name):
        """Run the scaffold command into target_dir (already exists). Raises on failure."""
        p = subprocess.run(_sub(self.scaffold_cmd, project=project_name, dir=target_dir),
                           capture_output=True, text=True, timeout=self.build_timeout)
        if p.returncode != 0:
            raise RuntimeError(p.stdout + p.stderr)

    def seed_workspace(self, project_dir, project_name, force=False, only_missing=False):
        """Place this tome's starter files into project_dir (a student's own folder).
        Non-destructive by default: if any required file already exists and neither
        force nor only_missing is set, seed nothing and report which required files are
        present vs. missing so the caller can choose. force overwrites everything;
        only_missing adds just the absent files, never touching the ones present."""
        os.makedirs(project_dir, exist_ok=True)
        required = self.required_files(project_name)
        existing = [f for f in required if os.path.isfile(os.path.join(project_dir, f))]
        missing = [f for f in required if f not in existing]
        if existing and not force and not only_missing:
            return {"ok": False, "conflicts": existing, "missing": missing, "seeded": []}
        if only_missing and not missing:
            return {"ok": True, "conflicts": existing, "missing": [], "seeded": []}

        if self.scaffold_cmd:  # e.g. `dotnet new console` — emits entry + project file together
            if only_missing:
                # scaffold into a throwaway dir, copy ONLY the absent required files back,
                # so an existing entry/project file the student edited is left untouched
                tmp = tempfile.mkdtemp()
                try:
                    self._scaffold_to(tmp, project_name)
                    seeded = []
                    for f in missing:
                        src = os.path.join(tmp, f)
                        if os.path.isfile(src):
                            dst = os.path.join(project_dir, f)
                            os.makedirs(os.path.dirname(dst) or project_dir, exist_ok=True)
                            shutil.copyfile(src, dst)
                            seeded.append(f)
                    return {"ok": True, "conflicts": existing, "missing": missing, "seeded": seeded}
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            self._scaffold_to(project_dir, project_name)  # fresh / force: --force overwrites
            return {"ok": True, "conflicts": existing, "missing": missing, "seeded": required}

        # entry-file runtime: the entry file is the only required file
        if not only_missing or self.entry in missing:
            common.atomic_write(os.path.join(project_dir, self.entry), self.starter)
            return {"ok": True, "conflicts": existing, "missing": missing, "seeded": [self.entry]}
        return {"ok": True, "conflicts": existing, "missing": missing, "seeded": []}

    def starter_content(self, project_name, rel):
        """The content the scaffold would place in a given required file — for showing a
        student the starter code to copy into their own editor. entry-file runtimes return
        starterCode; scaffold-command runtimes generate the project once and read it back."""
        if not self.scaffold_cmd:
            return self.starter if rel == self.entry else ""
        tmp = tempfile.mkdtemp()
        try:
            self._scaffold_to(tmp, project_name)
            f = os.path.join(tmp, rel)
            if os.path.isfile(f):
                with open(f, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            return ""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def collect_code(self, project_dir):
        files = []
        skip = EXCLUDE_DIRS | self.exclude_dirs
        for dirpath, dirnames, filenames in os.walk(project_dir):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in skip)
            for fn in sorted(filenames):
                if fn.endswith(self.CODE_EXT):
                    if len(files) >= MAX_FILES:
                        return files
                    p = os.path.join(dirpath, fn)
                    try:
                        with open(p, encoding="utf-8", errors="replace") as f:
                            files.append((os.path.relpath(p, project_dir), f.read()))
                    except OSError:
                        pass
        return files

    # --------------------------------------------------------- diagnostics
    def _parse_diags(self, out, base, default_file):
        """diagRegex finditer over compiler/checker output → diagnostic dicts."""
        if not self.diag_re:
            return []
        diags, seen = [], set()
        for m in re.finditer(self.diag_re, out, re.M):
            g = m.groupdict()
            f = g.get("file") or default_file
            if os.path.isabs(f):
                f = os.path.relpath(f, base)
            key = (f, g.get("line"), g.get("col"), g.get("code"), g.get("msg"))
            if key in seen:
                continue
            seen.add(key)
            diags.append({"file": f, "line": int(g.get("line") or 1), "col": int(g.get("col") or 1),
                          "sev": g.get("sev") or "error", "code": g.get("code") or "check",
                          "msg": (g.get("msg") or "").strip() or "error"})
        return diags

    def _check_file(self, path, rel, env=None):
        """Run checkCommand on one file → list of diagnostics (empty = clean)."""
        try:
            p = subprocess.run(_file_argv(self.check_cmd, path), env=env,
                               capture_output=True, text=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError) as e:
            return [{"file": rel, "line": 1, "col": 1, "sev": "error", "code": "check", "msg": str(e)}]
        if p.returncode == 0:
            return []
        out = (p.stdout + "\n" + p.stderr).strip()
        diags = self._parse_diags(out, os.path.dirname(path) or ".", rel)
        for d in diags:
            d["file"] = rel  # the check ran on this one file, whatever the output called it
        return diags or [{"file": rel, "line": 1, "col": 1, "sev": "error", "code": "check",
                          "msg": out[-500:] or "check failed"}]

    def try_build(self, project_dir):
        if self.build_cmd:
            if not os.path.isdir(project_dir) or not self.available():
                return "(no build attempted: project or toolchain missing)"
            try:
                with common.project_lock:
                    p = subprocess.run(self.build_cmd, cwd=project_dir, capture_output=True,
                                       text=True, timeout=self.build_timeout)
                return (p.stdout + p.stderr).strip() or "(build produced no output — success)"
            except subprocess.TimeoutExpired:
                return "(build timed out)"
            except OSError as e:
                return f"(build failed to start: {e})"
        if not self.check_cmd:
            return "(this runtime has no build step)"
        problems = []
        for rel, _ in self.collect_code(project_dir):
            if rel.endswith(self.CODE_EXT[0]):
                for d in self._check_file(os.path.join(project_dir, rel), rel):
                    problems.append(f"{d['file']}({d['line']},{d['col']}): error: {d['msg']}")
        return "\n".join(problems) or "(syntax OK — no errors)"

    def build_diagnostics(self, project_dir):
        if self.build_cmd:
            return {"ok": True, "diags": self._parse_diags(self.try_build(project_dir), project_dir, self.entry)}
        diags = []
        if self.check_cmd:
            for rel, _ in self.collect_code(project_dir):
                if rel.endswith(self.CODE_EXT[0]):
                    diags += self._check_file(os.path.join(project_dir, rel), rel)
        return {"ok": True, "diags": diags}

    # -------------------------------------------------------------- snippets
    def _snippet_dir(self, scratch_base):
        """Snippets run in the scratch dir; a scaffoldCommand runtime gets a real
        scaffolded project there (dotnet needs a .csproj even for one file)."""
        if not self.scaffold_cmd:
            os.makedirs(scratch_base, exist_ok=True)
            try:
                self._install_validation_project_dependencies(scratch_base)
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
                return scratch_base, "dependency install failed: " + str(e)[-500:]
            return scratch_base, None
        proj = os.path.join(scratch_base, "Snippet")
        try:
            self.scaffold(proj, "Snippet")
            self._install_validation_project_dependencies(proj)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            return proj, "scaffold failed: " + str(e)[-500:]
        return proj, None

    def _install_validation_project_dependencies(self, project_dir):
        """Install tome-only packages into this validator scratch project once."""
        if not self.validation_dependencies:
            return
        # Shared-environment ecosystems (Python venv, npm prefix, and similar) were
        # provisioned before this runtime was entered. Installing them again into every
        # snippet/project is both wrong and the source of the old /api/runsnippet failure.
        if self.validation_shared_environment:
            return
        if not self.validation_project_package_cmd:
            raise RuntimeError("validation dependencies are declared but this runtime has no "
                               "validation project package command")
        marker = os.path.join(project_dir, ".arcanum-validation-dependencies.json")
        wanted = json.dumps(self.validation_dependencies, separators=(",", ":"))
        try:
            with open(marker, encoding="utf-8") as handle:
                if handle.read() == wanted:
                    return
        except OSError:
            pass
        for dependency in self.validation_dependencies:
            if (not isinstance(dependency, str) or not dependency.strip()
                    or dependency.lstrip().startswith("-")
                    or any(ord(ch) < 32 for ch in dependency)):
                raise RuntimeError(f"invalid validation dependency {dependency!r}")
            p = subprocess.run(_sub(self.validation_project_package_cmd,
                                    dir=project_dir, package=dependency),
                               cwd=project_dir, capture_output=True, text=True, timeout=600)
            if p.returncode:
                raise RuntimeError((p.stdout + p.stderr)[-3000:])
        common.atomic_write(marker, wanted)

    def snippet_diagnostics(self, scratch_base, code, env=None):
        can = bool(self.build_cmd or self.check_cmd)
        if not can or len(code) > SNIPPET_MAX or not self.available():
            return {"ok": can, "diags": []}
        sdir, err = self._snippet_dir(scratch_base)
        if err:
            return {"ok": False, "diags": [], "output": err}
        with common.snippet_lock:
            if self.build_cmd:
                common.atomic_write(os.path.join(sdir, self.entry), code)
                try:
                    p = subprocess.run(self.build_cmd, cwd=sdir, env=env,
                                       capture_output=True, text=True, timeout=self.build_timeout)
                except (subprocess.TimeoutExpired, OSError):
                    return {"ok": False, "diags": []}
                output = p.stdout + p.stderr
                diags = [d for d in self._parse_diags(output, sdir, self.entry)
                         if d["file"].endswith(self.entry)]
                if p.returncode and not diags:
                    return {"ok": False, "diags": [],
                            "output": output.strip() or "scratch project build failed"}
                return {"ok": True, "diags": diags}
            path = os.path.join(sdir, "check-" + self.entry)
            common.atomic_write(path, code)
            return {"ok": True, "diags": self._check_file(path, self.entry, env=env)}

    def run_snippet(self, scratch_base, code, stdin_text, env=None):
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found."}
        if len(code) > SNIPPET_MAX:
            return {"ok": False, "output": "snippet too large"}
        sdir, err = self._snippet_dir(scratch_base)
        if err:
            return {"ok": False, "output": err}
        if self.snippet_run_cmd:
            argv = _sub(self.snippet_run_cmd, dir=sdir, entry=self.entry)
        elif self.cmd:
            argv = _file_argv(self.cmd, self.entry)
        else:
            argv = _sub(self.run_cmd, dir=sdir, entry=self.entry)
        try:
            with common.snippet_lock:
                common.atomic_write(os.path.join(sdir, self.entry), code)
                if self.build_cmd:
                    # build first with its own (generous) budget, so compile time never
                    # eats the execution cap — the run dies fast on an infinite loop
                    b = subprocess.run(self.build_cmd, cwd=sdir, env=env,
                                       capture_output=True, text=True, timeout=self.build_timeout)
                    if b.returncode != 0:
                        out = common.join_output(b.stdout, b.stderr)
                        return {"ok": False, "output": out or "(build failed)", "exit": b.returncode}
                p = subprocess.run(argv, cwd=sdir, env=env, input=stdin_text or "",
                                   capture_output=True, text=True, timeout=common.SNIPPET_TIMEOUT)
            out = common.join_output(p.stdout, p.stderr)
            return {"ok": p.returncode == 0, "output": out or "(no output)", "exit": p.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": f"(KILLED: exceeded {common.SNIPPET_TIMEOUT}s — infinite loop, or waiting for input the lab didn't provide?)"}
        except OSError as e:
            return {"ok": False, "output": f"(run failed to start: {e})"}

    # -------------------------------------------------------------- projects
    def project_command(self, project_dir, args=()):
        """Return the exact argv used for an ordinary project launch plus safe args."""
        if self.run_cmd:
            argv = _sub(self.run_cmd, dir=project_dir, entry=self.entry)
        else:
            argv = _file_argv(self.cmd, self.entry)
        safe_args = []
        for arg in args or ():
            if not isinstance(arg, str) or any(ord(ch) < 32 for ch in arg):
                raise ValueError(f"invalid project argument {arg!r}")
            safe_args.append(arg)
        return [*argv, *safe_args]

    def verify_project(self, project_dir, env=None):
        """Build/check a disposable project with a truthful return code and output."""
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found.",
                    "commands": []}
        try:
            if self.build_cmd:
                with common.project_lock:
                    p = subprocess.run(self.build_cmd, cwd=project_dir, env=env,
                                       capture_output=True, text=True,
                                       timeout=self.build_timeout)
                return {"ok": p.returncode == 0,
                        "output": common.join_output(p.stdout, p.stderr)
                                  or "(build produced no output)",
                        "exit": p.returncode, "commands": [list(self.build_cmd)]}
            if self.check_cmd:
                outputs, commands = [], []
                for rel, _source in self.collect_code(project_dir):
                    if not rel.endswith(self.CODE_EXT[0]):
                        continue
                    path = os.path.join(project_dir, rel)
                    command = _file_argv(self.check_cmd, path)
                    commands.append(command)
                    p = subprocess.run(command, cwd=project_dir,
                                       env=env, capture_output=True, text=True, timeout=30)
                    if p.returncode:
                        outputs.append(common.join_output(p.stdout, p.stderr))
                return {"ok": not outputs,
                        "output": "\n".join(outputs) or "(syntax/build check passed)",
                        "exit": 1 if outputs else 0, "commands": commands}
            return {"ok": True, "output": "(runtime has no separate build step)",
                    "exit": 0, "commands": []}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "(build timed out)", "commands": []}
        except OSError as exc:
            return {"ok": False, "output": f"(build failed to start: {exc})", "commands": []}

    def smoke_project(self, project_dir, stdin_text=None, env=None, timeout=None):
        return launch_probe.smoke_project(self, project_dir, stdin_text, env, timeout)

    def run_project(self, project_dir, stdin_text, args=(), env=None, timeout=None):
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found."}
        try:
            argv = self.project_command(project_dir, args)
        except ValueError as exc:
            return {"ok": False, "output": str(exc), "command": []}
        return common.run_cancellable(argv, stdin_text,
                                      timeout or self.run_timeout, cwd=project_dir, env=env)

    def add_package(self, project_dir, pkg):
        if not self.package_cmd:
            return {"ok": False, "output": f"package installation is not supported by the {self.NAME} runtime"}
        pkg = re.sub(r"[^A-Za-z0-9._-]", "", pkg or "")
        if not pkg:
            return {"ok": False, "output": "bad package name"}
        p = subprocess.run(_sub(self.package_cmd, dir=project_dir, package=pkg),
                           capture_output=True, text=True, timeout=300)
        return {"ok": p.returncode == 0, "output": (p.stdout + p.stderr)[-3000:]}
