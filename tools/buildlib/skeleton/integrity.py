"""Language-agnostic Phase-1/2 contracts for artifact ownership and graph depth."""
from __future__ import annotations

import re


CONTRACT_MARKER = "Skeleton integrity contract"
CONTRACT_VERSION = 3
SUPPORTED_VERSIONS = tuple(range(1, CONTRACT_VERSION + 1))
# Keep Phase-1 artifact identifiers representable by proof-v1's project-path contract:
# non-empty POSIX segments, no leading/trailing or doubled slash, and no dot traversal.
ARTIFACT_RE = re.compile(
    r"(?!.*(?:^|/)\.{1,2}(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\Z")
WORKING_RE = re.compile(r"s\d{2}\.working\Z")
RETIRE_RE = re.compile(r"retires@(s\d{2})\Z")
PACKAGE_PROMISE_RE = re.compile(
    r"\b(?:standalone\s+(?:application|app|binary|build|executable|program|tool)|"
    r"packag(?:e|es|ed|ing)\s+(?:(?:a|an|the)\s+)?"
    r"(?:artifact|application|app|binary|build|executable|program|project|tool)|"
    r"distribut(?:able|ion)|installer|app\s+bundle)\b|\blanguage-(?:packag|distribut)",
    re.I)


def _package_promise_scope(text):
    """Exclude machine-owned calibration prose from delivery classification.

    A complete build plan necessarily explains that packaged or distributable
    outcomes require package mode.  Treating that instruction as an authored
    promise made every runtime Arc fail only when the Phase-1 transition seeded
    the course map.  Full plans are therefore classified from their authored Arc;
    callers that already pass an Arc body retain the same behavior.
    """
    value = str(text or "")
    match = re.search(r"(?im)^## Arc(?:\s.*)?$", value)
    return value[match.end():] if match else value


def _promises_package(text):
    return bool(PACKAGE_PROMISE_RE.search(_package_promise_scope(text)))


def contract_version(text):
    match = re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*([0-9]+)\s*$",
        str(text or ""))
    return int(match.group(1)) if match and int(match.group(1)) in SUPPORTED_VERSIONS else 0


def required_by_plan(text):
    return bool(contract_version(text))


def _field(text, label):
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(\S.*)$", str(text or ""))
    return match.group(1).strip() if match else ""


def _block(text, label):
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(.*)$", str(text or ""))
    if not match:
        return ""
    tail = re.split(r"(?m)^\*\*[^\n]+:\*\*", str(text)[match.end():], 1)[0]
    return (match.group(1) + "\n" + tail).strip()


def lifecycle_inventory(text):
    """Return v2's exact backtick-delimited lifecycle artifacts."""
    block = _block(text, "Artifact lifecycle")
    artifacts, problems = [], []
    if not block:
        return artifacts, ["**Artifact lifecycle:** is missing"]
    for raw in re.findall(r"`([^`]+)`", block):
        artifact = raw.strip()
        if not ARTIFACT_RE.fullmatch(artifact):
            problems.append(
                f"Artifact lifecycle backtick token {artifact!r} is not a stable artifact; "
                "reserve backticks in this field for inventory artifacts")
        elif artifact in artifacts:
            problems.append(f"Artifact lifecycle repeats artifact {artifact!r}")
        else:
            artifacts.append(artifact)
    if not artifacts:
        problems.append(
            "Artifact lifecycle must backtick every stable artifact from Artifact ownership")
    return artifacts, problems


