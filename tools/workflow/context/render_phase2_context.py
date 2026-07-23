#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from buildlib import BUILD_DIR
from buildlib.course_map import _read_json, seed_path
from buildlib.course_map.author_spec import spec_root
from buildlib.phase2.research import ledger_path
from buildlib.phase2_audit import audit_path, phase2_authority
from arcanum.catalog.build_ids import resolve_working_id


def _toml(path):
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _command_demands(value, prefix=""):
    """Collect command-bearing runtime fields without assuming a toolchain."""
    demands = {}
    if not isinstance(value, dict):
        return demands
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        lowered = str(key).lower()
        if lowered == "command" or lowered.endswith("command") or lowered.endswith("commands"):
            if item not in (None, "", [], {}):
                demands[path] = item
        elif isinstance(item, dict):
            demands.update(_command_demands(item, path))
    return demands


def _runtime_demands(tome_id):
    manifest_path = REPO / "tomes" / tome_id / "tome.toml"
    manifest = _toml(manifest_path)
    runtime = manifest.get("runtime") or {}
    profile_name = str(runtime.get("name") or "")
    profile = _toml(REPO / "global-configs" / "runtimes" / f"{profile_name}.toml")
    merged = {**profile, **runtime}
    return {
        "profile": profile_name,
        "externalWorkspace": merged.get("externalWorkspace") is True,
        "projectFile": merged.get("projectFile") or "",
        "entryFile": merged.get("entryFile") or "",
        "commands": _command_demands(merged),
        "validationDependencies": list(merged.get("validationDependencies") or []),
        "acceptance": manifest.get("acceptance") or {},
    }


def main():
    parser = argparse.ArgumentParser(
        description="Render the bounded authoring context for Phase 2.")
    parser.add_argument("build_id", metavar="BUILD_ID")
    args = parser.parse_args()
    build_id = args.build_id
    plan_path = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    plan = Path(plan_path).read_text(encoding="utf-8")
    arc = re.split(r"(?m)^## Harness ground truth\b", plan, maxsplit=1)[0]
    tome_id = resolve_working_id(build_id, plan, str(REPO / "tomes"))
    seed = _read_json(seed_path(build_id))
    root = spec_root(build_id)
    runtime = _runtime_demands(tome_id)
    profile_name = runtime.get("profile") or ""
    profile_path = (REPO / "global-configs" / "runtimes" / f"{profile_name}.toml"
                    if re.fullmatch(r"[A-Za-z0-9_-]+", profile_name) else None)
    packet = {
        "buildId": build_id,
        "authority": phase2_authority(plan),
        "sealedLessonSpine": [
            {key: section.get(key) for key in ("id", "title", "promise", "lessonCount")
             if key in section}
            for section in seed.get("sections") or []
        ],
        "edit": {
            "course": os.path.relpath(os.path.join(root, "course.json"), REPO),
            "mechanisms": os.path.relpath(os.path.join(root, "mechanisms.json"), REPO),
            "obligations": os.path.relpath(os.path.join(root, "obligations.json"), REPO),
            "audit": os.path.relpath(audit_path(build_id), REPO),
            "sections": os.path.relpath(os.path.join(root, "sections"), REPO) + "/sNN.json",
            "research": os.path.relpath(ledger_path(build_id), REPO),
            "manifest": f"tomes/{tome_id}/tome.toml",
            "tomeSkeleton": f"tomes/{tome_id}",
            "runtimeProfile": (os.path.relpath(profile_path, REPO)
                               if profile_path is not None else ""),
        },
        "mechanicalObligations": {
            "runtime": runtime,
            "acceptanceScenarios": list(seed.get("acceptanceScenarios") or []),
            "artifactProductionRows": [
                {key: item.get(key) for key in
                 ("artifact", "ownerWorking", "disposition", "retireBy")
                 if key in item}
                for item in ((seed.get("artifactContract") or {}).get("artifacts") or [])
                if isinstance(item, dict)
            ],
            "mastery": {
                "standaloneLabCount": ((seed.get("masteryEvidence") or {})
                                       .get("standaloneLabCount", 0)),
                "workingVariantFamilyRule": "empty",
            },
            "requiredAudits": [
                "Give every mechanism exactly one language-neutral family and all concrete prerequisite mechanism ids.",
                "For audit version 2, give every mechanism productionDependsOn edges for the narrower concrete operations required to create an artifact; every artifact-production row must close over those edges.",
                "Map every taught capability to its concrete component mechanisms so the gate proves every component owner occurs no later than the capability claim.",
                "Map every planned continuity obligation to the concrete mechanisms its target Working must preserve.",
                "When a later Working retains any learner-owned artifact from an earlier Working, carry every earlier Working mechanism into the later Working mechanism list; extensions may add mechanisms but cannot silently drop inherited operations.",
                "Declare each failure path's status, branch, diagnostic, and cleanup mechanisms so the gate proves status-before-branch direction and rejects branches that depend on later diagnostics or cleanup.",
                "With external tooling, teach installation and diagnostic verification before the first project source edit/save lesson.",
                "A same-lesson prerequisite must share the family and precede its dependent in the ordered introduces list; cross-family prerequisites belong to earlier lessons.",
                "Keep every Working mechanism list transitively closed over those prerequisites.",
                "Map every declared artifact to one allowed production mode and concrete mechanism ids. Learner-written canonical source, configuration, data, and documentation are authored. Input policy is separate: authored has no artifact inputs, generated inputs are optional, and copied or packaged inputs are required.",
                "Trace every runtime, acceptance, proof, cleanup, and delivery command backward to owned mechanisms.",
                "At Starting level 1, use one pedagogical family per lesson. Related mechanisms may share it when they form one teach-practice-observe loop; never hide unrelated foundations under one family id.",
            ],
        },
    }
    print("PHASE 2 BOUNDED CONTEXT")
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    print("\nSEALED PHASE 1 ARC\n" + arc[-60000:])


if __name__ == "__main__":
    main()
