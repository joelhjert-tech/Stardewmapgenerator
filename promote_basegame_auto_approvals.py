import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ijson


TOOL_ROOT = Path(__file__).resolve().parent
AUTO_PATH = TOOL_ROOT / "review" / "auto_resolution" / "auto_approved_tile_tags.json"
CANONICAL_PATH = TOOL_ROOT / "classification" / "canonical_tile_candidates.json"
APPROVED_TAGS_ROOT = TOOL_ROOT / "classification" / "approved_tags"
DB_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
BACKUP_ROOT = TOOL_ROOT / "backups"
BASEGAME_MERGE_ROOT = TOOL_ROOT / "review" / "basegame_merge"
REPORTS_ROOT = TOOL_ROOT / "reports"

APPROVED_BY = "codex_basegame_authoritative_metadata"
SOURCE = "vanilla_tbin_intrinsic_metadata_and_byte_identical_tilesheet"
APPROVED_TAG_PATH = APPROVED_TAGS_ROOT / "basegame_vanilla_auto_approved.approved_tags.json"
RESTRICTED_MARKERS = {
    "deepwoodsinfested",
    "deepwoodslake",
    "waterbordertiles",
    "deepwoods_lake",
    "deepwoods_infested",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def validate_auto_file():
    result = subprocess.run(
        [sys.executable, str(TOOL_ROOT / "validate_auto_approved_tiles.py")],
        cwd=str(TOOL_ROOT.parent.parent),
        text=True,
        capture_output=True,
    )
    return result


def resolve_candidates(candidate_ids):
    wanted = set(candidate_ids)
    found = {}
    with CANONICAL_PATH.open("rb") as handle:
        for candidate in ijson.items(handle, "item"):
            cid = candidate.get("candidateId")
            if cid in wanted:
                found[cid] = {
                    "candidateId": cid,
                    "localTileId": candidate.get("localTileId"),
                    "tilesheetName": candidate.get("tilesheetName") or candidate.get("imageName"),
                    "copiedImagePath": candidate.get("copiedImagePath") or "",
                    "sourceCategory": candidate.get("sourceCategory"),
                    "sourceMod": candidate.get("sourceMod"),
                    "observedLayers": candidate.get("observedLayers") or {},
                }
                if len(found) == len(wanted):
                    break
    return found


def backup_current_state(ts):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"approved database not found: {DB_PATH}")
    db_backup = BACKUP_ROOT / f"tile_database_v1_human_approved.before_basegame_merge.{ts}.json"
    shutil.copy2(DB_PATH, db_backup)
    if not db_backup.exists() or db_backup.stat().st_size != DB_PATH.stat().st_size:
        raise RuntimeError(f"database backup failed: {db_backup}")

    tags_backup = BACKUP_ROOT / f"approved_tags.before_basegame_merge.{ts}"
    if tags_backup.exists():
        raise FileExistsError(f"backup directory already exists: {tags_backup}")
    if APPROVED_TAGS_ROOT.exists():
        shutil.copytree(APPROVED_TAGS_ROOT, tags_backup)
    else:
        tags_backup.mkdir(parents=True)
    if not tags_backup.exists():
        raise RuntimeError(f"approved_tags backup failed: {tags_backup}")
    return db_backup, tags_backup


def convert_tags(auto_tags):
    converted = []
    approved_at = now_iso()
    for index, tag in enumerate(auto_tags, start=1):
        converted.append(
            {
                "reviewPackId": "basegame_vanilla_auto_approved",
                "candidateIds": tag.get("candidateIds") or ([tag.get("candidateId")] if tag.get("candidateId") else []),
                "approvedClass": tag.get("approvedClass"),
                "approvedPurpose": tag.get("approvedPurpose"),
                "allowedLayers": tag.get("allowedLayers") or [],
                "collision": tag.get("collision"),
                "terrainSet": tag.get("terrainSet"),
                "terrainA": tag.get("terrainA"),
                "terrainB": tag.get("terrainB"),
                "edgeMask": tag.get("edgeMask") or [],
                "cornerMask": tag.get("cornerMask") or [],
                "transitionType": tag.get("transitionType"),
                "footprint": tag.get("footprint"),
                "allowedRooms": tag.get("allowedRooms") or [],
                "avoidNear": tag.get("avoidNear") or [],
                "weight": tag.get("weight", 1),
                "approvedBy": APPROVED_BY,
                "approvedAt": approved_at,
                "source": SOURCE,
                "confidence": tag.get("confidence"),
                "evidenceSourceFile": tag.get("evidenceSourceFile"),
                "evidenceSummary": tag.get("reason") or tag.get("evidenceSummary"),
                "safetyNotes": tag.get("safetyNotes"),
                "vanillaProps": tag.get("vanillaProps") or {},
                "vanillaLayers": tag.get("vanillaLayers") or {},
                "sheetsCovered": tag.get("sheetsCovered") or [],
                "originalAutoApprovalIndex": index,
            }
        )
    payload = {
        "generatedAt": now_iso(),
        "approvedBy": APPROVED_BY,
        "source": SOURCE,
        "basis": "Promoted from validated base-game auto approvals; validation must pass before merge.",
        "tags": converted,
    }
    APPROVED_TAGS_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(APPROVED_TAG_PATH, payload)
    return payload


