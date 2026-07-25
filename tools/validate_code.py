#!/usr/bin/env python3
"""validate_code.py — keep source files and source directories navigable.

A file over 500 lines is a file nobody reads to the end. This walks the repo and
fails on any hand-written source file that crossed the line. One finding per
line, longest first.

    python3 tools/validate_code.py [path] [--max 500] [--max-files 10]

Exit 0 = clean. Exit 1 = at least one file or directory over a limit. Stdlib only.
Vendored and generated trees are skipped — we did not write them and will not
split them.

A file or directory that genuinely cannot be split without making the code worse
declares itself in `[limits]` of global-configs/architecture-policy.toml with its
own ceiling and a reason. The gate re-checks every declaration, so an escape that
stops being needed fails too and gets deleted instead of accumulating."""
import argparse
import os
import sys

EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".css", ".html", ".java", ".cs", ".sh")
# Vendored or machine-written trees, matched by name at any depth.
#
# "build" is deliberately absent. Skipping it by name at any depth silently
# exempted every hand-written tree that happened to share the name: tools/tests/
# build hid 17 files and 3 files over 500 lines from both gates for months.
# Real build output at the repository root is git-ignored and never walked.
SKIP = {".git", "node_modules", "__pycache__", "monaco", "fonts", "generated", "dist", "obj"}
DIRECTORY_COUNT_ROOT_SKIP = {
    "tome-authoring", "tome-workflow", "sounds", "tmp", "runtimes",
    "validator-failures",
}

HINT = """
To fix: split the file, don't shave it. Cut on the seams that are already there
(section comments, top-level blocks), give each piece its own file, and keep one
entry file that wires them together.

Then put the pieces in a directory named for what they are. Nest as deep as it
takes -- sub-sub-directories are encouraged wherever a flat folder stops telling
you where to look. A directory of twenty files is the same problem as a file of
two thousand lines.

    web/css/                        web/audio/
      tokens.css ...(x16)             core.js  synth.js  keys.js ...(x8)

    web/css/                        web/audio/
      base/tokens.css                 index.js         <- the entry file
      shell/hud.css                   core.js
      desk/table.css                  sources/synth.js
      views/lesson.css                cues/keys.js
      overlay/modal.css               cues/ambience.js

Cascade and import order still matter: moving a file changes its path, never its
place in the sequence that loads it.

If a file has no such seam -- a single control loop whose only split would pass
its callables through a dict -- declare it in [limits] of
global-configs/architecture-policy.toml with its own ceiling and a reason. That
is a judgement on the record, not a bypass: the gate fails again if the file
outgrows its declared ceiling or drops back under the global limit.""".strip()


def _walk(root, count_files=False):
    """Yield (base, files) for every included directory under ``root``."""
    for base, dirs, files in os.walk(root):
        is_root = os.path.abspath(base) == os.path.abspath(root)
        excluded = SKIP | DIRECTORY_COUNT_ROOT_SKIP if (is_root and count_files) else SKIP
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
        if is_root and count_files:
            continue
        yield base, files


def offenders(root, limit, exemptions=None):
    """Return (violations, honored) for source files over their effective limit.

    ``exemptions`` maps a repo-relative path to its declared ceiling. A file with
    a declaration is measured against that ceiling instead of ``limit``.
    """
    exemptions = exemptions or {}
    violations, honored = [], []
    for base, files in _walk(root):
        for name in files:
            if not name.endswith(EXTS):
                continue
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                n = sum(1 for _ in fh)
            rel = os.path.relpath(path, root)
            ceiling = exemptions.get(rel)
            if ceiling is not None:
                if n > ceiling:
                    violations.append((n, rel, ceiling))
                else:
                    honored.append((n, rel, ceiling))
            elif n > limit:
                violations.append((n, rel, limit))
    return sorted(violations, reverse=True), sorted(honored, reverse=True)


def crowded_directories(root, limit, exemptions=None):
    """Return (violations, honored) for directories over their effective limit.

    Files in child directories never contribute to their parent's count. The
    repository root and explicitly excluded asset, generated, and authoring
    trees are outside this organization gate.
    """
    exemptions = exemptions or {}
    violations, honored = [], []
    for base, files in _walk(root, count_files=True):
        rel = os.path.relpath(base, root)
        ceiling = exemptions.get(rel)
        if ceiling is not None:
            (violations if len(files) > ceiling else honored).append(
                (len(files), rel, ceiling))
        elif len(files) > limit:
            violations.append((len(files), rel, limit))
    return sorted(violations, reverse=True), sorted(honored, reverse=True)


