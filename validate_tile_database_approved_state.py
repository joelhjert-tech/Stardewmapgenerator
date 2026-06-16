import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import ijson


TOOL_ROOT = Path(__file__).resolve().parent
DB_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
SCHEMA_PATH = TOOL_ROOT / "classification" / "tile_class_schema.json"
STATE_PATH = TOOL_ROOT / "review" / "basegame_merge" / "basegame_promotion_state.json"
REPORT_PATH = TOOL_ROOT / "reports" / "basegame_merged_database_validation.md"

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "AlwaysFront2", "Paths", "Map", "Objects"}
VALID_COLLISIONS = {
    "unknown",
    "walkable",
    "blocks",
    "blocked",
    "blocked_or_special",
    "water_blocked",
    "none",
    "passable",
    "special",
    "decorative",
    "decorative_front",
    "front_only",
    "overlay_only",
    "marker_only",
    "water",
    "custom",
    "custom_requires_review",
    "profile_specific",
}
RESTRICTED_MARKERS = {
    "deepwoodsinfested",
    "deepwoodslake",
    "waterbordertiles",
    "deepwoods_lake",
    "deepwoods_infested",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_json_array(path):
    with path.open("rb") as handle:
        yield from ijson.items(handle, "item")


def restricted_asset(tile):
    blob = f"{tile.get('tilesetName', '')} {tile.get('imageName', '')} {tile.get('copiedImagePath', '')}".lower()
    return any(marker in blob for marker in RESTRICTED_MARKERS)


def blocking_collision(value):
    return value in {"blocks", "blocked", "blocks_movement"}


def validate_approved_tile(tile, valid_classes):
    errors = []
    label = f"{tile.get('imageName') or tile.get('tilesetName')} localTileId={tile.get('localTileId')}"
    if not tile.get("finalClass"):
        errors.append(f"{label}: approved tile missing finalClass.")
    elif tile.get("finalClass") not in valid_classes:
        errors.append(f"{label}: finalClass `{tile.get('finalClass')}` is not in tile_class_schema.json.")
    if not tile.get("finalPurpose"):
        errors.append(f"{label}: approved tile missing finalPurpose.")
    if not tile.get("allowedLayers"):
        errors.append(f"{label}: approved tile missing allowedLayers.")
    for layer in tile.get("allowedLayers") or []:
        if layer not in VALID_LAYERS:
            errors.append(f"{label}: invalid allowedLayer `{layer}`.")
    if not tile.get("collision"):
        errors.append(f"{label}: approved tile missing collision.")
    elif tile.get("collision") not in VALID_COLLISIONS:
        errors.append(f"{label}: invalid collision `{tile.get('collision')}`.")
    if tile.get("localTileId") == 946 and ("Buildings" in (tile.get("allowedLayers") or []) or blocking_collision(tile.get("collision"))):
        errors.append(f"{label}: tile 946 approved as Buildings/blocking, which is forbidden.")
    if restricted_asset(tile):
        errors.append(f"{label}: approved tile references restricted DeepWoods asset.")
    return errors


def main():
    valid_classes = set(load_json(SCHEMA_PATH).keys())
    state = load_json(STATE_PATH) if STATE_PATH.exists() else {}
    backup_path = Path(state.get("dbBackupPath", "")) if state.get("dbBackupPath") else None

    errors = []
    warnings = []
    approved_count = 0
    total_count = 0
    class_counts = Counter()
    collision_counts = Counter()
    approved_key_to_class = defaultdict(set)

    if backup_path and backup_path.exists():
        old_iter = iter_json_array(backup_path)
    else:
        old_iter = None
        warnings.append("- No usable backup path found; unapproved unchanged check skipped.")

    changed_unapproved = 0
    compare_count = 0
    for new_tile in iter_json_array(DB_PATH):
        total_count += 1
        old_tile = next(old_iter) if old_iter else None
        if old_tile is not None:
            compare_count += 1
        if new_tile.get("approved") is True:
            approved_count += 1
            class_counts[new_tile.get("finalClass")] += 1
            collision_counts[new_tile.get("collision")] += 1
            errors.extend(validate_approved_tile(new_tile, valid_classes))
            key = (str(new_tile.get("copiedImagePath") or "").lower(), str(new_tile.get("localTileId")))
            approved_key_to_class[key].add(new_tile.get("finalClass"))
        elif old_tile is not None and new_tile != old_tile:
            changed_unapproved += 1
            if changed_unapproved <= 20:
                errors.append(
                    f"Unapproved entry changed unexpectedly: {new_tile.get('imageName') or new_tile.get('tilesetName')} localTileId={new_tile.get('localTileId')}"
                )

    for key, classes in approved_key_to_class.items():
        if len(classes) > 1:
            errors.append(f"Approved candidate key {key} has conflicting classes: {sorted(classes)}")

    if old_iter:
        try:
            next(old_iter)
            errors.append("Backup database has extra entries after new database ended.")
        except StopIteration:
            pass

    if approved_count < state.get("candidateCount", 0):
        errors.append(f"Approved count {approved_count} is below expected promoted candidate count {state.get('candidateCount')}.")

    lines = [
        "# Base-Game Merged Database Validation",
        "",
        f"- Generated: {now_iso()}",
        f"- Database: {DB_PATH}",
        f"- Backup compared: {backup_path if backup_path else 'not found'}",
        f"- Total entries scanned: {total_count}",
        f"- Approved entries: {approved_count}",
        f"- Expected promoted candidates: {state.get('candidateCount', 'unknown')}",
        f"- Unapproved entries changed: {changed_unapproved}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Verdict: {'PASS' if not errors else 'FAIL'}",
        "",
        "## Class Breakdown",
        *[f"- {key}: {value}" for key, value in class_counts.most_common()],
        "",
        "## Collision Breakdown",
        *[f"- {key}: {value}" for key, value in collision_counts.most_common()],
        "",
        "## Errors",
        *(errors or ["- None."]),
        "",
        "## Warnings",
        *(warnings or ["- None."]),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"database validation: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
