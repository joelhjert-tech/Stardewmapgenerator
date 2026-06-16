import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ijson


TOOL_ROOT = Path(__file__).resolve().parent
DB_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
HASH_INDEX_PATH = TOOL_ROOT / "review" / "duplicate_resolution" / "tile_hash_index.json"
PROPOSED_PATH = TOOL_ROOT / "review" / "custom_duplicate_matching" / "custom_duplicate_proposed_approved_tags.json"
SCHEMA_PATH = TOOL_ROOT / "classification" / "tile_class_schema.json"
REPORT_PATH = TOOL_ROOT / "reports" / "custom_duplicate_validation_report.md"

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "AlwaysFront2", "Paths", "Map", "Objects"}
VALID_COLLISIONS = {"walkable", "blocks", "blocked", "blocked_or_special", "none", "passable", "special", "decorative", "front_only", "water", "custom"}
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
BLOCKING_COLLISIONS = {"blocks", "blocked", "blocks_movement"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_json_array(path):
    with path.open("rb") as handle:
        yield from ijson.items(handle, "item")


def iter_hash_entries():
    with HASH_INDEX_PATH.open("rb") as handle:
        yield from ijson.items(handle, "entries.item")


def key_for(entry):
    return (str(entry.get("copiedImagePath") or "").lower(), str(entry.get("localTileId")))


def restricted(entry):
    blob = " ".join(str(entry.get(key, "")) for key in ("copiedImagePath", "tilesheetName", "sourceMod", "sourceCategory")).lower()
    return any(marker in blob for marker in RESTRICTED_MARKERS)


def layer_profile_supported(entry, allowed_layers, collision):
    observed = entry.get("observedLayers") or {}
    total = sum(int(v) for v in observed.values())
    allowed = set(allowed_layers or [])
    if total <= 0:
        return False, "candidate has no observed layer usage"
    if not allowed:
        return False, "proposal has no allowedLayers"
    dominant, count = max(observed.items(), key=lambda kv: int(kv[1]))
    allowed_count = sum(int(v) for layer, v in observed.items() if layer in allowed)
    if dominant not in allowed:
        return False, f"dominant layer `{dominant}` outside allowedLayers {sorted(allowed)}"
    if allowed_count / total < 0.80:
        return False, f"allowed layer fraction {allowed_count / total:.2f} below 0.80"
    if collision == "walkable" and int(observed.get("Buildings", 0)) / total > 0.20:
        return False, "walkable proposal conflicts with substantial Buildings-layer usage"
    if collision in BLOCKING_COLLISIONS and dominant != "Buildings":
        return False, "blocking proposal requires dominant Buildings-layer usage"
    return True, f"dominant layer `{dominant}` with allowed fraction {allowed_count / total:.2f}"


def load_hash_entries_for(candidate_ids):
    wanted = set(candidate_ids)
    found = {}
    for entry in iter_hash_entries():
        cid = entry.get("candidateId")
        if cid in wanted:
            found[cid] = entry
            if len(found) == len(wanted):
                break
    return found


def load_approved_db_keys():
    approved = {}
    for tile in iter_json_array(DB_PATH):
        if tile.get("approved") is not True:
            continue
        key = (str(tile.get("copiedImagePath") or "").lower(), str(tile.get("localTileId")))
        approved[key] = {
            "finalClass": tile.get("finalClass"),
            "finalPurpose": tile.get("finalPurpose"),
            "allowedLayers": tile.get("allowedLayers") or [],
            "collision": tile.get("collision"),
            "approvalSource": tile.get("approvalSource"),
            "localTileId": tile.get("localTileId"),
        }
    return approved


def main():
    errors = []
    warnings = []
    schema = load_json(SCHEMA_PATH)
    valid_classes = set(schema.keys())
    doc = load_json(PROPOSED_PATH) if PROPOSED_PATH.exists() else {"tags": []}
    proposals = doc.get("tags", [])

    wanted_ids = set()
    for tag in proposals:
        wanted_ids.update(tag.get("candidateIds") or [])
        if tag.get("matchedVanillaAnchorCandidateId"):
            wanted_ids.add(tag.get("matchedVanillaAnchorCandidateId"))
    hash_entries = load_hash_entries_for(wanted_ids)
    approved_keys = load_approved_db_keys()
    conflict_counts = Counter()

    for index, tag in enumerate(proposals, start=1):
        label = f"proposal #{index}"
        cids = tag.get("candidateIds") or []
        if tag.get("approved") is not False:
            errors.append(f"- {label}: duplicate proposal must keep approved:false.")
        if tag.get("confidence", 0) < 90:
            errors.append(f"- {label}: confidence below 90.")
        if tag.get("approvedClass") not in valid_classes:
            errors.append(f"- {label}: approvedClass `{tag.get('approvedClass')}` is not in tile_class_schema.json.")
        for layer in tag.get("allowedLayers") or []:
            if layer not in VALID_LAYERS:
                errors.append(f"- {label}: invalid allowedLayer `{layer}`.")
        if tag.get("collision") not in VALID_COLLISIONS:
            errors.append(f"- {label}: invalid collision `{tag.get('collision')}`.")
        if len(cids) != 1:
            errors.append(f"- {label}: expected exactly one duplicate candidateId.")
            continue
        cid = cids[0]
        candidate = hash_entries.get(cid)
        anchor = hash_entries.get(tag.get("matchedVanillaAnchorCandidateId"))
        if not candidate:
            errors.append(f"- {label}: duplicate candidateId `{cid}` not found in hash index.")
            continue
        if not anchor:
            errors.append(f"- {label}: anchor candidateId `{tag.get('matchedVanillaAnchorCandidateId')}` not found in hash index.")
            continue
        candidate_key = key_for(candidate)
        anchor_key = key_for(anchor)
        anchor_db = approved_keys.get(anchor_key)
        if not anchor_db:
            errors.append(f"- {label}: anchor candidate is not approved in tile_database_v1_human_approved.json.")
        elif anchor_db.get("approvalSource") != "vanilla_basegame_authoritative_metadata":
            errors.append(f"- {label}: anchor is approved, but not from vanilla_basegame_authoritative_metadata.")
        if candidate_key in approved_keys:
            errors.append(f"- {label}: duplicate candidate is already approved; do not propose duplicate approval.")
        if candidate.get("hashExact") != anchor.get("hashExact") or tag.get("hashExact") != candidate.get("hashExact"):
            errors.append(f"- {label}: exact hash mismatch.")
        if restricted(candidate) or restricted(anchor):
            errors.append(f"- {label}: restricted DeepWoods asset dependency detected.")
        if candidate.get("sourceCategory") not in PROJECT_OWNED_CATEGORIES:
            errors.append(f"- {label}: duplicate sourceCategory `{candidate.get('sourceCategory')}` is not project-owned.")
        supported, reason = layer_profile_supported(candidate, tag.get("allowedLayers"), tag.get("collision"))
        if not supported:
            errors.append(f"- {label}: layer usage conflict: {reason}.")
            conflict_counts["layer_usage_conflict"] += 1
        if int(candidate.get("localTileId") or -1) == 946 and ("Buildings" in (tag.get("allowedLayers") or []) or tag.get("collision") in BLOCKING_COLLISIONS):
            errors.append(f"- {label}: tile 946 proposed as Buildings/blocking.")
            conflict_counts["tile_946_blocking"] += 1

    conflict_lines = [f"- {key}: {value}" for key, value in conflict_counts.most_common()] or ["- None."]
    lines = [
        "# Custom Duplicate Validation Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Proposals scanned: {len(proposals)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Verdict: {'PASS' if not errors else 'FAIL'}",
        "",
        "## Conflict Counts",
        *conflict_lines,
        "",
        "## Errors",
        *(errors or ["- None."]),
        "",
        "## Warnings",
        *(warnings or ["- None."]),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"custom duplicate validation: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
