#!/usr/bin/env python3
"""Deterministic live HTTP smoke gate for a finished tome.

Exercises the real loader route, one authored reference solution through the real
runtime route, and the grader job/status lifecycle.  The grader request uses the
server's deterministic smoke mode, so validation never spends model tokens or depends
on a configured provider.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tome_layout
from validatelib import norm_lines


TOMES_ROOT = ROOT / "tomes"


class SmokeError(RuntimeError):
    pass


def _request(base_url, path, body=None, timeout=30):
    url = base_url.rstrip("/") + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = str(exc)
        raise SmokeError(f"{path} returned HTTP {exc.code}: {detail[:500]}") from exc
    except (OSError, ValueError) as exc:
        raise SmokeError(f"{path} could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"{path} returned a non-object JSON payload")
    if payload.get("error") and not payload.get("ok"):
        raise SmokeError(f"{path}: {payload['error']}")
    return payload


def _first_reference_lab(sections):
    for section in sections:
        for lesson in section.get("lessons") or []:
            for exercise in lesson.get("exercises") or []:
                if (exercise.get("type") == "write"
                        and str(exercise.get("solution") or "").strip()):
                    return section, lesson, exercise
    return None, None, None


def _authored_sections(tome_id):
    """Load trusted reference material without adding it to the learner payload."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tome_id or "")):
        raise SmokeError("installed tome id is invalid")
    tome_root = TOMES_ROOT / tome_id
    manifest_path = tome_root / "tome.toml"
    try:
        with manifest_path.open("rb") as handle:
            manifest = tomllib.load(handle)
        section_ids = (manifest.get("content") or {}).get("sections") or []
        return [tome_layout.load_section(str(tome_root), section_id)
                for section_id in section_ids]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SmokeError(f"trusted authored tome could not be loaded: {exc}") from exc


def _accepted(exercise, output):
    expected = exercise.get("expect")
    if isinstance(expected, str) and expected.strip():
        return norm_lines(output) == norm_lines(expected)
    pattern = exercise.get("expectRe")
    if isinstance(pattern, str) and pattern.strip():
        try:
            return bool(re.search(re.sub(r"\(\?<(?=[A-Za-z])", "(?P<", pattern),
                                  output, re.M))
        except re.error as exc:
            raise SmokeError(f"write lab {exercise.get('id')!r} has invalid expectRe: {exc}")
    return False


def smoke_tome(tome_id, base_url, timeout=30, poll_interval=0.1):
    query = urllib.parse.urlencode({"tome": tome_id})
    loaded = _request(base_url, f"/api/tome?{query}", timeout=timeout)
    sections = loaded.get("sections")
    if not isinstance(sections, list) or not sections:
        raise SmokeError("loader returned no sections")
    first = sections[0]
    lessons = first.get("lessons") or []
    if not lessons or not str(lessons[0].get("body") or "").strip():
        raise SmokeError(f"first section {first.get('id')!r} has no renderable lesson")

    section, lesson, lab = _first_reference_lab(_authored_sections(tome_id))
    if lab is None:
        raise SmokeError("no write lab carries a reference solution for runtime smoke testing")
    ran = _request(base_url, f"/api/runsnippet?{query}", {
        "tome": tome_id,
        "code": lab.get("solution") or "",
        "stdin": lab.get("stdin") or "",
    }, timeout=timeout)
    if not ran.get("ok"):
        raise SmokeError(f"write lab {lab.get('id')!r} failed through /api/runsnippet: "
                         f"{str(ran.get('output') or '')[:500]}")
    output = str(ran.get("output") or "")
    if not _accepted(lab, output):
        raise SmokeError(f"write lab {lab.get('id')!r} ran, but its live output did not "
                         "satisfy expect/expectRe")

    graded = _request(base_url, f"/api/grade?{query}", {
        "tome": tome_id, "smoke": True, "sectionId": section.get("id"),
    }, timeout=timeout)
    job_id = str(graded.get("jobId") or "")
    if not graded.get("ok") or not job_id:
        raise SmokeError("/api/grade did not start a smoke job")
    deadline = time.monotonic() + timeout
    terminal = None
    while time.monotonic() < deadline:
        status_query = urllib.parse.urlencode({"id": job_id, "tome": tome_id})
        status = _request(base_url, f"/api/grade/status?{status_query}", timeout=timeout)
        state = status.get("status")
        if state == "done":
            terminal = status
            break
        if state in ("error", "failed", "cancelled", "unknown"):
            raise SmokeError(f"grader smoke job ended as {state!r}: "
                             f"{status.get('error') or 'no diagnostic'}")
        time.sleep(poll_interval)
    if terminal is None:
        raise SmokeError(f"grader smoke job did not reach the API's `done` state within {timeout}s")
    if not ((terminal.get("result") or {}).get("smoke")):
        raise SmokeError("grader smoke job reached done without its deterministic result")

    return [
        f"loader assembled {len(sections)} section(s)",
        f"lesson {lessons[0].get('id') or '?'} rendered",
        f"write lab {lab.get('id') or '?'} passed through /api/runsnippet",
        "freestyle grader route reached status `done`",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smoke-test one installed tome through live HTTP routes.")
    parser.add_argument("tome", help="installed tome id")
    parser.add_argument("--base-url", default=None,
                        help="server origin (default: http://127.0.0.1:$ARCANUM_PORT)")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    base_url = args.base_url or f"http://127.0.0.1:{os.environ.get('ARCANUM_PORT', '8777')}"
    try:
        checks = smoke_tome(args.tome, base_url, max(1, args.timeout))
    except SmokeError as exc:
        print(f"ERROR live-smoke: {exc}")
        print(f"-- live smoke {args.tome}: 1 error(s)")
        return 1
    for check in checks:
        print(f"ok live-smoke: {check}")
    print(f"-- live smoke {args.tome}: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
