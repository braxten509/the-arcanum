"""Learner-safe public tome payload assembly."""
from __future__ import annotations

import glob
import os
import tomllib

import tome_layout
from tome_proof import public_section

def _read_toml(path: str) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def public_mastery_labs(tome_root: str) -> list[dict]:
    labs = []
    for path in sorted(glob.glob(os.path.join(
            tome_root, "sections", "*", "mastery-labs", "*.toml"))):
        try:
            raw = _read_toml(path)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        lab = dict(raw.get("masteryLab") or {})
        if not lab:
            continue
        labs.append({"masteryLab": lab,
                     "requirements": list(raw.get("requirements") or []),
                     "rubric": [{key: value for key, value in row.items()
                                  if key in {"id", "criterion", "weight", "kind"}}
                                 for row in raw.get("rubric") or []]})
    return labs


def list_skins(skins_root: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(skins_root, "*", "skin.toml"))):
        try:
            skin = _read_toml(path)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        skin["id"] = os.path.basename(os.path.dirname(path))
        out.append(skin)
    return out


def assemble_public_tome(manifest: dict, tome_root: str, skins_root: str,
                         runtime_config: dict) -> dict:
    if not str((manifest.get("narrative") or {}).get("objective") or "").strip():
        tome_id = (manifest.get("meta") or {}).get("id") or os.path.basename(tome_root)
        raise ValueError(f"tome {tome_id!r}: [narrative] objective is required — "
                         "state what the whole tome builds toward (shown on the Operative File)")
    sections = [public_section(tome_layout.load_section(tome_root, section_id))
                for section_id in (manifest.get("content") or {}).get("sections", [])]
    attack_path = os.path.join(
        tome_root, (manifest.get("content") or {}).get("attacks", "generated/attacks.toml"))
    attacks = _read_toml(attack_path).get("tiers", []) if os.path.isfile(attack_path) else []
    payload = tome_layout.merge_banks(dict(manifest), tome_root)
    payload["runtime"] = runtime_config
    payload["sections"] = sections
    payload["masteryLabs"] = public_mastery_labs(tome_root)
    evidence_path = os.path.join(tome_root, "generated", "mastery-evidence.json")
    if os.path.isfile(evidence_path):
        import json
        with open(evidence_path, encoding="utf-8") as handle:
            payload["masteryEvidence"] = json.load(handle)
    payload["attacks"] = attacks
    payload["skins"] = list_skins(skins_root)
    return payload
