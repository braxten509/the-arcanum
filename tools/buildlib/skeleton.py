"""Deterministic Phase-2 section scaffolding derived from the approved plan Arc."""
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

from . import REPO


SECTION_LIST_LABEL = re.compile(r"(?im)^\*\*Section list:\*\*[^\n]*$")
SECTION_LINE = re.compile(
    r"^\s*(?P<number>\d+)[.)]\s+\*\*(?P<sid>s\d{2})\s+[—-]\s+"
    r"(?P<title>.+?):\*\*\s+(?P<promise>\S.+?)\s*$"
)


@dataclass(frozen=True)
class SectionSpec:
    sid: str
    title: str
    promise: str


def parse_section_list(text):
    """Parse the Arc's intentionally rigid, one-physical-line section blueprint."""
    match = SECTION_LIST_LABEL.search(str(text or ""))
    if not match:
        raise ValueError("the Arc has no `**Section list:**` label")
    specs = []
    for line in str(text)[match.end():].splitlines():
        stripped = line.strip()
        if stripped.startswith("**") and stripped.endswith("**"):
            break  # the next Arc/durable-decisions field
        entry = SECTION_LINE.fullmatch(line)
        if not entry:
            if stripped and re.match(r"^\d+[.)]\s", stripped):
                raise ValueError(
                    "malformed Section list entry; use one physical line exactly like "
                    "`1. **s01 — Title:** capability/build promise`")
            continue
        expected_number = len(specs) + 1
        expected_sid = f"s{expected_number:02d}"
        number = int(entry.group("number"))
        sid = entry.group("sid")
        if number != expected_number or sid != expected_sid:
            raise ValueError(
                f"Section list must be sequential: entry {expected_number} must be "
                f"`{expected_number}. **{expected_sid} — ...:**`, got {number}. **{sid}**")
        specs.append(SectionSpec(sid, entry.group("title").strip(),
                                 entry.group("promise").strip()))
    if not specs:
        raise ValueError("the Section list has no parseable entries")
    return specs


def read_section_list(plan_path):
    try:
        with open(plan_path, encoding="utf-8") as handle:
            return parse_section_list(handle.read())
    except OSError as exc:
        raise ValueError(f"could not read plan {plan_path}: {exc}") from exc


def _replace_manifest_sections(manifest_path, specs):
    with open(manifest_path, encoding="utf-8") as handle:
        lines = handle.readlines()
    rendered = "sections = [" + ", ".join(json.dumps(spec.sid) for spec in specs) + "]"
    in_content = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_content = stripped == "[content]"
        if in_content and re.match(r"^\s*sections\s*=", line):
            comment = ""
            if "#" in line:
                comment = "  #" + line.split("#", 1)[1].rstrip("\n")
            lines[index] = rendered + comment + "\n"
            replaced = True
            break
    if not replaced:
        raise ValueError(f"{manifest_path} has no [content] sections = [...] line")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


def _set_first(text, key, value):
    rendered = json.dumps(str(value), ensure_ascii=False)
    changed, count = re.subn(rf"(?m)^{re.escape(key)}\s*=\s*[^\n]+$",
                             f"{key} = {rendered}", text, count=1)
    if count != 1:
        raise ValueError(f"section template has no top-level {key} field")
    return changed


def _render_section(spec, number):
    # Reuse the same known-green schema as new_tome.py; the generator only supplies
    # plan facts and unique ids, leaving honest Phase-3 TODO markers in authored fields.
    from new_tome import SECTION_TEMPLATE, render, roman

    text = render(SECTION_TEMPLATE, {"SID": spec.sid, "ROMAN": roman(number)})
    text = _set_first(text, "codename", f"CHAPTER {roman(number)} // {spec.title.upper()}")
    text = _set_first(text, "short", spec.title)
    text = _set_first(text, "title", spec.title)
    text = _set_first(text, "build", spec.promise)
    text = _set_first(text, "brief", f"TODO: Phase 3 authors {spec.title} from the approved Arc.")
    capability = f"{spec.sid}-phase3-placeholder"
    text = text.replace('requires = ["replace-me"]',
                        f"requires = [{json.dumps(capability)}]", 1)
    text = text.replace('teaches = ["replace-me"]',
                        f"teaches = [{json.dumps(capability)}]", 1)
    text = text.replace('title = "TODO: lesson title"',
                        f"title = {json.dumps('TODO: Phase 3 lesson — ' + spec.title, ensure_ascii=False)}",
                        1)
    return text.lstrip("\n")


def _assert_replaceable(sections_path):
    if not os.path.isdir(sections_path):
        return
    authored = []
    for dirpath, _dirs, names in os.walk(sections_path):
        for name in names:
            if not name.endswith(".toml"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                continue
            if "TODO" not in text and "FIXME" not in text:
                authored.append(os.path.relpath(path, sections_path))
    if authored:
        shown = ", ".join(authored[:5])
        raise ValueError("refusing to replace section files that no longer look scaffolded: "
                         + shown + (" ..." if len(authored) > 5 else ""))


def scaffold_sections(tid, plan_path, force=False):
    """Replace a fresh tome's sections with one deterministic stub per Arc entry."""
    tome_path = os.path.join(REPO, "tomes", tid)
    manifest_path = os.path.join(tome_path, "tome.toml")
    if not os.path.isfile(manifest_path):
        raise ValueError(f"tomes/{tid}/tome.toml is missing")
    specs = read_section_list(plan_path)
    sections_path = os.path.join(tome_path, "sections")
    if not force:
        _assert_replaceable(sections_path)

    parent = os.path.dirname(tome_path)
    temp_root = tempfile.mkdtemp(prefix=f".{tid}-phase2-", dir=parent)
    try:
        temp_sections = os.path.join(temp_root, "sections")
        os.makedirs(temp_sections)
        from split_tome import migrate_section
        import split_tome
        old_quiet = split_tome.QUIET
        split_tome.QUIET = True
        try:
            for number, spec in enumerate(specs, 1):
                flat = os.path.join(temp_sections, spec.sid + ".toml")
                with open(flat, "w", encoding="utf-8") as handle:
                    handle.write(_render_section(spec, number))
                migrate_section(temp_root, spec.sid)
        finally:
            split_tome.QUIET = old_quiet

        _replace_manifest_sections(manifest_path, specs)
        shutil.rmtree(sections_path, ignore_errors=True)
        os.replace(temp_sections, sections_path)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return specs
