"""Versioned future-tome proof: structured teaching, replay, assets, and source links."""
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from tome_proof import (CODE_KINDS, MEDIA_EXTENSIONS, PROOF_MODES, STEP_MODES,
                        is_media_path, media_mentions, proof_enabled, safe_project_path)

from .. import REPO, _findings, err, rel, warn
from .contract import check_proof_contract
from .runtime import clear_evidence, replay


_CODE = re.compile(r"<pre><code(?P<attrs>[^>]*)>(?P<body>.*?)</code></pre>", re.S | re.I)
_KIND = re.compile(r"\bdata-kind\s*=\s*(['\"])([^'\"]+)\1", re.I)
_NOOP = re.compile(r"(?im)^\s*(?:pass|\.\.\.)\s*(?:#.*)?$|"
                   r"\b(?:implementation omitted|your code here)\b")
_AI_MEDIA = re.compile(
    r"\b(?:dall[- ]?e|midjourney|stable diffusion|text[- ]to[- ](?:image|music)|"
    r"ai[- ]generated\s+(?:art|asset|image|sprite|sound|music))\b|"
    r"(?:<svg\b|data:image/|pygame\.image\.save\s*\(|Image\.new\s*\(|"
    r"(?:cv2|imageio(?:\.v\d+)?)\.imwrite\s*\(|ImageDraw\.|svgwrite\.|"
    r"pygame\.sndarray\.make_sound\s*\(|pygame\.mixer\.Sound\s*\(\s*buffer\s*=|"
    r"(?:soundfile|sf|wavfile)\.write\s*\(|"
    r"wave\.open\s*\([^\n]{0,120}['\"]wb['\"])", re.I)
_CACHE = os.path.join(REPO, ".tome-build", "proof-link-cache.json")


def _text(value, minimum=8):
    return isinstance(value, str) and len(value.strip()) >= minimum


def _step_errors(step, where, seen):
    if not isinstance(step, dict):
        err(where, "artifact/reference step must be a TOML table")
        return False
    sid = step.get("id")
    if not _text(sid, 3):
        err(where, "every artifact/reference step needs a stable non-empty id")
    elif sid in seen:
        err(where, f"artifact/reference step id {sid!r} is duplicated")
    else:
        seen.add(sid)
    path = safe_project_path(step.get("path"))
    if not path:
        err(where, f"step {sid!r} needs a safe relative project path")
    elif is_media_path(path):
        err(where, f"step {sid!r} writes media {path!r}; AI-authored media is forbidden")
    mode = step.get("mode")
    if mode not in STEP_MODES:
        err(where, f"step {sid!r} mode must be one of {', '.join(sorted(STEP_MODES))}")
    if not _text(step.get("instruction"), 20):
        err(where, f"step {sid!r} needs a specific learner-visible instruction")
    if mode == "author":
        checks = step.get("checks")
        if any(key in step for key in ("content", "find", "preserves")):
            err(where, f"author step {sid!r} is a work order and may not contain solution content")
        if (not isinstance(checks, list) or not checks
                or not all(_text(check, 12) for check in checks)):
            err(where, f"author step {sid!r} needs one or more specific observable checks")
    if mode in ("write", "rewrite", "append") and not isinstance(step.get("content"), str):
        err(where, f"{mode} step {sid!r} needs string content")
    if mode == "rewrite" and step.get("preserves") != "all-active":
        err(where, f"rewrite step {sid!r} must declare preserves = 'all-active'")
    if mode == "replace" and (not _text(step.get("find"), 1)
                              or not isinstance(step.get("content"), str)):
        err(where, f"replace step {sid!r} needs non-empty find and string content")
    code = str(step.get("content") or "")
    if _NOOP.search(code):
        err(where, f"step {sid!r} contains a pass/ellipsis/omitted implementation")
    if _AI_MEDIA.search(code):
        err(where, f"step {sid!r} synthesizes or embeds media; teach human sourcing instead")
    return bool(path and mode in STEP_MODES)