def stale_exemptions(root, honored_files, honored_dirs, file_limit, dir_limit,
                     declared_files, declared_dirs):
    """Report declarations that no longer earn their place.

    An escape is only defensible while the thing it describes still exists and
    still exceeds the global limit. Anything else is a bypass nobody reviewed.
    """
    out = []
    for rel, ceiling in sorted(declared_files.items()):
        target = os.path.join(root, rel)
        if not os.path.isfile(target):
            out.append(f"ERROR {rel}: declared in [[limits.oversizeFiles]] but the "
                       "file does not exist -- delete the declaration")
        elif ceiling <= file_limit:
            out.append(f"ERROR {rel}: declared ceiling {ceiling} is not above the "
                       f"{file_limit}-line limit -- the declaration does nothing")
    for n, rel, _ceiling in honored_files:
        if n <= file_limit:
            out.append(f"ERROR {rel}: {n} lines is back under the {file_limit}-line "
                       "limit -- delete its [[limits.oversizeFiles]] declaration")
    for rel, ceiling in sorted(declared_dirs.items()):
        if not os.path.isdir(os.path.join(root, rel)):
            out.append(f"ERROR {rel}: declared in [[limits.crowdedDirectories]] but "
                       "the directory does not exist -- delete the declaration")
        elif ceiling <= dir_limit:
            out.append(f"ERROR {rel}: declared ceiling {ceiling} is not above the "
                       f"{dir_limit}-file limit -- the declaration does nothing")
    for n, rel, _ceiling in honored_dirs:
        if n <= dir_limit:
            out.append(f"ERROR {rel}: {n} direct files is back under the {dir_limit}-file "
                       "limit -- delete its [[limits.crowdedDirectories]] declaration")
    return out


def _declarations(policy):
    """Read [limits] escapes, keyed by repo-relative path."""
    limits = policy.get("limits") or {}
    files, dirs = {}, {}
    for entry in limits.get("oversizeFiles") or []:
        if not entry.get("reason"):
            raise ValueError(
                f"[[limits.oversizeFiles]] {entry.get('path')!r} needs a reason")
        files[str(entry["path"])] = int(entry["maxLines"])
    for entry in limits.get("crowdedDirectories") or []:
        if not entry.get("reason"):
            raise ValueError(
                f"[[limits.crowdedDirectories]] {entry.get('path')!r} needs a reason")
        dirs[str(entry["path"])] = int(entry["maxFiles"])
    return files, dirs, limits


def main():
    ap = argparse.ArgumentParser(
        description="Fail on oversized source files or crowded source directories.")
    ap.add_argument("path", nargs="?", default=os.path.join(os.path.dirname(__file__), ".."),
                    help="tree to walk (default: the repo root)")
    ap.add_argument("--max", type=int, default=None, help="hard line limit (default: 500)")
    ap.add_argument("--max-files", type=int, default=None,
                    help="maximum direct files per included directory (default: 10)")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    architecture = ()
    declared_files, declared_dirs, limits = {}, {}, {}
    policy_path = os.path.join(root, "global-configs", "architecture-policy.toml")
    if os.path.isfile(policy_path):
        sys.path.insert(0, root)
        from tools.architecture.models import load_policy
        from tools.architecture.rules import check_all
        policy = load_policy(policy_path)
        declared_files, declared_dirs, limits = _declarations(policy)
        architecture = check_all(root, policy)

    file_limit = args.max if args.max is not None else int(limits.get("maxLines", 500))
    dir_limit = (args.max_files if args.max_files is not None
                 else int(limits.get("maxFilesPerDirectory", 10)))

    found, honored_files = offenders(root, file_limit, declared_files)
    crowded, honored_dirs = crowded_directories(root, dir_limit, declared_dirs)
    stale = stale_exemptions(root, honored_files, honored_dirs, file_limit, dir_limit,
                             declared_files, declared_dirs)

    for n, path, ceiling in found:
        print(f"ERROR {path}: {n} lines, {n - ceiling} over the {ceiling}-line limit")
    for n, path, ceiling in crowded:
        print(f"ERROR {path}: {n} direct files, "
              f"{n - ceiling} over the {ceiling}-file limit")
    for finding in architecture:
        print(finding.render())
    for line in stale:
        print(line)
    for n, path, ceiling in honored_files:
        print(f"note  {path}: {n} lines, declared limit {ceiling}")
    for n, path, ceiling in honored_dirs:
        print(f"note  {path}: {n} direct files, declared limit {ceiling}")
    print(f"-- {len(found)} file(s) over {file_limit} lines; "
          f"{len(crowded)} directory(s) over {dir_limit} direct files; "
          f"{len(architecture)} architecture violation(s); "
          f"{len(stale)} stale declaration(s); "
          f"{len(honored_files) + len(honored_dirs)} declared escape(s)")
    if found or crowded:
        print()
        print(HINT)
    sys.exit(1 if found or crowded or architecture or stale else 0)


if __name__ == "__main__":
    main()