def artifact_inventory(text):
    """Parse an exhaustive one-line learner-owned artifact inventory.

    Syntax is intentionally independent of any programming language or toolchain:
    ``path @ sNN.working -> ships`` or
    ``path @ sNN.working -> retires@sNN``.
    """
    raw = _field(text, "Artifact ownership")
    if not raw:
        return [], ["**Artifact ownership:** is missing"]
    records, problems, seen = [], [], set()
    pattern = re.compile(
        r"^(`?[A-Za-z0-9._/-]+`?)\s*@\s*(s\d{2}\.working)\s*->\s*"
        r"(ships|retires@s\d{2})$", re.I)
    for raw_clause in raw.split(";"):
        clause = raw_clause.strip()
        match = pattern.fullmatch(clause)
        if not match:
            problems.append(
                f"invalid artifact ownership clause {clause!r}; expected "
                "`path @ sNN.working -> ships|retires@sNN`")
            continue
        artifact, owner, disposition = match.groups()
        artifact = artifact.strip("`")
        owner, disposition = owner.lower(), disposition.lower()
        if not ARTIFACT_RE.fullmatch(artifact):
            problems.append(
                f"artifact {artifact!r} must be a stable relative path or identifier")
        if artifact in seen:
            problems.append(f"artifact ownership contains duplicate {artifact!r}")
        seen.add(artifact)
        record = {"artifact": artifact, "ownerWorking": owner,
                  "disposition": "ships" if disposition == "ships" else "retires"}
        retired = RETIRE_RE.fullmatch(disposition)
        if retired:
            record["retireBy"] = retired.group(1)
        records.append(record)
    return records, problems


def delivery_contract(text):
    """Parse the immutable, language-neutral final-delivery selection."""
    raw = _field(text, "Delivery contract")
    if not raw:
        return None, ["**Delivery contract:** is missing"]
    match = re.fullmatch(
        r"mode\s*=\s*(runtime|package)\s*;\s*artifact\s*=\s*(\S+)\s*;\s*"
        r"requirements\s*=\s*(\S+)", raw, re.I)
    if not match:
        return None, [
            "Delivery contract must be exactly `mode = runtime|package; "
            "artifact = path; requirements = path|none`"]
    mode, artifact, requirements = match.groups()
    mode = mode.lower()
    requirements = None if requirements.lower() == "none" else requirements
    problems = []
    if not ARTIFACT_RE.fullmatch(artifact):
        problems.append("Delivery contract artifact must be a stable relative path")
    if requirements is not None and not ARTIFACT_RE.fullmatch(requirements):
        problems.append("Delivery contract requirements must be a stable relative path or none")
    if mode == "package" and requirements is None:
        problems.append("package delivery requires an explicit requirements path")
    if mode == "runtime" and requirements is not None:
        problems.append("runtime delivery must use requirements = none")
    return {"mode": mode, "artifact": artifact, "requirements": requirements}, problems


def phase1_problems(text, body, section_ids):
    if not required_by_plan(text):
        return []
    records, problems = artifact_inventory(body)
    order = {sid: index for index, sid in enumerate(section_ids)}
    for index, record in enumerate(records):
        label = f"artifact ownership clause {index + 1}"
        owner_sid = record["ownerWorking"].split(".", 1)[0]
        if owner_sid not in order:
            problems.append(f"{label} names unknown owner {record['ownerWorking']}")
        if record["disposition"] == "retires":
            target = record.get("retireBy")
            if target not in order:
                problems.append(f"{label} names unknown retirement section {target}")
            elif owner_sid in order and order[target] <= order[owner_sid]:
                problems.append(f"{label} must retire in a section after its owner")
    ownership_is_well_formed = not problems
    if records and not any(item["disposition"] == "ships" for item in records):
        problems.append("artifact ownership must declare at least one shipped learner artifact")
    if contract_version(text) >= 2:
        if records and ownership_is_well_formed:
            for sid in section_ids:
                section_index = order[sid]
                available = []
                for record in records:
                    owner_sid = record["ownerWorking"].split(".", 1)[0]
                    if order[owner_sid] > section_index:
                        continue
                    if (record["disposition"] == "retires"
                            and order[record["retireBy"]] <= section_index):
                        continue
                    available.append(record["artifact"])
                if not available:
                    problems.append(
                        f"Artifact ownership cannot populate {sid}.working: every Working "
                        "needs at least one learner-owned artifact, but none is legally "
                        "available (owned at or before this section and not yet retired)")
        lifecycle, lifecycle_problems = lifecycle_inventory(body)
        problems.extend(lifecycle_problems)
        declared = {item["artifact"] for item in records}
        lifecycle_set = set(lifecycle)
        missing = sorted(declared - lifecycle_set)
        extra = sorted(lifecycle_set - declared)
        if missing:
            problems.append("Artifact lifecycle omits owned artifacts: " + ", ".join(missing))
        if extra:
            problems.append("Artifact lifecycle names artifacts absent from ownership: "
                            + ", ".join(extra))
    if contract_version(text) >= 3:
        delivery, delivery_problems = delivery_contract(body)
        problems.extend(delivery_problems)
        if delivery:
            shipped = {item["artifact"] for item in records
                       if item["disposition"] == "ships"}
            delivery_paths = {delivery["artifact"]}
            if delivery["requirements"]:
                delivery_paths.add(delivery["requirements"])
            missing = sorted(delivery_paths - shipped)
            if missing:
                problems.append(
                    "Delivery contract paths must be declared `ships` in Artifact ownership: "
                    + ", ".join(missing))
            if _promises_package(body) and delivery["mode"] != "package":
                problems.append(
                    "the Arc promises packaging or standalone distribution, so Delivery "
                    "contract mode must be package; remove the promise or package the artifact")
    return problems


