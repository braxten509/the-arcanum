"""Deterministic Phase-2 section scaffolding derived from the approved plan Arc."""
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

from .. import REPO
from ..course.limits import MAX_SECTIONS, MIN_SECTIONS, section_count_error


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
    if not MIN_SECTIONS <= len(specs) <= MAX_SECTIONS:
        raise ValueError(section_count_error(len(specs)))
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
    try:
        from new_tome import SECTION_TEMPLATE, render, roman
    except ModuleNotFoundError:  # imported by server.py as tools.buildlib.skeleton
        from tools.new_tome import SECTION_TEMPLATE, render, roman

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
    text = text.replace('[[lessons.concepts]]                # one complete first-use proof for every `teaches` id\n'
                        'id = "replace-me"',
                        '[[lessons.concepts]]                # one complete first-use proof for every `teaches` id\n'
                        f'id = {json.dumps(capability)}', 1)
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


SCAFFOLD_MARKER = "scaffolded by tools/new_tome.py"


def is_scaffold(section_dir):
    """True when a section directory is still an unauthored Phase-2 stub.

    Phase 2 fills the plan's title and promise but leaves the generator banner and the
    TODO markers; Phase 3 authoring rewrites the file and the banner goes with it.
    """
    try:
        with open(os.path.join(section_dir, "section.toml"), encoding="utf-8") as handle:
            return SCAFFOLD_MARKER in handle.read(4096)
    except OSError:
        return False


def _toml_array(values):
    return "[" + ", ".join(json.dumps(str(value), ensure_ascii=False)
                            for value in (values or [])) + "]"


def _replace_first_field(text, key, rendered):
    changed, count = re.subn(
        rf"(?m)^{re.escape(key)}\s*=\s*[^\n]+$", f"{key} = {rendered}", text, count=1)
    if count != 1:
        raise ValueError(f"section scaffold has no {key} field")
    return changed


def _insert_after_first_field(text, key, lines):
    match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*[^\n]+$", text)
    if not match:
        raise ValueError(f"section scaffold has no {key} field")
    return text[:match.end()] + "\n" + "\n".join(lines) + text[match.end():]


def _lesson_scaffold(template, node):
    """Bind one generic lesson template to its sealed Phase-2 node."""
    node_id = str(node["id"]).replace(".", "-")
    teaches = list(node.get("teaches") or [])
    introduces = list(node.get("introduces") or [])
    dependencies = list(node.get("validationDependencies") or [])
    text = re.sub(r"s\d{2}-l01", node_id, template)
    text = _replace_first_field(text, "id", json.dumps(node_id))
    text = _replace_first_field(
        text, "title", json.dumps("TODO: " + str(node.get("title") or node_id),
                                  ensure_ascii=False))
    text = _replace_first_field(text, "teaches", _toml_array(teaches))
    text = _insert_after_first_field(text, "teaches", (
        f"introduces = {_toml_array(introduces)}",
        f"validationDependencies = {_toml_array(dependencies)}",
    ))

    # Give every sealed capability/mechanism an explicit evidence slot. Phase 3
    # replaces the TODO prose and may distribute practices more finely, but it no
    # longer has to infer ids or lesson ownership from validator failures.
    concepts = []
    for concept_id in dict.fromkeys([*teaches, *introduces]):
        concepts.append(
            "[[lessons.concepts]]\n"
            f"id = {json.dumps(concept_id)}\n"
            "purpose = \"TODO: plain-language purpose.\"\n"
            "anatomy = \"TODO: read its parts or procedure in order.\"\n"
            "example = \"TODO: point to the complete worked example in this lesson.\"\n"
            "observable = \"TODO: what the learner sees when the example works.\"\n"
            "failure = \"TODO: one likely failure and how to recognize it.\"\n"
            f"practice = {json.dumps(node_id + '-e1')}\n")
    text, count = re.subn(
        r"(?s)\[\[lessons\.concepts\]\].*?(?=\[\[lessons\.readings\]\])",
        "\n".join(concepts) + "\n", text, count=1)
    if count != 1:
        raise ValueError("lesson scaffold has no concepts block")
    text = text.replace('capabilities = ["replace-me"]',
                        f"capabilities = {_toml_array(teaches)}")
    # The first guided exercise is the initial mechanical coverage slot. The
    # author is expected to distribute demands honestly while replacing TODOs.
    text = text.replace("cognitiveTask = \"predict\"",
                        f"mechanisms = {_toml_array(introduces)}\n"
                        "cognitiveTask = \"predict\"", 1)
    text = text.replace("cognitiveTask = \"explain\"",
                        "mechanisms = []\ncognitiveTask = \"explain\"", 1)
    text = text.replace("cognitiveTask = \"complete\"",
                        "mechanisms = []\ncognitiveTask = \"complete\"", 1)
    text = text.replace("cognitiveTask = \"recall\"",
                        "mechanisms = []\ncognitiveTask = \"recall\"", 1)
    text = text.replace("cognitiveTask = \"build\"",
                        "mechanisms = []\ncognitiveTask = \"build\"", 1)
    return text


