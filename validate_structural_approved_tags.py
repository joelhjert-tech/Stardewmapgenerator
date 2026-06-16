#!/usr/bin/env python3
"""Validate manually approved structural tile tags."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ijson

import approval_validation_utils as approval_utils
from mine_structural_tile_candidates import MISSING_ROLES, ROLE_CLASS_DEFAULTS


TOOL_ROOT = Path(__file__).resolve().parent
STRUCTURAL_ROOT = TOOL_ROOT / "structural_learning"
CANDIDATES_PATH = STRUCTURAL_ROOT / "candidates" / "structural_tile_candidates_by_role.json"
PATH_BASE_CANDIDATES_PATH = STRUCTURAL_ROOT / "path_base_review" / "path_base_candidates.json"
APPROVED_PATH = TOOL_ROOT / "classification" / "approved_tags" / "structural_manual_approved.approved_tags.json"
MINIMUM_APPROVED_PATH = TOOL_ROOT / "classification" / "approved_tags" / "minimum_structural_manual_approved.approved_tags.json"
PATH_BASE_APPROVED_PATH = TOOL_ROOT / "classification" / "approved_tags" / "path_base_manual_approved.approved_tags.json"
APPROVED_TAGS_DIR = TOOL_ROOT / "classification" / "approved_tags"
CANONICAL_CANDIDATES = TOOL_ROOT / "classification" / "canonical_tile_candidates.json"
CLASS_SCHEMA = TOOL_ROOT / "classification" / "tile_class_schema.json"
REPORT_PATH = TOOL_ROOT / "reports" / "structural_approval_validation_report.md"
MINIMUM_REPORT_PATH = TOOL_ROOT / "reports" / "minimum_structural_approval_validation_report.md"
PATH_BASE_REPORT_PATH = TOOL_ROOT / "reports" / "path_base_approval_validation_report.md"

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
VALID_COLLISIONS = {"unknown", "walkable", "blocked", "blocks", "blocked_or_special", "water_blocked", "decorative_front", "overlay_only", "marker_only", "custom_requires_review"}
BLOCKING_ROLES = {"wall_body", "wall_corner", "wall_edge"}
BLOCKING_COLLISIONS = {"blocked", "blocks", "water_blocked"}
RESTRICTED_TOKENS = {"deepwoods_custom_lake_tilesheet", "deepwoods_infested_outdoors_tilesheet", "deepwoods_exclusive_assets"}
EXTRA_ROLE_CLASS_DEFAULTS = {
    "path_base": ("path_base", "walkable_base_path", ["Back"], "walkable"),
}
ALL_ROLE_CLASS_DEFAULTS = {**ROLE_CLASS_DEFAULTS, **EXTRA_ROLE_CLASS_DEFAULTS}
ALL_ROLES = set(MISSING_ROLES) | set(EXTRA_ROLE_CLASS_DEFAULTS)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def tags_from_doc(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return doc
    return doc.get("tags", [])


def candidate_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if CANDIDATES_PATH.exists():
        doc = load_json(CANDIDATES_PATH)
        for role, items in doc.get("roles", {}).items():
            for item in items:
                item = dict(item)
                item["roleName"] = role
                for key in [item.get("candidateId"), item.get("structuralCandidateId")]:
                    if key:
                        lookup[key] = item
                for key in item.get("mappedCandidateIds") or []:
                    lookup[key] = item
    if PATH_BASE_CANDIDATES_PATH.exists():
        doc = load_json(PATH_BASE_CANDIDATES_PATH)
        for item in doc.get("candidates", []) or []:
            item = dict(item)
            item["roleName"] = "path_base"
            for key in [item.get("pathBaseCandidateId"), item.get("candidateId")]:
                if key:
                    lookup[str(key)] = item
            for key in item.get("mappedCandidateIds") or []:
                lookup[str(key)] = item
    if CANONICAL_CANDIDATES.exists():
        with CANONICAL_CANDIDATES.open("rb") as handle:
            for item in ijson.items(handle, "item"):
                cid = item.get("candidateId")
                if cid and cid not in lookup:
                    lookup[cid] = {
                        "candidateId": cid,
                        "localTileId": item.get("localTileId"),
                        "sourceTilesheet": item.get("tilesheetName") or item.get("imageName"),
                        "mappedCandidates": [{"copiedImagePath": item.get("copiedImagePath")}],
                    }
    return lookup


def existing_approved_profiles(exclude_path: Path) -> dict[str, set[str]]:
    existing: dict[str, set[str]] = defaultdict(set)
    for path in sorted(APPROVED_TAGS_DIR.glob("*.approved_tags.json")):
        if path == exclude_path:
            continue
        try:
            doc = load_json(path)
        except Exception:
            continue
        for tag in tags_from_doc(doc):
            classes = set()
            if tag.get("approvedClass"):
                classes.add(tag["approvedClass"])
            for profile in tag.get("usageProfiles") or []:
                if profile.get("approvedClass"):
                    classes.add(profile["approvedClass"])
            for cid in tag.get("candidateIds") or []:
                existing[cid].update(classes)
    return existing


def tag_note_text(tag: dict[str, Any]) -> str:
    pieces = [tag.get("notes"), tag.get("safetyNotes"), tag.get("approvalNotes")]
    for profile in tag.get("usageProfiles") or []:
        pieces.append(profile.get("notes"))
        pieces.append(profile.get("evidenceSummary"))
    return " ".join(str(piece or "") for piece in pieces)


def validate_file(approved_path: Path, report_path: Path, title: str) -> tuple[int, dict[str, Any]]:
    if not approved_path.exists():
        write_report(report_path, [
            f"# {title}",
            "",
            f"- Generated: {now_iso()}",
            "- Result: SKIPPED",
            f"- Reason: `{approved_path}` does not exist yet.",
            "- No structural approvals were validated.",
        ])
        return 0, {"result": "SKIPPED", "errors": 0, "warnings": 0, "tags": 0}

    schema = load_json(CLASS_SCHEMA)
    valid_classes = set(schema)
    candidates = candidate_lookup()
    approval_candidate_lookup = approval_utils.candidate_lookup()
    approved_db = approval_utils.db_approval_lookup(approval_candidate_lookup)
    existing = existing_approved_profiles(approved_path)
    doc = load_json(approved_path)
    errors: list[str] = []
    warnings: list[str] = []
    tag_count = 0
    candidate_count = 0

    for i, tag in enumerate(tags_from_doc(doc)):
        tag_count += 1
        label = f"tag #{i + 1}"
        for tile_error in approval_utils.validate_tile_946_tag(tag, approval_candidate_lookup):
            errors.append(f"{label}: {tile_error}")
        if tag.get("source") in {"manual_review", "accepted_proposed_tag"}:
            status, notes = approval_utils.classify_against_stronger_db(tag, approval_candidate_lookup, approved_db)
            if status == "conflict":
                errors.append(f"{label}: manual approval conflicts with stronger approved DB entry; quarantine required. {'; '.join(notes[:4])}")
            elif status == "confirmation":
                errors.append(f"{label}: manual approval matches stronger approved DB entry and belongs in approval_confirmations, not approved_tags.")
        role = tag.get("structuralRole")
        if role not in ALL_ROLES:
            errors.append(f"{label}: invalid or missing structuralRole `{role}`.")
            continue
        approved_class = tag.get("approvedClass")
        layers = tag.get("allowedLayers") or []
        collision = tag.get("collision")
        if approved_class not in valid_classes:
            errors.append(f"{label}: approvedClass `{approved_class}` is not in tile_class_schema.json.")
        for layer in layers:
            if layer not in VALID_LAYERS:
                errors.append(f"{label}: invalid allowedLayer `{layer}`.")
        if collision not in VALID_COLLISIONS:
            errors.append(f"{label}: invalid collision `{collision}`.")
        default_layers = set(ALL_ROLE_CLASS_DEFAULTS[role][2])
        if not set(layers) <= (default_layers | {"Back", "Front", "Buildings", "AlwaysFront", "Paths"}):
            errors.append(f"{label}: layers {layers} are not compatible with role {role}.")
        if role == "path_base":
            if approved_class != "path_base":
                errors.append(f"{label}: path_base approval must use approvedClass `path_base`.")
            if set(layers) != {"Back"}:
                errors.append(f"{label}: path_base approval must use allowedLayers exactly [`Back`].")
            if collision != "walkable":
                errors.append(f"{label}: path_base approval must use collision `walkable`.")
        for profile in tag.get("usageProfiles") or []:
            if profile.get("approvedClass") != approved_class:
                errors.append(f"{label}: usageProfile class differs from tag approvedClass.")
            if profile.get("layerRole") != role:
                errors.append(f"{label}: usageProfile layerRole differs from structuralRole.")
        for cid in tag.get("candidateIds") or []:
            candidate_count += 1
            candidate = candidates.get(cid)
            if not candidate:
                errors.append(f"{label}: unknown candidateId `{cid}`.")
                continue
            local_id = candidate.get("localTileId")
            try:
                local_id = int(local_id)
            except Exception:
                local_id = None
            if local_id == 946 and (role in BLOCKING_ROLES or collision in BLOCKING_COLLISIONS or "Buildings" in layers):
                errors.append(f"{label}: tile 946 cannot be approved for wall/body/blocking/collision roles.")
            if local_id == 946 and role == "path_base":
                errors.append(f"{label}: tile 946 cannot be approved as path_base.")
            if role == "path_base":
                for gate_error in approval_utils.path_base_candidate_gate_errors(
                    candidate,
                    note_text=tag_note_text(tag),
                    allow_explicit_non_back_note=True,
                ):
                    errors.append(f"{label}: {gate_error}")
            if "AlwaysFront" in layers and collision in BLOCKING_COLLISIONS:
                errors.append(f"{label}: AlwaysFront tile approved as blocker.")
            for mapped in candidate.get("mappedCandidates") or []:
                path_text = str(mapped.get("copiedImagePath", "")).lower()
                if any(token in path_text for token in RESTRICTED_TOKENS):
                    errors.append(f"{label}: restricted DeepWoods asset dependency in `{path_text}`.")
            previous = existing.get(cid, set())
            if previous and approved_class not in previous:
                warnings.append(f"{label}: candidate `{cid}` already has approved classes {sorted(previous)}; profile-specific merge review needed.")

    result = "PASS" if not errors else "FAIL"
    lines = [
        f"# {title}",
        "",
        f"- Generated: {now_iso()}",
        f"- Result: {result}",
        f"- Tags checked: {tag_count}",
        f"- Candidate IDs checked: {candidate_count}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
    ]
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {err}" for err in errors)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warn}" for warn in warnings[:100])
    write_report(report_path, lines)
    return (0 if not errors else 1), {"result": result, "errors": len(errors), "warnings": len(warnings), "tags": tag_count}


def main() -> int:
    code_full, summary_full = validate_file(APPROVED_PATH, REPORT_PATH, "Structural Approval Validation Report")
    code_min, summary_min = validate_file(MINIMUM_APPROVED_PATH, MINIMUM_REPORT_PATH, "Minimum Structural Approval Validation Report")
    code_path, summary_path = validate_file(PATH_BASE_APPROVED_PATH, PATH_BASE_REPORT_PATH, "Path Base Approval Validation Report")
    print(
        "Structural approval validation complete; "
        f"full={summary_full['result']} errors={summary_full['errors']} warnings={summary_full['warnings']}; "
        f"minimum={summary_min['result']} errors={summary_min['errors']} warnings={summary_min['warnings']}; "
        f"path_base={summary_path['result']} errors={summary_path['errors']} warnings={summary_path['warnings']}"
    )
    return 1 if code_full or code_min or code_path else 0


if __name__ == "__main__":
    raise SystemExit(main())