def main():
    for path in [BASEGAME_MERGE_ROOT, REPORTS_ROOT, APPROVED_TAGS_ROOT]:
        path.mkdir(parents=True, exist_ok=True)

    result = validate_auto_file()
    auto = load_json(AUTO_PATH)
    tags = auto.get("tags", [])
    candidate_ids = [cid for tag in tags for cid in (tag.get("candidateIds") or [])]
    distinct_candidate_ids = sorted(set(candidate_ids))
    found = resolve_candidates(distinct_candidate_ids)

    missing = sorted(set(distinct_candidate_ids) - set(found))
    restricted = []
    tile_946_blocking = []
    for tag in tags:
        layers = set(tag.get("allowedLayers") or [])
        collision = tag.get("collision")
        is_blocking = "Buildings" in layers or collision in {"blocks", "blocked", "blocks_movement"}
        for cid in tag.get("candidateIds") or []:
            meta = found.get(cid, {})
            local_id = meta.get("localTileId")
            blob = f"{meta.get('tilesheetName', '')} {meta.get('copiedImagePath', '')}".lower()
            if any(marker in blob for marker in RESTRICTED_MARKERS):
                restricted.append(cid)
            if int(local_id) == 946 and is_blocking:
                tile_946_blocking.append(cid)

    failures = []
    if result.returncode != 0:
        failures.append("validate_auto_approved_tiles.py returned a non-zero status.")
    if len(tags) != 1050:
        failures.append(f"Expected 1,050 tags, found {len(tags)}.")
    if len(distinct_candidate_ids) != 1815:
        failures.append(f"Expected 1,815 candidates, found {len(distinct_candidate_ids)}.")
    if missing:
        failures.append(f"{len(missing)} candidateIds were missing from canonical candidates.")
    if restricted:
        failures.append(f"{len(restricted)} restricted DeepWoods asset dependencies detected.")
    if tile_946_blocking:
        failures.append(f"{len(tile_946_blocking)} tile 946 candidates attempted Buildings/blocking approval.")

    verdict = "PASS" if not failures else "FAIL"
    lines = [
        "# Base-Game Approval Premerge Validation",
        "",
        f"- Generated: {now_iso()}",
        f"- Dedicated validator result: {'PASS' if result.returncode == 0 else 'FAIL'}",
        f"- Tags: {len(tags)}",
        f"- Distinct candidateIds: {len(distinct_candidate_ids)}",
        f"- Missing candidateIds: {len(missing)}",
        f"- Restricted DeepWoods dependencies: {len(restricted)}",
        f"- Tile 946 Buildings/blocking approvals: {len(tile_946_blocking)}",
        f"- Verdict: {verdict}",
        "",
        "## Class Breakdown",
        *[f"- {key}: {value}" for key, value in Counter(t.get("approvedClass") for t in tags).most_common()],
        "",
        "## Collision Breakdown",
        *[f"- {key}: {value}" for key, value in Counter(t.get("collision") for t in tags).most_common()],
        "",
        "## Failures",
        *(f"- {failure}" for failure in failures),
    ]
    if not failures:
        lines.append("- None.")
    write_text(REPORTS_ROOT / "basegame_approval_premerge_validation.md", "\n".join(lines) + "\n")

    if failures:
        raise SystemExit("Premerge validation failed; no backup or conversion was written.")

    ts = timestamp()
    db_backup, tags_backup = backup_current_state(ts)
    converted = convert_tags(tags)

    state = {
        "generatedAt": now_iso(),
        "timestamp": ts,
        "dbBackupPath": str(db_backup),
        "approvedTagsBackupPath": str(tags_backup),
        "approvedTagsPath": str(APPROVED_TAG_PATH),
        "tagCount": len(converted["tags"]),
        "candidateCount": len(distinct_candidate_ids),
        "validatorOutput": result.stdout,
    }
    write_json(BASEGAME_MERGE_ROOT / "basegame_promotion_state.json", state)
    print(f"premerge validation PASS; wrote {APPROVED_TAG_PATH}")
    print(f"database backup: {db_backup}")
    print(f"approved_tags backup: {tags_backup}")


if __name__ == "__main__":
    main()
