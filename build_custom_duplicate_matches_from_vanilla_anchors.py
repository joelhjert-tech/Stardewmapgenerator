import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import ijson


TOOL_ROOT = Path(__file__).resolve().parent
DB_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
HASH_INDEX_PATH = TOOL_ROOT / "review" / "duplicate_resolution" / "tile_hash_index.json"
OUT_ROOT = TOOL_ROOT / "review" / "custom_duplicate_matching"

MATCHES_PATH = OUT_ROOT / "custom_duplicate_matches.json"
CONFLICTS_PATH = OUT_ROOT / "custom_duplicate_conflicts.json"
PROPOSED_PATH = OUT_ROOT / "custom_duplicate_proposed_approved_tags.json"

PROJECT_OWNED_CATEGORIES = {"moonvillage"}
RESTRICTED_MARKERS = {
    "deepwoodsinfested",
    "deepwoodslake",
    "waterbordertiles",
    "deepwoods_lake",
    "deepwoods_infested",
    "deepwoodsmod-main",
    "deepwoodsmod/src/deepwoods/assets",
    "deepwoodsmod\\src\\deepwoods\\assets",
}
AMBIGUOUS_COLLISIONS = {"unknown", "varies", "profile_specific", None, ""}
BLOCKING_COLLISIONS = {"blocks", "blocked", "blocks_movement"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_hash_index():
    if HASH_INDEX_PATH.exists():
        return "existing_tile_hash_index"
    result = subprocess.run(
        [sys.executable, str(TOOL_ROOT / "build_seed_duplicate_workflow.py")],
        cwd=str(TOOL_ROOT.parent.parent),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or not HASH_INDEX_PATH.exists():
        raise RuntimeError(f"Unable to build tile hash index: {result.stdout}\n{result.stderr}")
    return "rebuilt_tile_hash_index"


def iter_json_array(path):
    with path.open("rb") as handle:
        yield from ijson.items(handle, "item")


def iter_hash_entries():
    with HASH_INDEX_PATH.open("rb") as handle:
        yield from ijson.items(handle, "entries.item")


def key_for_path(path, local_tile_id):
    return (str(path or "").lower(), str(local_tile_id))


def restricted(entry):
    blob = " ".join(str(entry.get(key, "")) for key in ("copiedImagePath", "tilesheetName", "sourceMod", "sourceCategory")).lower()
    return any(marker in blob for marker in RESTRICTED_MARKERS)


def dominant_layer(observed_layers):
    if not observed_layers:
        return None, 0, 0.0
    total = sum(int(v) for v in observed_layers.values())
    if total <= 0:
        return None, 0, 0.0
    layer, count = max(observed_layers.items(), key=lambda kv: int(kv[1]))
    return layer, int(count), int(count) / total


def compatible_layer_usage(candidate_entry, anchor):
    observed = candidate_entry.get("observedLayers") or {}
    total = sum(int(v) for v in observed.values())
    allowed = set(anchor.get("allowedLayers") or [])
    if total <= 0:
        return False, "duplicate has no observed layer usage"
    if not allowed:
        return False, "approved anchor has no allowedLayers"
    dominant, _count, fraction = dominant_layer(observed)
    allowed_count = sum(int(count) for layer, count in observed.items() if layer in allowed)
    allowed_fraction = allowed_count / total
    if dominant not in allowed:
        return False, f"dominant duplicate layer `{dominant}` is outside anchor layers {sorted(allowed)}"
    if allowed_fraction < 0.80:
        return False, f"duplicate allowed-layer fraction {allowed_fraction:.2f} is below 0.80"
    if anchor.get("collision") == "walkable" and int(observed.get("Buildings", 0)) / total > 0.20:
        return False, "walkable anchor conflicts with substantial Buildings-layer duplicate usage"
    if anchor.get("collision") in BLOCKING_COLLISIONS and dominant != "Buildings":
        return False, "blocking anchor is only compatible with dominant Buildings-layer duplicate usage"
    return True, f"dominant layer `{dominant}` ({fraction:.2f}) and allowed fraction {allowed_fraction:.2f} are compatible"


def load_approved_basegame_anchors():
    anchors_by_key = {}
    for tile in iter_json_array(DB_PATH):
        if tile.get("approved") is not True:
            continue
        if tile.get("approvalSource") != "vanilla_basegame_authoritative_metadata":
            continue
        if tile.get("collision") in AMBIGUOUS_COLLISIONS:
            continue
        key = key_for_path(tile.get("copiedImagePath"), tile.get("localTileId"))
        anchors_by_key[key] = {
            "finalClass": tile.get("finalClass"),
            "finalPurpose": tile.get("finalPurpose"),
            "allowedLayers": tile.get("allowedLayers") or [],
            "collision": tile.get("collision"),
            "terrainSet": tile.get("terrainSet"),
            "terrainA": tile.get("terrainA"),
            "terrainB": tile.get("terrainB"),
            "edgeMask": tile.get("edgeMask") or [],
            "cornerMask": tile.get("cornerMask") or [],
            "transitionType": tile.get("transitionType"),
            "footprint": tile.get("footprint"),
            "allowedRooms": tile.get("allowedRooms") or [],
            "avoidNear": tile.get("avoidNear") or [],
            "weight": tile.get("weight", 1),
            "approvalConfidence": tile.get("approvalConfidence"),
            "imageName": tile.get("imageName") or tile.get("tilesetName"),
            "copiedImagePath": tile.get("copiedImagePath"),
            "localTileId": tile.get("localTileId"),
        }
    return anchors_by_key


def build_anchor_hashes(anchors_by_key):
    anchors_by_hash = defaultdict(list)
    approved_candidate_ids = set()
    for entry in iter_hash_entries():
        key = key_for_path(entry.get("copiedImagePath"), entry.get("localTileId"))
        anchor = anchors_by_key.get(key)
        if not anchor:
            continue
        if restricted(entry):
            continue
        approved_candidate_ids.add(entry.get("candidateId"))
        anchors_by_hash[entry.get("hashExact")].append(
            {
                **anchor,
                "candidateId": entry.get("candidateId"),
                "hashExact": entry.get("hashExact"),
                "hashRgbOnly": entry.get("hashRgbOnly"),
                "tilesheetName": entry.get("tilesheetName"),
                "sourceCategory": entry.get("sourceCategory"),
                "sourceMod": entry.get("sourceMod"),
                "observedLayers": entry.get("observedLayers") or {},
                "observedCountTotal": entry.get("observedCountTotal", 0),
            }
        )
    return anchors_by_hash, approved_candidate_ids


def candidate_is_tile_946_conflict(entry, anchor):
    if int(entry.get("localTileId") or -1) != 946:
        return False
    allowed = set(anchor.get("allowedLayers") or [])
    if "AlwaysFront" in allowed and anchor.get("collision") not in BLOCKING_COLLISIONS:
        return False
    return True


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    hash_status = ensure_hash_index()
    anchors_by_key = load_approved_basegame_anchors()
    anchors_by_hash, approved_candidate_ids = build_anchor_hashes(anchors_by_key)

    matches = []
    conflicts = []
    matched_candidates = set()
    conflict_reasons = Counter()
    scanned = 0
    hash_hit_count = 0

    for entry in iter_hash_entries():
        scanned += 1
        if entry.get("candidateId") in approved_candidate_ids:
            continue
        anchors = anchors_by_hash.get(entry.get("hashExact")) or []
        if not anchors:
            continue
        hash_hit_count += 1
        if restricted(entry):
            conflicts.append({"candidateId": entry.get("candidateId"), "reason": "restricted_deepwoods_asset", "hashExact": entry.get("hashExact")})
            conflict_reasons["restricted_deepwoods_asset"] += 1
            continue
        if entry.get("sourceCategory") not in PROJECT_OWNED_CATEGORIES:
            conflicts.append(
                {
                    "candidateId": entry.get("candidateId"),
                    "sourceCategory": entry.get("sourceCategory"),
                    "reason": "source_sheet_not_project_owned",
                    "hashExact": entry.get("hashExact"),
                }
            )
            conflict_reasons["source_sheet_not_project_owned"] += 1
            continue

        accepted_for_candidate = False
        for anchor in anchors:
            if anchor.get("collision") in AMBIGUOUS_COLLISIONS:
                conflicts.append(
                    {
                        "candidateId": entry.get("candidateId"),
                        "anchorCandidateId": anchor.get("candidateId"),
                        "reason": "approved_anchor_has_ambiguous_collision",
                    }
                )
                conflict_reasons["approved_anchor_has_ambiguous_collision"] += 1
                continue
            if candidate_is_tile_946_conflict(entry, anchor):
                conflicts.append(
                    {
                        "candidateId": entry.get("candidateId"),
                        "anchorCandidateId": anchor.get("candidateId"),
                        "reason": "tile_946_canopy_blocker_profile_conflict",
                        "anchorAllowedLayers": anchor.get("allowedLayers"),
                        "anchorCollision": anchor.get("collision"),
                    }
                )
                conflict_reasons["tile_946_canopy_blocker_profile_conflict"] += 1
                continue
            compatible, reason = compatible_layer_usage(entry, anchor)
            if not compatible:
                conflicts.append(
                    {
                        "candidateId": entry.get("candidateId"),
                        "anchorCandidateId": anchor.get("candidateId"),
                        "hashExact": entry.get("hashExact"),
                        "reason": "layer_usage_conflict",
                        "detail": reason,
                        "candidateObservedLayers": entry.get("observedLayers") or {},
                        "anchorAllowedLayers": anchor.get("allowedLayers"),
                    }
                )
                conflict_reasons["layer_usage_conflict"] += 1
                continue
            if entry.get("candidateId") in matched_candidates:
                conflicts.append(
                    {
                        "candidateId": entry.get("candidateId"),
                        "anchorCandidateId": anchor.get("candidateId"),
                        "reason": "candidate_already_matched_by_another_anchor",
                    }
                )
                conflict_reasons["candidate_already_matched_by_another_anchor"] += 1
                continue
            match = {
                "candidateId": entry.get("candidateId"),
                "matchedVanillaAnchorCandidateId": anchor.get("candidateId"),
                "hashExact": entry.get("hashExact"),
                "approvedClass": anchor.get("finalClass"),
                "approvedPurpose": anchor.get("finalPurpose"),
                "allowedLayers": anchor.get("allowedLayers"),
                "collision": anchor.get("collision"),
                "terrainSet": anchor.get("terrainSet"),
                "terrainA": anchor.get("terrainA"),
                "terrainB": anchor.get("terrainB"),
                "edgeMask": anchor.get("edgeMask") or [],
                "cornerMask": anchor.get("cornerMask") or [],
                "transitionType": anchor.get("transitionType"),
                "footprint": anchor.get("footprint"),
                "allowedRooms": anchor.get("allowedRooms") or [],
                "avoidNear": anchor.get("avoidNear") or [],
                "weight": anchor.get("weight", 1),
                "confidence": 90,
                "approved": False,
                "approvedBy": "codex_duplicate_evidence_pending_validation",
                "source": "exact_duplicate_of_approved_vanilla_anchor",
                "reason": "pixel_exact_duplicate_of_basegame_authoritative_anchor_with_matching_layer_usage",
                "layerCompatibilityReason": reason,
                "candidate": {
                    "tilesheetName": entry.get("tilesheetName"),
                    "copiedImagePath": entry.get("copiedImagePath"),
                    "sourceCategory": entry.get("sourceCategory"),
                    "sourceMod": entry.get("sourceMod"),
                    "localTileId": entry.get("localTileId"),
                    "observedLayers": entry.get("observedLayers") or {},
                    "observedCountTotal": entry.get("observedCountTotal", 0),
                },
                "anchor": {
                    "tilesheetName": anchor.get("tilesheetName"),
                    "copiedImagePath": anchor.get("copiedImagePath"),
                    "localTileId": anchor.get("localTileId"),
                    "observedLayers": anchor.get("observedLayers") or {},
                    "observedCountTotal": anchor.get("observedCountTotal", 0),
                    "approvalConfidence": anchor.get("approvalConfidence"),
                },
            }
            matches.append(match)
            matched_candidates.add(entry.get("candidateId"))
            accepted_for_candidate = True
            break
        if not accepted_for_candidate:
            continue

    proposed_tags = [
        {
            "candidateIds": [m["candidateId"]],
            "approvedClass": m["approvedClass"],
            "approvedPurpose": m["approvedPurpose"],
            "allowedLayers": m["allowedLayers"],
            "collision": m["collision"],
            "terrainSet": m["terrainSet"],
            "terrainA": m["terrainA"],
            "terrainB": m["terrainB"],
            "edgeMask": m["edgeMask"],
            "cornerMask": m["cornerMask"],
            "transitionType": m["transitionType"],
            "footprint": m["footprint"],
            "allowedRooms": m["allowedRooms"],
            "avoidNear": m["avoidNear"],
            "weight": m["weight"],
            "approvedBy": m["approvedBy"],
            "approvedAt": now_iso(),
            "source": m["source"],
            "confidence": m["confidence"],
            "approved": False,
            "matchedVanillaAnchorCandidateId": m["matchedVanillaAnchorCandidateId"],
            "hashExact": m["hashExact"],
            "evidenceSummary": m["reason"],
            "safetyNotes": "Quarantined duplicate proposal only; not merged until validation and user acceptance.",
        }
        for m in matches
    ]

    metadata = {
        "generatedAt": now_iso(),
        "hashIndexStatus": hash_status,
        "hashEntriesScanned": scanned,
        "approvedBasegameAnchorKeys": len(anchors_by_key),
        "approvedAnchorHashes": len(anchors_by_hash),
        "hashHitsAgainstUnapprovedCandidates": hash_hit_count,
        "matchesCount": len(matches),
        "conflictsCount": len(conflicts),
        "conflictBreakdown": dict(conflict_reasons),
        "rules": {
            "confidence": 90,
            "sourceCategoriesAllowedForProposal": sorted(PROJECT_OWNED_CATEGORIES),
            "requiresExactHash": True,
            "requiresCompatibleLayerUsage": True,
            "doesNotAutoMerge": True,
        },
    }
    write_json(MATCHES_PATH, {**metadata, "matches": matches})
    write_json(CONFLICTS_PATH, {**metadata, "conflicts": conflicts})
    write_json(PROPOSED_PATH, {**metadata, "tags": proposed_tags})
    print(f"custom duplicate matches: {len(matches)}; conflicts: {len(conflicts)}")


if __name__ == "__main__":
    main()