def _working_scaffold(text, node):
    requires = list(node.get("requires") or [])
    mechanisms = list(node.get("mechanisms") or [])
    dependencies = list(node.get("validationDependencies") or [])
    mastery = list(node.get("masteryPerformances") or [])
    text = _replace_first_field(
        text, "title", json.dumps("THE WORKING: " + str(node.get("title") or "TODO"),
                                  ensure_ascii=False))
    text = _replace_first_field(text, "requires", _toml_array(requires))
    text = _insert_after_first_field(text, "requires", (
        f"mechanisms = {_toml_array(mechanisms)}",
        f"validationDependencies = {_toml_array(dependencies)}",
        f"masteryPerformances = {_toml_array(mastery)}",
    ))
    text = text.replace("instruction = \"TODO: exact private reference edit that satisfies "
                        "this Working.\"",
                        "mechanisms = " + _toml_array(mechanisms) + "\n"
                        "instruction = \"TODO: exact private reference edit that satisfies "
                        "this Working.\"")
    text = text.replace("kind = \"deterministic\"",
                        "kind = \"deterministic\"\nmechanisms = []")
    text = text.replace("kind = \"qualitative\"",
                        "kind = \"qualitative\"\nmechanisms = []")
    return text


def hydrate_section_scaffolds(tid, course, tomes_dir=None, only=None):
    """Materialize sealed lesson/Working obligations into untouched scaffolds.

    Authored sections are never changed. This runs after Phase 2 seals the map and
    is also used when a Phase-3 section reset rebuilds one fresh scaffold.
    """
    tomes_dir = tomes_dir or os.path.join(REPO, "tomes")
    wanted = set(only or [])
    hydrated = []
    for section in course.get("sections") or []:
        sid = str(section.get("id") or "")
        if not sid or (wanted and sid not in wanted):
            continue
        section_dir = os.path.join(tomes_dir, tid, "sections", sid)
        if not is_scaffold(section_dir):
            continue
        lessons = [node for node in section.get("nodes") or []
                   if node.get("kind") == "lesson"]
        working = next((node for node in section.get("nodes") or []
                        if node.get("kind") == "working"), None)
        lesson_dir = os.path.join(section_dir, "lessons")
        template_path = os.path.join(lesson_dir, "l01.toml")
        if not lessons or not working or not os.path.isfile(template_path):
            raise ValueError(f"{sid} sealed scaffold is missing lessons or Working")
        with open(template_path, encoding="utf-8") as handle:
            lesson_template = handle.read()
        with open(os.path.join(section_dir, "freestyle.toml"), encoding="utf-8") as handle:
            freestyle = handle.read()
        with open(os.path.join(section_dir, "section.toml"), encoding="utf-8") as handle:
            section_text = handle.read()
        section_text = section_text.replace(
            "mode = \"run\"", "mode = \"run\"\nmechanisms = []", 1)
        with open(os.path.join(section_dir, "section.toml"), "w", encoding="utf-8") as handle:
            handle.write(section_text)
        for name in os.listdir(lesson_dir):
            if name.endswith(".toml"):
                os.remove(os.path.join(lesson_dir, name))
        for index, node in enumerate(lessons, 1):
            with open(os.path.join(lesson_dir, f"l{index:02d}.toml"),
                      "w", encoding="utf-8") as handle:
                handle.write(_lesson_scaffold(lesson_template, node))
        with open(os.path.join(section_dir, "freestyle.toml"), "w", encoding="utf-8") as handle:
            handle.write(_working_scaffold(freestyle, working))
        assessment = os.path.join(section_dir, "assessment.toml")
        if not os.path.isfile(assessment):
            try:
                from scaffold import ASSESSMENT_TEMPLATE
            except ModuleNotFoundError:
                from tools.scaffold import ASSESSMENT_TEMPLATE
            with open(assessment, "w", encoding="utf-8") as handle:
                handle.write(ASSESSMENT_TEMPLATE.lstrip("\n"))
        research = os.path.join(section_dir, "research.toml")
        if not os.path.isfile(research):
            try:
                from scaffold import RESEARCH_TEMPLATE
            except ModuleNotFoundError:
                from tools.scaffold import RESEARCH_TEMPLATE
            with open(research, "w", encoding="utf-8") as handle:
                handle.write(RESEARCH_TEMPLATE.lstrip("\n"))
        hydrated.append(sid)
    return hydrated