def _check_lesson(section, lesson, where, step_ids, work_orders_only=False):
    lid = str(lesson.get("id") or "lesson")
    exercises = {str(ex.get("id")) for ex in (lesson.get("exercises") or [])
                 if isinstance(ex, dict)}
    teaches = lesson.get("teaches") or []
    introduces = lesson.get("introduces") or []
    taught_ids = [*teaches, *introduces]
    concepts = lesson.get("concepts") or []
    by_id = {}
    for concept in concepts:
        if not isinstance(concept, dict) or not _text(concept.get("id"), 3):
            err(where, f"{lid}: each [[lessons.concepts]] entry needs an id")
            continue
        cid = str(concept["id"])
        if cid in by_id:
            err(where, f"{lid}: concept evidence for {cid!r} is duplicated")
        by_id[cid] = concept
    for capability in taught_ids:
        concept = by_id.get(str(capability))
        if not concept:
            err(where, f"{lid}: teaches {capability!r} without matching structured concept evidence")
            continue
        for field in ("purpose", "anatomy", "example", "observable", "failure"):
            if not _text(concept.get(field), 12):
                err(where, f"{lid}: concept {capability!r} needs substantive {field}")
        if str(concept.get("practice") or "") not in exercises:
            err(where, f"{lid}: concept {capability!r} practice must name an exercise in this lesson")
    extras = set(by_id) - {str(item) for item in taught_ids}
    if extras:
        err(where, f"{lid}: concept evidence has ids not declared by teaches: {sorted(extras)}")

    steps = lesson.get("artifactSteps") or []
    for step in steps:
        if (work_orders_only and isinstance(step, dict)
                and step.get("mode") != "author"):
            err(where, f"{lid}: sealed course-map builds require every learner-visible "
                "artifactStep to use mode 'author'; replayable project solutions belong only "
                "in hidden freestyle.referenceSteps")
        _step_errors(step, where, step_ids)

    blocks = list(_CODE.finditer(str(lesson.get("body") or "")))
    for number, block in enumerate(blocks, 1):
        match = _KIND.search(block.group("attrs"))
        kind = match.group(2).strip().lower() if match else ""
        if kind not in CODE_KINDS:
            err(where, f"{lid}: code block {number} needs data-kind="
                       f"{'|'.join(sorted(CODE_KINDS))}")
    # Structured concept evidence and its named graded practice own the teaching proof. Some
    # design, diagnosis, and tool-procedure lessons legitimately need no code block, and an
    # optional project work order must never be used as a substitute for teaching evidence.


def _asset_sources(section, lesson_ids, where, urls):
    assets = section.get("assets") or []
    destinations = {}
    for asset in assets:
        if not isinstance(asset, dict):
            err(where, "each [[assets]] entry must be a table")
            continue
        aid = str(asset.get("id") or "")
        destination = safe_project_path(asset.get("destination"))
        if not _text(aid, 3):
            err(where, "each asset sourcing guide needs an id")
        if not destination or not is_media_path(destination):
            err(where, f"asset {aid!r} destination must be a relative media path")
        elif destination in destinations:
            err(where, f"asset destination {destination!r} is declared more than once")
        else:
            destinations[destination] = asset
        if str(asset.get("lesson") or "") not in lesson_ids:
            err(where, f"asset {aid!r} must name the lesson that shows its sourcing guide")
        if not _text(asset.get("kind"), 3):
            err(where, f"asset {aid!r} needs a kind such as sprite, sound, music, or font")
        for field in ("sourceGuidance", "licenseGuidance"):
            if not _text(asset.get(field), 8):
                err(where, f"asset {aid!r} needs substantive {field}")
        sources = asset.get("sources") or []
        if not isinstance(sources, list) or not sources:
            err(where, f"asset {aid!r} needs at least one human-selectable licensed source")
        for source in sources if isinstance(sources, list) else []:
            if not isinstance(source, dict):
                err(where, f"asset {aid!r} source must be an inline table")
                continue
            url = source.get("url")
            if not (_text(source.get("label"), 3) and _text(source.get("license"), 2)
                    and isinstance(url, str) and url.startswith("https://")):
                err(where, f"asset {aid!r} sources need label, https URL, and license")
            else:
                urls.add(url)
    authored = dict(section)
    authored.pop("assets", None)
    mentions = media_mentions(authored)
    declared = set(destinations)
    declared_names = {os.path.basename(path): path for path in declared}
    for mention in sorted(mentions):
        if mention not in declared and os.path.basename(mention) not in declared_names:
            err(where, f"media {mention!r} is used without a [[assets]] human-sourcing guide")
    for destination in sorted(declared):
        if (destination not in mentions
                and os.path.basename(destination) not in {os.path.basename(m) for m in mentions}):
            err(where, f"asset guide destination {destination!r} is never used in the section")
    authored_text = "\n".join(str(value) for value in _flatten(authored))
    if _AI_MEDIA.search(html.unescape(authored_text)):
        err(where, "course content invokes AI/media synthesis; assets must be sourced by the learner")


