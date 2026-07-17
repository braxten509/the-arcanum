#!/usr/bin/env python3
"""validate_code.py — keep source files and source directories navigable.

A file over 500 lines is a file nobody reads to the end. This walks the repo and
fails on any hand-written source file that crossed the line. One finding per
line, longest first.

    python3 tools/validate_code.py [path] [--max 500] [--max-files 8]

Exit 0 = clean. Exit 1 = at least one file or directory over a limit. Stdlib only.
Vendored and generated trees are skipped — we did not write them and will not
split them."""
import argparse
import os
import sys

EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".css", ".html", ".java", ".cs", ".sh")
SKIP = {
    ".git", "node_modules", "__pycache__", "monaco", "fonts", "generated", "dist",
    "build", "obj",
}
DIRECTORY_COUNT_ROOT_SKIP = {
    "tome-authoring", "tome-workflow", "sounds", "tmp", "runtimes",
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
place in the sequence that loads it.""".strip()


def offenders(root, limit):
    """Yield (lines, path) for each source file over `limit`, longest first."""
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for name in files:
            if not name.endswith(EXTS):
                continue
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                n = sum(1 for _ in fh)
            if n > limit:
                out.append((n, os.path.relpath(path, root)))
    return sorted(out, reverse=True)


def crowded_directories(root, limit):
    """Return direct-file counts for included non-root directories over ``limit``.

    Files in child directories never contribute to their parent's count. The
    repository root and explicitly excluded asset, generated, and authoring
    trees are outside this organization gate.
    """
    out = []
    for base, dirs, files in os.walk(root):
        is_root = os.path.abspath(base) == os.path.abspath(root)
        excluded = SKIP | DIRECTORY_COUNT_ROOT_SKIP if is_root else SKIP
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
        if is_root:
            continue
        if len(files) > limit:
            out.append((len(files), os.path.relpath(base, root)))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser(
        description="Fail on oversized source files or crowded source directories.")
    ap.add_argument("path", nargs="?", default=os.path.join(os.path.dirname(__file__), ".."),
                    help="tree to walk (default: the repo root)")
    ap.add_argument("--max", type=int, default=500, help="hard line limit (default: 500)")
    ap.add_argument("--max-files", type=int, default=8,
                    help="maximum direct files per included directory (default: 8)")
    args = ap.parse_args()

    found = offenders(os.path.abspath(args.path), args.max)
    crowded = crowded_directories(os.path.abspath(args.path), args.max_files)
    for n, path in found:
        print(f"ERROR {path}: {n} lines, {n - args.max} over the {args.max}-line limit")
    for n, path in crowded:
        print(f"ERROR {path}: {n} direct files, "
              f"{n - args.max_files} over the {args.max_files}-file limit")
    print(f"-- {len(found)} file(s) over {args.max} lines; "
          f"{len(crowded)} directory(s) over {args.max_files} direct files")
    if found or crowded:
        print()
        print(HINT)
    sys.exit(1 if found or crowded else 0)


if __name__ == "__main__":
    main()
