#!/usr/bin/env python3
"""Validate approved tag staging files before any merge into the tile DB."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from approval_validation_utils import (
    APPROVED_TAGS_DIR,
    CONFIRMATION_ROOT,
    CONFLICT_ROOT,
    OFFICIAL_APPROVED_GLOB,
    REPORTS_ROOT,
    TOOL_ROOT,
    VALID_LAYERS,
    candidate_lookup,
    classify_against_stronger_db,
    db_approval_lookup,
    official_approved_tag_files,
    load_json,
    normalize_collision,
    normalized_profiles,
    now_iso,
    path_base_candidate_gate_errors,
    suspicious_approval_files,
    tag_candidate_ids,
    tag_looks_like_approval_data,
    tags_from_doc,
    validate_tile_946_tag,
)


BASE_REQUIRED_FIELDS = {
    "candidateIds",
    "weight",
    "approvedBy",
    "approvedAt",
    "source",
}
PROFILE_REQUIRED_FIELDS = {
    "profileId",
    "approvedClass",
    "approvedPurpose",
    "allowedLayers",
    "collision",
    "layerRole",
    "evidence",
    "notes",
}
VALID_APPROVED_BY = {"human", "Joel", "codex_basegame_authoritative_metadata"}
VALID_SOURCES = {
    "manual_review",
    "accepted_proposed_tag",
    "manual_confirmation",
    "approval_confirmation",
    "vanilla_tbin_intrinsic_metadata_and_byte_identical_tilesheet",
}


def valid_collisions() -> set[str]:
    collision_schema = TOOL_ROOT / "stylepacks" / "collision_schema.json"
    if collision_schema.exists():
        data = load_json(collision_schema)
        values = data.get("enum")
        if isinstance(values, list) and values:
            return set(values)
    return {
        "unknown",
        "walkable",
        "blocked",
        "water_blocked",
        "decorative_front",
        "overlay_only",
        "marker_only",
        "custom_requires_review",
    }


def load_schema_classes() -> set[str]:
    schema_path = TOOL_ROOT / "classification" / "tile_class_schema.json"
    return set(load_json(schema_path))


def expand_tile_range(tile_range: str | None, pack_id: str | None, tile_id_by_pack: dict[str, dict[str, str]]) -> list[str]:
    if not tile_range:
        return []
    expr = str(tile_range).strip()
    if not expr:
        return []
    local_ids = []
    for part in re.split(r"\s*,\s*", expr):
        if not part:
            continue
        if re.fullmatch(r"\d+", part):
            local_ids.append(part)
        elif re.fullmatch(r"\d+\s*-\s*\d+", part):
            start, end = [int(x) for x in re.split(r"\s*-\s*", part)]
            step = 1 if end >= start else -1
            local_ids.extend(str(x) for x in range(start, end + step, step))
        elif part.startswith("rect:"):
            continue
        else:
            raise ValueError(f"unsupported tileRange segment: {part}")
    lookup = tile_id_by_pack.get(pack_id or "", {})
    return [lookup[str(local_id)] for local_id in local_ids if str(local_id) in lookup]


def tile_id_lookup_by_pack(lookup: dict[str, dict]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    review_pack_root = TOOL_ROOT / "classification" / "review_packs"
    if not review_pack_root.exists():
        return out
    for pack_path in review_pack_root.glob("*.json"):
        try:
            pack = load_json(pack_path)
        except Exception:
            continue
        pack_id = pack.get("reviewPackId")
        if not pack_id:
            continue
        for candidate in pack.get("candidates", []) or []:
            cid = candidate.get("candidateId")
            local_id = candidate.get("localTileId")
            if cid and local_id is not None:
                out[pack_id][str(local_id)] = str(cid)
    return out


def profile_signature(profile: dict) -> str:
    fields = [
        "approvedClass",
        "approvedPurpose",
        "allowedLayers",
        "collision",
        "layerRole",
        "terrainSet",
        "terrainA",
        "terrainB",
        "transitionType",
        "footprint",
    ]
    signature = {field: profile.get(field) for field in fields}
    signature["collision"] = normalize_collision(signature.get("collision"))
    return json.dumps(signature, sort_keys=True)


def validate_tag(
    path: Path,
    tag: dict,
    index: int,
    valid_classes: set[str],
    valid_collision_values: set[str],
    candidate_ids: set[str],
    lookup: dict[str, dict],
    approvals: dict[str, dict],
    tile_id_by_pack: dict[str, dict[str, str]],
    candidate_to_profiles: dict,
) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    prefix = f"{path.name} tag #{index + 1}"
    missing = sorted(BASE_REQUIRED_FIELDS - set(tag.keys()))
    if missing:
        errors.append(f"- {prefix}: missing required fields: {', '.join(missing)}")
    profiles = normalized_profiles(tag)
    if not profiles:
        errors.append(f"- {prefix}: missing usageProfiles or legacy approvedClass/approvedPurpose/allowedLayers/collision fields.")
    for j, profile in enumerate(profiles):
        profile_prefix = f"{prefix} profile #{j + 1}"
        missing_profile = sorted(PROFILE_REQUIRED_FIELDS - set(profile.keys()))
        if missing_profile and "usageProfiles" in tag:
            errors.append(f"- {profile_prefix}: missing required fields: {', '.join(missing_profile)}")
        if profile.get("approvedClass") not in valid_classes:
            errors.append(f"- {profile_prefix}: approvedClass is not in tile_class_schema.json: {profile.get('approvedClass')}")
        if normalize_collision(profile.get("collision")) not in valid_collision_values:
            errors.append(f"- {profile_prefix}: invalid collision value: {profile.get('collision')}")
        for layer in profile.get("allowedLayers") or []:
            if layer not in VALID_LAYERS:
                warnings.append(f"- {profile_prefix}: uncommon allowedLayer `{layer}`; add to validator if intentional.")
        if profile.get("approvedClass") == "path_base":
            if set(profile.get("allowedLayers") or []) != {"Back"}:
                errors.append(f"- {profile_prefix}: path_base approvals must use allowedLayers exactly [`Back`].")
            if normalize_collision(profile.get("collision")) != "walkable":
                errors.append(f"- {profile_prefix}: path_base approvals must use collision `walkable`.")
    if tag.get("approvedBy") not in VALID_APPROVED_BY:
        errors.append(f"- {prefix}: approvedBy must be one of: {', '.join(sorted(VALID_APPROVED_BY))}.")
    if tag.get("source") not in VALID_SOURCES:
        errors.append(f"- {prefix}: source must be one of: {', '.join(sorted(VALID_SOURCES))}.")
    if tag.get("approvedBy") == "codex_basegame_authoritative_metadata" and tag.get("confidence", 0) < 90:
        errors.append(f"- {prefix}: authoritative base-game approval has confidence below 90.")
    try:
        expanded = expand_tile_range(tag.get("tileRange"), tag.get("reviewPackId"), tile_id_by_pack)
    except Exception as exc:
        expanded = []
        errors.append(f"- {prefix}: tileRange failed to expand: {exc}")
    ids = list(dict.fromkeys(tag_candidate_ids(tag) + expanded))
    if not ids:
        errors.append(f"- {prefix}: no candidateIds and tileRange did not expand to candidates.")
    for cid in ids:
        if cid not in candidate_ids:
            errors.append(f"- {prefix}: unknown candidateId: {cid}")
        for profile in profiles:
            profile_id = profile.get("profileId") or "missing_profile_id"
            candidate_to_profiles[cid][profile_id].append((prefix, profile_signature(profile)))
    if any(profile.get("approvedClass") == "path_base" for profile in profiles):
        note_text = " ".join(
            str(value or "")
            for value in [
                tag.get("notes"),
                tag.get("safetyNotes"),
                tag.get("approvalNotes"),
                *[profile.get("notes") for profile in profiles],
            ]
        )
        for cid in ids:
            candidate = lookup.get(cid)
            if not candidate:
                continue
            for gate_error in path_base_candidate_gate_errors(candidate, note_text=note_text, allow_explicit_non_back_note=True):
                errors.append(f"- {prefix}: {gate_error}")
    for error in validate_tile_946_tag({**tag, "candidateIds": ids}, lookup):
        errors.append(f"- {prefix}: {error}")
    if tag.get("source") in {"manual_review", "accepted_proposed_tag"}:
        status, status_notes = classify_against_stronger_db({**tag, "candidateIds": ids}, lookup, approvals)
        if status == "conflict":
            errors.append(f"- {prefix}: manual approval conflicts with stronger approved DB entry; quarantine required. {'; '.join(status_notes[:4])}")
        elif status == "confirmation":
            errors.append(f"- {prefix}: manual approval matches stronger approved DB entry and belongs in `{CONFIRMATION_ROOT.relative_to(TOOL_ROOT)}`, not approved_tags.")
    return errors, warnings, len(ids)


def validate_suspicious_files(lookup: dict[str, dict], approvals: dict[str, dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    official = set(official_approved_tag_files())
    for path in suspicious_approval_files():
        if path in official:
            continue
        try:
            doc = load_json(path)
            looks_like_approval = tag_looks_like_approval_data(doc)
        except Exception as exc:
            errors.append(f"- {path.name}: suspicious approval-looking file skipped by `{OFFICIAL_APPROVED_GLOB}` and JSON failed to parse: {exc}")
            continue
        if looks_like_approval:
            tags = tags_from_doc(doc)
            tile_946 = any(validate_tile_946_tag(tag, lookup) for tag in tags)
            manual_conflicts = []
            for tag in tags:
                status, notes = classify_against_stronger_db(tag, lookup, approvals)
                if status == "conflict":
                    manual_conflicts.extend(notes)
            detail = []
            if tile_946:
                detail.append("contains tile 946 approval data")
            if manual_conflicts:
                detail.append("contains conflict with stronger approved DB entry")
            errors.append(
                f"- {path.name}: approval-looking JSON is skipped by `{OFFICIAL_APPROVED_GLOB}`; move it to `{CONFLICT_ROOT.relative_to(TOOL_ROOT)}` or rename through the controlled importer. "
                + ("; ".join(detail) if detail else "")
            )
        else:
            warnings.append(f"- {path.name}: suspicious filename skipped by official glob but content does not look like approval data.")
    return errors, warnings


def main() -> int:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    valid_classes = load_schema_classes()
    valid_collision_values = valid_collisions()
    lookup = candidate_lookup()
    approvals = db_approval_lookup(lookup)
    candidate_ids = set(lookup)
    tile_id_by_pack = tile_id_lookup_by_pack(lookup)
    errors: list[str] = []
    warnings: list[str] = []
    tag_count = 0
    candidate_count = 0
    candidate_to_profiles = defaultdict(lambda: defaultdict(list))
    official_files = official_approved_tag_files()

    for path in official_files:
        try:
            doc = load_json(path)
        except Exception as exc:
            errors.append(f"- {path}: invalid JSON: {exc}")
            continue
        for i, tag in enumerate(tags_from_doc(doc)):
            tag_count += 1
            tag_errors, tag_warnings, id_count = validate_tag(
                path,
                tag,
                i,
                valid_classes,
                valid_collision_values,
                candidate_ids,
                lookup,
                approvals,
                tile_id_by_pack,
                candidate_to_profiles,
            )
            errors.extend(tag_errors)
            warnings.extend(tag_warnings)
            candidate_count += id_count

    for cid, profiles in candidate_to_profiles.items():
        for profile_id, signatures in profiles.items():
            unique = {signature for _, signature in signatures}
            if len(unique) > 1:
                refs = ", ".join(prefix for prefix, _ in signatures)
                errors.append(f"- candidate {cid}: conflicting approved definitions for profile `{profile_id}`: {refs}")

    suspicious_errors, suspicious_warnings = validate_suspicious_files(lookup, approvals)
    errors.extend(suspicious_errors)
    warnings.extend(suspicious_warnings)

    report = [
        "# Approved Tag Validation Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Approved tag directory: `{APPROVED_TAGS_DIR}`",
        f"- Official glob: `{OFFICIAL_APPROVED_GLOB}`",
        f"- Official approved tag files scanned: {len(official_files)}",
        f"- Suspicious skipped files found: {len(suspicious_approval_files())}",
        f"- Approved tag entries scanned: {tag_count}",
        f"- Candidate IDs checked: {candidate_count}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        "",
        "## Errors",
        *(errors or ["- None."]),
        "",
        "## Warnings",
        *(warnings or ["- None."]),
    ]
    (REPORTS_ROOT / "approved_tag_validation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