def _flatten(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten(item)


def _check_section(section, where, step_ids, urls, allow_guided=False,
                   work_orders_only=False):
    sid = str(section.get("id") or "section")
    proof = section.get("proof")
    if not isinstance(proof, dict):
        err(where, f"{sid}: future tome section needs a [proof] milestone")
        return
    mode = proof.get("mode")
    if mode not in PROOF_MODES:
        err(where, f"{sid}: proof mode must be one of {', '.join(sorted(PROOF_MODES))}")
    files = proof.get("expectedFiles")
    if not isinstance(files, list) or not files:
        err(where, f"{sid}: proof expectedFiles must name at least one project source/config file")
    for path in files if isinstance(files, list) else []:
        if not safe_project_path(path):
            err(where, f"{sid}: proof expected file {path!r} is not a safe relative path")
        elif is_media_path(path):
            err(where, f"{sid}: media {path!r} cannot be a machine-authored proof file")
    if mode == "run":
        args = proof.get("runArgs")
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            err(where, f"{sid}: run proof needs a non-empty string runArgs array")
        if not (_text(proof.get("expect"), 1) or _text(proof.get("expectRegex"), 1)):
            err(where, f"{sid}: run proof needs exact expect or expectRegex output")
        if proof.get("expectRegex"):
            try:
                re.compile(str(proof["expectRegex"]))
            except re.error as exc:
                err(where, f"{sid}: expectRegex does not compile: {exc}")
    if mode == "guided":
        if not allow_guided:
            err(where, f"{sid}: guided proof is allowed only for runtime.externalWorkspace; "
                       "ordinary and in-browser projects must use build or run")
        checks = proof.get("guidedChecks")
        if not isinstance(checks, list) or len(checks) < 2 or not all(_text(c, 12) for c in checks):
            err(where, f"{sid}: guided proof needs at least two deterministic guidedChecks")

    lessons = [lesson for lesson in (section.get("lessons") or []) if isinstance(lesson, dict)]
    lesson_ids = {str(lesson.get("id")) for lesson in lessons}
    for lesson in lessons:
        _check_lesson(section, lesson, where, step_ids, work_orders_only)
    freestyle = section.get("freestyle") or {}
    refs = freestyle.get("referenceSteps") if isinstance(freestyle, dict) else None
    if not isinstance(refs, list) or not refs:
        err(where, f"{sid}: freestyle needs hidden referenceSteps so its solution is replayable")
    for step in refs if isinstance(refs, list) else []:
        if isinstance(step, dict) and step.get("mode") == "author":
            err(where, f"{sid}: hidden referenceSteps must implement the solution; "
                       "mode 'author' is learner-visible work-order-only")
        _step_errors(step, where, step_ids)
    _asset_sources(section, lesson_ids, where, urls)


def _load_cache():
    try:
        with open(_CACHE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _probe_url(url):
    request = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Arcanum-Tome-Validator/1"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.status, ""
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Arcanum-Tome-Validator/1",
                                                                "Range": "bytes=0-0"})
                with urllib.request.urlopen(request, timeout=6) as response:
                    return response.status, ""
            except Exception as retry:
                return getattr(retry, "code", 0), str(retry)
        return exc.code, str(exc)
    except Exception as exc:
        return 0, str(exc)


def _check_links(urls):
    cache, now = _load_cache(), time.time()
    fresh = {url: item for url, item in cache.items()
             if isinstance(item, dict) and now - item.get("at", 0) < 86400}
    missing = sorted(set(urls) - set(fresh))
    with ThreadPoolExecutor(max_workers=min(8, len(missing) or 1)) as pool:
        for url, result in zip(missing, pool.map(_probe_url, missing)):
            fresh[url] = {"status": result[0], "error": result[1], "at": now}
    if missing:
        try:
            os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
            with open(_CACHE, "w", encoding="utf-8") as handle:
                json.dump(fresh, handle, separators=(",", ":"))
        except OSError:
            pass
    for url in sorted(urls):
        item = fresh.get(url) or {}
        status = int(item.get("status") or 0)
        if status in (404, 410):
            err("sources", f"required course/asset source is gone ({status}): {url}")
        elif not 200 <= status < 400:
            warn("advisory", f"source reachability could not be confirmed ({status or 'network'}): {url}")


