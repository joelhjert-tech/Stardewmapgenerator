#!/usr/bin/env python3
"""Shared helpers for Tile Map Assistant approval staging validation."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ijson


TOOL_ROOT = Path(os.environ.get("TMA_TOOL_ROOT", Path(__file__).resolve().parent)).resolve()
CLASS_ROOT = TOOL_ROOT / "classification"
APPROVED_TAGS_DIR = CLASS_ROOT / "approved_tags"
REVIEW_ROOT = TOOL_ROOT / "review"
CONFLICT_ROOT = REVIEW_ROOT / "manual_approval_conflicts"
CONFIRMATION_ROOT = REVIEW_ROOT / "approval_confirmations"
REPORTS_ROOT = TOOL_ROOT / "reports"
DATABASE_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
CANONICAL_CANDIDATES = CLASS_ROOT / "canonical_tile_candidates.json"
STRUCTURAL_CANDIDATES = TOOL_ROOT / "structural_learning" / "candidates" / "structural_tile_candidates_by_role.json"
PATH_BASE_CANDIDATES = TOOL_ROOT / "structural_learning" / "path_base_review" / "path_base_candidates.json"

OFFICIAL_APPROVED_GLOB = "*.approved_tags.json"
SUSPICIOUS_APPROVAL_NAME = re.compile(r"(\(\d+\)|\bcopy\b|approved[_ .-]?tags|approval)", re.IGNORECASE)
DUPLICATE_BROWSER_COPY_NAME = re.compile(r"(\(\d+\)|\bcopy\b)", re.IGNORECASE)

STRONGER_APPROVAL_SOURCES = {
    "vanilla_basegame_authoritative_metadata",
    "codex_basegame_authoritative_metadata",
    "vanilla_tbin_intrinsic_metadata_and_byte_identical_tilesheet",
    "tsx_metadata",
    "tsx_wang_metadata",
    "tsx_terrain_metadata",
    "wang_metadata",
    "terrain_metadata",
}

TILE_946_ALLOWED_CLASSES = {"canopy_overlay", "overlay"}
TILE_946_ALLOWED_SOURCES = {"manual_review", "manual_confirmation", "approval_confirmation"}
TILE_946_UNSAFE_CLASSES = {
    "wall_body",
    "wall_corner",
    "wall_edge",
    "blocker",
    "collision_blocker",
    "wall_side",
    "exterior_wall",
}
TILE_946_UNSAFE_COLLISIONS = {"blocked", "blocks", "water_blocked", "blocked_or_special", "blocks_movement"}
TILE_946_UNSAFE_ROLES = {"wall_body", "wall_corner", "wall_edge", "blocker", "wallBody", "wall_body_blocker"}
VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "AlwaysFront2", "Paths", "Map", "Objects"}
BACK_LIKE_LAYERS = {"Back", "Back2", "Back3", "Back4"}
PATH_BASE_FORBIDDEN_DOMINANT_LAYERS = {"Buildings", "Front", "AlwaysFront", "AlwaysFront2"}

LEGACY_APPROVAL_FIELDS = {"approvedClass", "approvedPurpose", "allowedLayers", "collision"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").lower()


def normalize_collision(value: Any) -> str:
    legacy = {
        "none": "overlay_only",
        "front_only": "decorative_front",
        "decorative": "decorative_front",
        "water": "water_blocked",
        "blocked_or_special": "water_blocked",
        "blocks": "blocked",
        "block": "blocked",
        "blocks_movement": "blocked",
        "special": "custom_requires_review",
        "custom": "custom_requires_review",
        "varies": "custom_requires_review",
        "passable": "walkable",
        "walkable_unless_marked": "walkable",
    }
    return legacy.get(str(value or "").lower(), value or "unknown")


def tags_from_doc(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [tag for tag in doc if isinstance(tag, dict)]
    if isinstance(doc, dict):
        tags = doc.get("tags", [])
        return tags if isinstance(tags, list) else []
    return []


def normalized_profiles(tag: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = tag.get("usageProfiles")
    if isinstance(profiles, list) and profiles:
        return [profile for profile in profiles if isinstance(profile, dict)]
    if LEGACY_APPROVAL_FIELDS <= set(tag.keys()):
        return [
            {
                "profileId": tag.get("profileId") or "legacy_default",
                "approvedClass": tag.get("approvedClass"),
                "approvedPurpose": tag.get("approvedPurpose"),
                "allowedLayers": tag.get("allowedLayers") or [],
                "collision": tag.get("collision", "unknown"),
                "layerRole": tag.get("layerRole") or tag.get("structuralRole") or "legacy_single_profile",
                "evidence": tag.get("evidence") or [],
                "notes": tag.get("notes", ""),
                "terrainSet": tag.get("terrainSet"),
                "terrainA": tag.get("terrainA"),
                "terrainB": tag.get("terrainB"),
                "transitionType": tag.get("transitionType"),
                "footprint": tag.get("footprint"),
            }
        ]
    return []


def tag_candidate_ids(tag: dict[str, Any]) -> list[str]:
    ids = tag.get("candidateIds") or []
    if not isinstance(ids, list):
        return []
    return [str(cid) for cid in ids if cid]


def tag_looks_like_approval_data(doc: Any) -> bool:
    tags = tags_from_doc(doc)
    if tags:
        for tag in tags[:20]:
            if any(key in tag for key in ("candidateIds", "approvedClass", "usageProfiles", "approvedBy", "approvedAt")):
                return True
    if isinstance(doc, dict):
        return any(key in doc for key in ("approvedBy", "reviewPackId", "source", "tags"))
    return False


def official_approved_tag_files(approved_dir: Path = APPROVED_TAGS_DIR) -> list[Path]:
    if not approved_dir.exists():
        return []
    return sorted(approved_dir.glob(OFFICIAL_APPROVED_GLOB))


def suspicious_approval_files(approved_dir: Path = APPROVED_TAGS_DIR) -> list[Path]:
    if not approved_dir.exists():
        return []
    official = set(official_approved_tag_files(approved_dir))
    out = []
    for path in sorted(approved_dir.glob("*.json")):
        if path in official:
            continue
        if SUSPICIOUS_APPROVAL_NAME.search(path.name):
            out.append(path)
            continue
        try:
            if tag_looks_like_approval_data(load_json(path)):
                out.append(path)
        except Exception:
            if SUSPICIOUS_APPROVAL_NAME.search(path.name):
                out.append(path)
    return out


def candidate_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if CANONICAL_CANDIDATES.exists():
        with CANONICAL_CANDIDATES.open("rb") as handle:
            for item in ijson.items(handle, "item"):
                cid = item.get("candidateId")
                if cid:
                    lookup[str(cid)] = {
                        **item,
                        "candidateId": str(cid),
                        "copiedImagePath": item.get("copiedImagePath"),
                        "sourceTilesheet": item.get("tilesheetName") or item.get("imageName"),
                    }
    review_pack_root = CLASS_ROOT / "review_packs"
    if review_pack_root.exists():
        for pack_path in review_pack_root.glob("*.json"):
            try:
                pack = load_json(pack_path)
            except Exception:
                continue
            image_path = pack.get("copiedImagePath")
            for candidate in pack.get("candidates", []) or []:
                cid = candidate.get("candidateId")
                if cid and cid not in lookup:
                    lookup[str(cid)] = {
                        **candidate,
                        "candidateId": str(cid),
                        "copiedImagePath": image_path,
                        "sourceTilesheet": candidate.get("sourceTilesheet") or pack.get("tilesheetName"),
                    }
    if STRUCTURAL_CANDIDATES.exists():
        try:
            doc = load_json(STRUCTURAL_CANDIDATES)
        except Exception:
            doc = {}
        for role, items in (doc.get("roles") or {}).items():
            for item in items or []:
                enriched = {**item, "roleName": role}
                for key in [item.get("candidateId"), item.get("structuralCandidateId")]:
                    if key:
                        lookup.setdefault(str(key), enriched)
                for key in item.get("mappedCandidateIds") or []:
                    lookup.setdefault(str(key), enriched)
    if PATH_BASE_CANDIDATES.exists():
        try:
            doc = load_json(PATH_BASE_CANDIDATES)
        except Exception:
            doc = {}
        for item in doc.get("candidates", []) or []:
            enriched = {**item, "roleName": "path_base"}
            for key in [item.get("pathBaseCandidateId"), item.get("candidateId")]:
                if key:
                    existing = lookup.get(str(key), {})
                    lookup[str(key)] = {**existing, **enriched, "candidateId": str(key)}
            for key in item.get("mappedCandidateIds") or []:
                existing = lookup.get(str(key), {})
                lookup[str(key)] = {**existing, **enriched, "candidateId": str(key)}
    return lookup


def candidate_local_tile_id(candidate_id: str, lookup: dict[str, dict[str, Any]]) -> int | None:
    candidate = lookup.get(candidate_id) or {}
    value = candidate.get("localTileId")
    if value is None:
        match = re.search(r"_(\d+)$", str(candidate_id))
        value = match.group(1) if match else None
    try:
        return int(value)
    except Exception:
        return None


def candidate_key(candidate_id: str, lookup: dict[str, dict[str, Any]]) -> tuple[str, int] | None:
    candidate = lookup.get(candidate_id) or {}
    local_id = candidate_local_tile_id(candidate_id, lookup)
    image = normalize_path(candidate.get("copiedImagePath"))
    if not image or local_id is None:
        return None
    return image, local_id


def db_approval_lookup(lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    lookup = lookup or candidate_lookup()
    key_to_ids: dict[tuple[str, int], list[str]] = defaultdict(list)
    for cid in lookup:
        key = candidate_key(cid, lookup)
        if key:
            key_to_ids[key].append(cid)
    approvals: dict[str, dict[str, Any]] = {}
    if not DATABASE_PATH.exists():
        return approvals
    with DATABASE_PATH.open("rb") as handle:
        for item in ijson.items(handle, "item"):
            if not item.get("approved"):
                continue
            local_id = item.get("localTileId")
            image = normalize_path(item.get("copiedImagePath"))
            if image and local_id is not None:
                for cid in key_to_ids.get((image, int(local_id)), []):
                    approvals[cid] = item
            cid = item.get("candidateId")
            if cid:
                approvals[str(cid)] = item
    return approvals


def source_is_stronger(source: Any) -> bool:
    return str(source or "") in STRONGER_APPROVAL_SOURCES


def db_entry_is_stronger(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    return source_is_stronger(entry.get("approvalSource") or entry.get("source") or entry.get("approvedBy"))


def same_approval(profile: dict[str, Any], entry: dict[str, Any]) -> bool:
    return (
        profile.get("approvedClass") == entry.get("finalClass")
        and str(profile.get("approvedPurpose") or "") == str(entry.get("finalPurpose") or "")
        and set(profile.get("allowedLayers") or []) == set(entry.get("allowedLayers") or [])
        and normalize_collision(profile.get("collision")) == normalize_collision(entry.get("collision"))
    )


def conflict_with_approval(profile: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    issues = []
    if profile.get("approvedClass") != entry.get("finalClass"):
        issues.append(f"class `{profile.get('approvedClass')}` conflicts with existing `{entry.get('finalClass')}`")
    if str(profile.get("approvedPurpose") or "") != str(entry.get("finalPurpose") or ""):
        issues.append(f"purpose `{profile.get('approvedPurpose')}` conflicts with existing `{entry.get('finalPurpose')}`")
    if set(profile.get("allowedLayers") or []) != set(entry.get("allowedLayers") or []):
        issues.append(f"layers `{profile.get('allowedLayers')}` conflict with existing `{entry.get('allowedLayers')}`")
    if normalize_collision(profile.get("collision")) != normalize_collision(entry.get("collision")):
        issues.append(f"collision `{profile.get('collision')}` conflicts with existing `{entry.get('collision')}`")
    return issues


def classify_against_stronger_db(
    tag: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
    approvals: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    """Return active/new, confirmation, or conflict for a tag."""
    candidate_ids = tag_candidate_ids(tag)
    profiles = normalized_profiles(tag)
    if not candidate_ids or not profiles:
        return "active", []
    saw_stronger = False
    saw_confirmation = False
    issues = []
    for cid in candidate_ids:
        entry = approvals.get(cid)
        if not db_entry_is_stronger(entry):
            continue
        saw_stronger = True
        for profile in profiles:
            if same_approval(profile, entry):
                saw_confirmation = True
            else:
                issues.extend(f"{cid}: {issue}" for issue in conflict_with_approval(profile, entry))
    if issues:
        return "conflict", issues
    if saw_stronger and saw_confirmation:
        return "confirmation", []
    return "active", []


def validate_tile_946_tag(tag: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    candidate_ids = tag_candidate_ids(tag)
    tile_946_ids = [cid for cid in candidate_ids if candidate_local_tile_id(cid, lookup) == 946]
    if not tile_946_ids:
        return errors
    safety_text = f"{tag.get('safetyNotes') or ''} {tag.get('approvalNotes') or ''}".lower()
    source = str(tag.get("source") or "")
    approved_by = str(tag.get("approvedBy") or "")
    for profile in normalized_profiles(tag):
        approved_class = str(profile.get("approvedClass") or "")
        layers = set(profile.get("allowedLayers") or [])
        collision = normalize_collision(profile.get("collision"))
        layer_role = str(profile.get("layerRole") or tag.get("structuralRole") or "")
        if approved_class in TILE_946_UNSAFE_CLASSES:
            errors.append(f"tile 946 cannot be approved as `{approved_class}`.")
        if layer_role in TILE_946_UNSAFE_ROLES:
            errors.append(f"tile 946 cannot be approved for layerRole/structuralRole `{layer_role}`.")
        if "Buildings" in layers:
            errors.append("tile 946 cannot be approved on Buildings.")
        if collision in TILE_946_UNSAFE_COLLISIONS or collision == "blocked":
            errors.append(f"tile 946 cannot carry blocking collision `{collision}`.")
        if approved_class not in TILE_946_ALLOWED_CLASSES:
            errors.append("tile 946 may only pass approval as canopy_overlay or overlay.")
        if "AlwaysFront" not in layers:
            errors.append("tile 946 canopy/overlay approval must include AlwaysFront.")
        if collision != "overlay_only":
            errors.append("tile 946 canopy/overlay approval must use collision overlay_only.")
    if source not in TILE_946_ALLOWED_SOURCES:
        errors.append("tile 946 approval source must be manual review or confirmation, never auto.")
    if approved_by not in {"human", "Joel"}:
        errors.append("tile 946 approval must be explicitly human/manual.")
    if "946" not in safety_text or "quarantine" not in safety_text:
        errors.append("tile 946 approval requires explicit safetyNotes mentioning 946 quarantine.")
    return sorted(set(errors))


def _as_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if value is None:
        return []
    return [value]


def candidate_has_water_property(candidate: dict[str, Any] | None) -> bool:
    candidate = candidate or {}
    prop_sources = [
        candidate.get("intrinsicProperties"),
        candidate.get("existingProperties"),
        candidate.get("properties"),
    ]
    for props in prop_sources:
        if not isinstance(props, dict):
            continue
        for key, value in props.items():
            key_text = str(key or "").lower()
            values = [str(v or "").strip().lower() for v in _as_values(value)]
            if key_text == "water" and any(v in {"t", "true", "1", "yes"} for v in values):
                return True
            if key_text == "type" and any(v == "water" for v in values):
                return True
    return False


def candidate_layer_counts(candidate: dict[str, Any] | None) -> dict[str, int]:
    candidate = candidate or {}
    counts: dict[str, int] = defaultdict(int)

    def add_layers(layers: Any) -> None:
        if not isinstance(layers, dict):
            return
        for layer, count in layers.items():
            try:
                counts[str(layer)] += int(count)
            except Exception:
                counts[str(layer)] += 1

    add_layers(candidate.get("observedLayers"))
    for key in ("canonicalMatches", "mappedCandidates"):
        for item in candidate.get(key) or []:
            add_layers(item.get("observedLayers"))
    return dict(counts)


def candidate_dominant_non_back_layers(candidate: dict[str, Any] | None) -> list[str]:
    candidate = candidate or {}
    bad: set[str] = set()
    dominant_layer = str(candidate.get("dominantLayer") or "")
    if dominant_layer in PATH_BASE_FORBIDDEN_DOMINANT_LAYERS:
        bad.add(dominant_layer)
    counts = candidate_layer_counts(candidate)
    if counts:
        max_layer, _ = max(counts.items(), key=lambda item: item[1])
        if max_layer in PATH_BASE_FORBIDDEN_DOMINANT_LAYERS:
            bad.add(max_layer)
    return sorted(bad)


def has_explicit_non_back_review_note(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    return ("non-back" in text or "non back" in text) and "review" in text


def path_base_candidate_gate_errors(
    candidate: dict[str, Any] | None,
    *,
    note_text: str = "",
    allow_explicit_non_back_note: bool = False,
) -> list[str]:
    candidate = candidate or {}
    errors: list[str] = []
    local_id = candidate.get("localTileId")
    try:
        local_id = int(local_id)
    except Exception:
        local_id = candidate_local_tile_id(str(candidate.get("candidateId") or ""), {str(candidate.get("candidateId") or ""): candidate})
    if local_id == 946:
        errors.append("path_base cannot use tile 946.")
    if candidate_has_water_property(candidate):
        errors.append("path_base candidate has Water=T or water type metadata.")
    bad_layers = candidate_dominant_non_back_layers(candidate)
    if bad_layers and not (allow_explicit_non_back_note and has_explicit_non_back_review_note(note_text)):
        errors.append(f"path_base candidate has dominant non-Back behavior: {', '.join(bad_layers)}.")
    return sorted(set(errors))


def approval_file_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_move_to_quarantine(path: Path, quarantine_dir: Path) -> Path:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / path.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = quarantine_dir / f"{stem}.quarantine{counter}{suffix}"
            counter += 1
    resolved_source = path.resolve()
    resolved_target_dir = quarantine_dir.resolve()
    if TOOL_ROOT not in resolved_source.parents:
        raise ValueError(f"Refusing to move outside tool root: {path}")
    if TOOL_ROOT not in resolved_target_dir.parents and resolved_target_dir != TOOL_ROOT:
        raise ValueError(f"Refusing to move outside tool root: {quarantine_dir}")
    shutil.move(str(path), str(target))
    return target