def seed_contract(text):
    if not required_by_plan(text):
        return None
    records, problems = artifact_inventory(text)
    if problems:
        raise ValueError("invalid artifact ownership: " + "; ".join(problems))
    version = contract_version(text)
    contract = {"version": version, "artifacts": records}
    if version >= 3:
        delivery, delivery_problems = delivery_contract(text)
        if delivery_problems:
            raise ValueError("invalid delivery contract: " + "; ".join(delivery_problems))
        shipped = {item["artifact"] for item in records
                   if item["disposition"] == "ships"}
        delivery_paths = {delivery["artifact"]}
        if delivery["requirements"]:
            delivery_paths.add(delivery["requirements"])
        missing = sorted(delivery_paths - shipped)
        if missing:
            raise ValueError(
                "invalid delivery contract: paths must be shipped artifacts: "
                + ", ".join(missing))
        if _promises_package(text) and delivery["mode"] != "package":
            raise ValueError(
                "invalid delivery contract: packaging promise requires package mode")
        contract["delivery"] = delivery
    return contract


def _contract_shape_problems(contract):
    if not isinstance(contract, dict):
        return ["artifactContract must be an object"]
    problems = []
    version = contract.get("version")
    expected_keys = ({"version", "artifacts", "delivery"}
                     if version == 3 else {"version", "artifacts"})
    if set(contract) != expected_keys:
        keys = ", ".join(sorted(expected_keys))
        problems.append(f"artifactContract version {version!r} must contain exactly {keys}")
    if version not in SUPPORTED_VERSIONS:
        problems.append(
            f"artifactContract.version must be one of {list(SUPPORTED_VERSIONS)}")
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return problems + ["artifactContract.artifacts must be a non-empty array"]
    seen = set()
    for index, record in enumerate(artifacts):
        label = f"artifactContract.artifacts[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{label} must be an object")
            continue
        disposition = record.get("disposition")
        expected = ({"artifact", "ownerWorking", "disposition", "retireBy"}
                    if disposition == "retires" else
                    {"artifact", "ownerWorking", "disposition"})
        if set(record) != expected:
            problems.append(f"{label} has invalid keys for disposition {disposition!r}")
        artifact = record.get("artifact")
        if not isinstance(artifact, str) or not ARTIFACT_RE.fullmatch(artifact):
            problems.append(f"{label}.artifact must be a stable relative path or identifier")
        elif artifact in seen:
            problems.append(f"artifactContract contains duplicate {artifact!r}")
        seen.add(artifact)
        if not WORKING_RE.fullmatch(str(record.get("ownerWorking") or "")):
            problems.append(f"{label}.ownerWorking must be sNN.working")
        if disposition not in ("ships", "retires"):
            problems.append(f"{label}.disposition must be ships or retires")
        if disposition == "retires" and not re.fullmatch(r"s\d{2}", str(record.get("retireBy") or "")):
            problems.append(f"{label}.retireBy must be sNN")
    if version == 3:
        delivery = contract.get("delivery")
        label = "artifactContract.delivery"
        if not isinstance(delivery, dict):
            problems.append(f"{label} must be an object")
        else:
            if set(delivery) != {"mode", "artifact", "requirements"}:
                problems.append(
                    f"{label} must contain exactly mode, artifact, and requirements")
            mode = delivery.get("mode")
            artifact = delivery.get("artifact")
            requirements = delivery.get("requirements")
            if mode not in ("runtime", "package"):
                problems.append(f"{label}.mode must be runtime or package")
            if not isinstance(artifact, str) or not ARTIFACT_RE.fullmatch(artifact):
                problems.append(f"{label}.artifact must be a stable relative path")
            if requirements is not None and (
                    not isinstance(requirements, str)
                    or not ARTIFACT_RE.fullmatch(requirements)):
                problems.append(f"{label}.requirements must be a stable relative path or null")
            if mode == "package" and requirements is None:
                problems.append(f"{label}.requirements is required for package mode")
            if mode == "runtime" and requirements is not None:
                problems.append(f"{label}.requirements must be null for runtime mode")
            shipped = {item.get("artifact") for item in artifacts
                       if isinstance(item, dict) and item.get("disposition") == "ships"}
            delivery_paths = {item for item in (artifact, requirements) if item is not None}
            missing = sorted(delivery_paths - shipped)
            if missing:
                problems.append(
                    f"{label} paths must be shipped artifacts: " + ", ".join(missing))
    return problems