def rebuild_section_scaffold(tid, sid, plan_path, tomes_dir=None, course=None):
    """Put one section back to its Phase-2 stub, leaving every other section alone.

    A Phase-3 restart has to clear authored prose without leaving the section empty: the
    author is told to read its scaffold, and with nothing there it goes looking for shape
    in whatever else is on disk. Rebuilding from the same plan Arc keeps that read local.

    ``tomes_dir`` is explicit because callers rebind their own tome root; deriving it from
    ``REPO`` here would write into the real repository instead.
    """
    tomes_dir = tomes_dir or os.path.join(REPO, "tomes")
    specs = read_section_list(plan_path)
    number, spec = next(((index, item) for index, item in enumerate(specs, 1)
                         if item.sid == sid), (0, None))
    if spec is None:
        raise ValueError(f"{sid} is not in the plan Arc at {plan_path}")
    try:
        from maintenance import split_tome
    except ModuleNotFoundError:  # imported by server.py as tools.buildlib.skeleton
        from tools.maintenance import split_tome
    sections_path = os.path.join(tomes_dir, tid, "sections")
    os.makedirs(tomes_dir, exist_ok=True)
    temp_root = tempfile.mkdtemp(prefix=f".{tid}-{sid}-scaffold-", dir=tomes_dir)
    old_quiet = split_tome.QUIET
    split_tome.QUIET = True
    try:
        os.makedirs(os.path.join(temp_root, "sections"))
        with open(os.path.join(temp_root, "sections", sid + ".toml"),
                  "w", encoding="utf-8") as handle:
            handle.write(_render_section(spec, number))
        split_tome.migrate_section(temp_root, sid)
        os.makedirs(sections_path, exist_ok=True)
        shutil.rmtree(os.path.join(sections_path, sid), ignore_errors=True)
        os.replace(os.path.join(temp_root, "sections", sid),
                   os.path.join(sections_path, sid))
    finally:
        split_tome.QUIET = old_quiet
        shutil.rmtree(temp_root, ignore_errors=True)
    if course:
        hydrate_section_scaffolds(tid, course, tomes_dir=tomes_dir, only=(sid,))
    return spec


def scaffold_sections(tid, plan_path, force=False, repo=REPO):
    """Replace a fresh tome's sections with one deterministic stub per Arc entry."""
    tome_path = os.path.join(repo, "tomes", tid)
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
        try:
            from maintenance import split_tome
        except ModuleNotFoundError:  # imported by server.py as tools.buildlib.skeleton
            from tools.maintenance import split_tome
        old_quiet = split_tome.QUIET
        split_tome.QUIET = True
        try:
            for number, spec in enumerate(specs, 1):
                flat = os.path.join(temp_sections, spec.sid + ".toml")
                with open(flat, "w", encoding="utf-8") as handle:
                    handle.write(_render_section(spec, number))
                split_tome.migrate_section(temp_root, spec.sid)
        finally:
            split_tome.QUIET = old_quiet

        _replace_manifest_sections(manifest_path, specs)
        shutil.rmtree(sections_path, ignore_errors=True)
        os.replace(temp_sections, sections_path)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return specs