def check_no_bundled_media(tome_path, manifest):
    """Reject media files/generators immediately, including in the relaxed Phase-2 gate."""
    if not proof_enabled(manifest):
        return
    authored_text = "\n".join(str(value) for value in _flatten(manifest))
    if _AI_MEDIA.search(html.unescape(authored_text)):
        err(rel(os.path.join(tome_path, "tome.toml")),
            "the tome/runtime scaffold invokes AI or procedural media synthesis; "
            "teach human sourcing instead")
    for mention in sorted(media_mentions(manifest)):
        err(rel(os.path.join(tome_path, "tome.toml")),
            f"the manifest/runtime scaffold depends on media {mention!r}; introduce it in a "
            "lesson with a human-sourcing guide and keep the initial scaffold asset-free")
    runtime_table = manifest.get("runtime")
    if isinstance(runtime_table, dict):
        try:
            from runtimes import resolve_config
            starter = str(resolve_config(runtime_table).get("starterCode") or "")
        except (OSError, TypeError, ValueError):
            starter = ""
        if _AI_MEDIA.search(html.unescape(starter)) or media_mentions(starter):
            err("runtime", "the selected global runtime starter creates, embeds, or depends "
                "on media; future-tome scaffolds must remain asset-free")
    for dirpath, dirs, names in os.walk(tome_path):
        dirs[:] = [name for name in dirs if name != "save"]
        for name in names:
            if os.path.splitext(name.lower())[1] in MEDIA_EXTENSIONS:
                err(rel(os.path.join(dirpath, name)),
                    "media file is bundled in a tome; publish a human-sourcing guide instead")


def _check_blank_learner_scaffold(manifest):
    """A sealed learner-construction course starts from an empty editor, not project code."""
    try:
        from runtimes import resolve_config
        config = resolve_config(manifest.get("runtime") or {})
    except (OSError, TypeError, ValueError) as exc:
        err("runtime", f"cannot verify the learner-owned blank scaffold: {exc}")
        return
    if str(config.get("starterCode") or "").strip():
        err("runtime", "course-map builds require an empty starterCode so the learner "
            "authors the canonical entry file; examples belong only in lesson teaching")
    if config.get("scaffoldCommand"):
        err("runtime", "course-map builds may not run a project-generating "
            "scaffoldCommand; the learner must assemble project structure and behavior")


def _authored_prefix(sections, run_section):
    """Return proof scope through ``run_section`` while later scaffolds stay untouched."""
    sections = list(sections)
    if not run_section:
        return sections
    target = str(run_section)
    for index, section in enumerate(sections):
        if str(section.get("id")) == target:
            return sections[:index + 1]
    return []


def check_future_tome_proof(tome_path, manifest, sections, run=False, run_section=None,
                            plan_path=None, source_only=False):
    """Validate and optionally replay proof-v1 tomes; do nothing for legacy tomes.

    A warm Phase-3 section gate owns the authored prefix only.  Phase-2 deliberately leaves
    later sections as structurally valid placeholders, so proof requirements must not turn
    those future scaffolds into blockers before their batch is writable.  The complete Phase-3
    and shipping gates omit ``run_section`` and therefore still inspect every section.
    """
    if not proof_enabled(manifest):
        return
    if run and not run_section:
        clear_evidence(tome_path)
    check_no_bundled_media(tome_path, manifest)
    proof_sections = _authored_prefix(sections, run_section)
    before, step_ids, urls = len(_findings), set(), set()
    runtime_config = manifest.get("runtime")
    allow_guided = (isinstance(runtime_config, dict)
                    and runtime_config.get("externalWorkspace") is True)
    course_map_build = False
    work_orders_only = False
    if plan_path:
        try:
            from buildlib.course_map import build_id_from_plan, map_path, proposal_path
            build_id = build_id_from_plan(plan_path)
            course_map_build = bool(build_id and (
                os.path.isfile(map_path(build_id)) or os.path.isfile(proposal_path(build_id))))
            work_orders_only = bool(build_id and os.path.isfile(map_path(build_id)))
        except (ImportError, ValueError):
            pass
    if course_map_build:
        _check_blank_learner_scaffold(manifest)
    for section in proof_sections:
        where = rel(os.path.join(tome_path, "sections", str(section.get("id") or "?")))
        _check_section(section, where, step_ids, urls, allow_guided=allow_guided,
                       work_orders_only=work_orders_only)
        for lesson in section.get("lessons") or []:
            for reading in lesson.get("readings") or [] if isinstance(lesson, dict) else []:
                url = reading.get("url") if isinstance(reading, dict) else None
                if isinstance(url, str) and url.startswith("https://"):
                    urls.add(url)
                else:
                    err(where, "future-tome readings must use reachable https URLs")
    declared = ((manifest.get("content") or {}).get("sections")
                if isinstance(manifest.get("content"), dict) else []) or []
    course_complete = (not run_section or (declared and str(run_section) ==
                                           str(declared[-1])))
    check_proof_contract(manifest, proof_sections, plan_path=plan_path,
                         allow_guided=allow_guided, course_complete=course_complete)
    if run and len(_findings) == before and not any(item[0] == "ERROR" for item in _findings):
        replay(tome_path, manifest, sections, run_section,
               persist=not bool(run_section), source_only=source_only)
    if run and not run_section and urls:
        _check_links(urls)