def contract_problems(contract, sections, detailed):
    """Reconcile the immutable inventory with every sealed Working."""
    problems = _contract_shape_problems(contract)
    if problems or not detailed:
        return problems
    sections = [item for item in sections if isinstance(item, dict)]
    order = {section.get("id"): index for index, section in enumerate(sections)}
    workings = {}
    for section in sections:
        for node in section.get("nodes") or []:
            if isinstance(node, dict) and node.get("kind") == "working":
                workings[node.get("id")] = set(node.get("learnerOwnedArtifacts") or [])
    declared = {item["artifact"] for item in contract["artifacts"]}
    actual = {artifact for artifacts in workings.values() for artifact in artifacts}
    undeclared = sorted(actual - declared)
    if undeclared:
        problems.append("Working learnerOwnedArtifacts are absent from Artifact ownership: "
                        + ", ".join(undeclared))
    final_working = workings.get(f"{sections[-1].get('id')}.working", set()) if sections else set()
    for record in contract["artifacts"]:
        artifact, owner = record["artifact"], record["ownerWorking"]
        owner_sid = owner.split(".", 1)[0]
        if owner not in workings:
            problems.append(f"artifact {artifact!r} names missing owner Working {owner}")
            continue
        if artifact not in workings[owner]:
            problems.append(f"{owner}.learnerOwnedArtifacts must introduce declared {artifact!r}")
        if contract.get("version", 1) >= 2 and owner_sid in order:
            for sid, section_index in order.items():
                if section_index >= order[owner_sid]:
                    continue
                if artifact in workings.get(f"{sid}.working", set()):
                    problems.append(
                        f"artifact {artifact!r} appears in {sid}.working before declared owner {owner}")
        if record["disposition"] == "ships":
            if artifact not in final_working:
                problems.append(
                    f"final Working learnerOwnedArtifacts must retain shipped {artifact!r}")
            continue
        target = record.get("retireBy")
        if target not in order:
            problems.append(f"artifact {artifact!r} retires in unknown section {target!r}")
            continue
        if owner_sid not in order or order[target] <= order[owner_sid]:
            problems.append(f"artifact {artifact!r} must retire after its owner Working")
            continue
        for sid, section_index in order.items():
            if section_index >= order[target] and artifact in workings.get(f"{sid}.working", set()):
                problems.append(
                    f"artifact {artifact!r} must be absent from {sid}.working at/after {target}")
    return problems


def phase2_alignment_problems(contract, plan_text, manifest, sections):
    """Reconcile the sealed plan with runtime and executable proof artifacts."""
    if not isinstance(contract, dict) or contract.get("version", 1) < 2:
        return []
    problems = []
    declared = {item.get("artifact") for item in contract.get("artifacts") or []
                if isinstance(item, dict)}
    shipped = {item.get("artifact") for item in contract.get("artifacts") or []
               if isinstance(item, dict) and item.get("disposition") == "ships"}
    lifecycle, lifecycle_problems = lifecycle_inventory(plan_text)
    problems.extend(lifecycle_problems)
    if set(lifecycle) != declared:
        missing = sorted(declared - set(lifecycle))
        extra = sorted(set(lifecycle) - declared)
        if missing:
            problems.append("Artifact lifecycle omits sealed artifacts: " + ", ".join(missing))
        if extra:
            problems.append("Artifact lifecycle has unsealed artifacts: " + ", ".join(extra))
    required = set()
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else {}
    entry_file = runtime.get("entryFile") if isinstance(runtime, dict) else None
    if isinstance(entry_file, str) and entry_file.strip():
        required.add(entry_file.strip())
    for section in sections:
        if not isinstance(section, dict):
            continue
        proof = section.get("proof")
        if not isinstance(proof, dict):
            continue
        required.update(item for item in proof.get("expectedFiles") or []
                        if isinstance(item, str) and item.strip()
                        and not re.search(r"(?:replace[-_ ]?me|todo|fixme)", item, re.I))
        if proof.get("mode") == "package":
            for key in ("requirementsFile", "artifactPath"):
                value = proof.get(key)
                if isinstance(value, str) and value.strip():
                    required.add(value.strip())
    if contract.get("version", 1) >= 3:
        delivery = contract.get("delivery") if isinstance(contract.get("delivery"), dict) else {}
        mode = delivery.get("mode")
        artifact = delivery.get("artifact")
        requirements = delivery.get("requirements")
        acceptance = manifest.get("acceptance") if isinstance(manifest, dict) else {}
        acceptance_artifact = (acceptance.get("artifact")
                               if isinstance(acceptance, dict) else None)
        if acceptance_artifact != mode:
            problems.append(
                "[acceptance].artifact must exactly preserve Phase-1 Delivery contract mode "
                f"{mode!r}; got {acceptance_artifact!r}")
        final_proof = ((sections[-1].get("proof") or {})
                       if sections and isinstance(sections[-1], dict) else {})
        if mode == "runtime":
            if entry_file != artifact:
                problems.append(
                    "[runtime].entryFile must exactly preserve Phase-1 runtime delivery "
                    f"artifact {artifact!r}; got {entry_file!r}")
        elif mode == "package":
            if final_proof.get("mode") != "package":
                problems.append(
                    "final section proof mode must be package because Phase 1 selected "
                    "package delivery")
            for key, expected in (("artifactPath", artifact),
                                  ("requirementsFile", requirements)):
                if final_proof.get(key) != expected:
                    problems.append(
                        f"final package proof {key} must exactly preserve Phase-1 value "
                        f"{expected!r}; got {final_proof.get(key)!r}")
        if isinstance(artifact, str):
            required.add(artifact)
        if requirements:
            required.add(requirements)
    missing_required = sorted(required - shipped)
    if missing_required:
        problems.append(
            "runtime/proof artifacts must be declared `ships` in Artifact ownership: "
            + ", ".join(missing_required))
    return problems


def graph_problems(sections, detailed):
    """Require an explicit chronological node chain for new strict skeletons."""
    if not detailed:
        return []
    problems = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        sid = section.get("id")
        if section_index and not section.get("dependsOn"):
            problems.append(f"{sid}.dependsOn must name an earlier section")
        lessons = [node for node in section.get("nodes") or []
                   if isinstance(node, dict) and node.get("kind") == "lesson"]
        working = next((node for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("kind") == "working"), None)
        for lesson_index, lesson in enumerate(lessons):
            dependencies = set(lesson.get("dependsOn") or [])
            if section_index == 0 and lesson_index == 0:
                continue
            if not dependencies:
                problems.append(f"{lesson.get('id')}.dependsOn must name earlier prerequisite evidence")
            if lesson_index:
                previous = lessons[lesson_index - 1].get("id")
                if previous not in dependencies:
                    problems.append(
                        f"{lesson.get('id')}.dependsOn must include previous lesson {previous}")
        if working and lessons and lessons[-1].get("id") not in set(working.get("dependsOn") or []):
            problems.append(
                f"{working.get('id')}.dependsOn must include final lesson {lessons[-1].get('id')}")
    return problems
