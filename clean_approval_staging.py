#!/usr/bin/env python3
"""Inventory and quarantine unsafe approval staging files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from approval_validation_utils import (
    APPROVED_TAGS_DIR,
    CONFIRMATION_ROOT,
    CONFLICT_ROOT,
    DUPLICATE_BROWSER_COPY_NAME,
    OFFICIAL_APPROVED_GLOB,
    REPORTS_ROOT,
    TOOL_ROOT,
    approval_file_digest,
    candidate_lookup,
    classify_against_stronger_db,
    db_approval_lookup,
    load_json,
    official_approved_tag_files,
    safe_move_to_quarantine,
    suspicious_approval_files,
    tag_candidate_ids,
    tags_from_doc,
    validate_tile_946_tag,
    write_json,
    write_text,
)


SCAN_DIRS = [
    APPROVED_TAGS_DIR,
    CONFLICT_ROOT,
    CONFIRMATION_ROOT,
]
DUPLICATE_QUARANTINE_DIR = CONFLICT_ROOT / "duplicate_staging_files"
TILE_946_QUARANTINE_DIR = CONFLICT_ROOT / "tile_946_quarantine"


def all_json_files() -> list[Path]:
    paths: list[Path] = []
    for folder in SCAN_DIRS:
        if folder.exists():
            paths.extend(sorted(folder.rglob("*.json")))
    return sorted(set(paths))


def file_tags(path: Path) -> tuple[bool, list[dict[str, Any]], str | None]:
    try:
        doc = load_json(path)
        return True, tags_from_doc(doc), None
    except Exception as exc:
        return False, [], str(exc)


def duplicate_of_conflict(path: Path) -> bool:
    if not path.exists():
        return False
    digest = approval_file_digest(path)
    for other in CONFLICT_ROOT.rglob("*.json") if CONFLICT_ROOT.exists() else []:
        if other.resolve() == path.resolve():
            continue
        try:
            if approval_file_digest(other) == digest:
                return True
        except Exception:
            continue
    return False


def inventory_record(path: Path, lookup: dict[str, dict], approvals: dict[str, dict]) -> dict[str, Any]:
    json_parses, tags, parse_error = file_tags(path)
    candidate_ids = sorted(set(cid for tag in tags for cid in tag_candidate_ids(tag)))
    tile_946_errors = [err for tag in tags for err in validate_tile_946_tag(tag, lookup)]
    contains_tile_946 = any("tile 946" in err.lower() or any(cid.endswith("_946") for cid in tag_candidate_ids(tag)) for tag in tags for err in (validate_tile_946_tag(tag, lookup) or [""]))
    already_approved = False
    conflict = False
    conflict_notes: list[str] = []
    confirmation = False
    manual_review_data = False
    for tag in tags:
        is_manual_review = tag.get("source") in {"manual_review", "accepted_proposed_tag"}
        if is_manual_review:
            manual_review_data = True
        status, notes = classify_against_stronger_db(tag, lookup, approvals)
        if is_manual_review and status == "conflict":
            conflict = True
            conflict_notes.extend(notes[:4])
        elif is_manual_review and status == "confirmation":
            confirmation = True
        for cid in tag_candidate_ids(tag):
            if cid in approvals:
                already_approved = True
    in_approved = APPROVED_TAGS_DIR in path.resolve().parents
    in_conflicts = CONFLICT_ROOT in path.resolve().parents
    in_confirmations = CONFIRMATION_ROOT in path.resolve().parents
    matches_glob = in_approved and path.match(f"*/{OFFICIAL_APPROVED_GLOB}")
    duplicate_name = bool(DUPLICATE_BROWSER_COPY_NAME.search(path.name))
    duplicate_conflict = duplicate_of_conflict(path) if in_approved else False
    status = "needs_review"
    recommendation = "Review manually before moving or importing."
    if in_confirmations:
        status = "confirmation_only"
        recommendation = "Keep as confirmation evidence; do not merge into approved_tags."
    elif in_conflicts:
        status = "conflict_quarantined"
        recommendation = "Keep quarantined unless a human explicitly resolves the conflict."
    elif in_approved and duplicate_name:
        status = "duplicate_browser_copy"
        recommendation = f"Move to {DUPLICATE_QUARANTINE_DIR.relative_to(TOOL_ROOT)}."
    elif in_approved and not matches_glob and path in suspicious_approval_files():
        status = "skipped_by_glob"
        recommendation = f"Move suspicious skipped approval data to {DUPLICATE_QUARANTINE_DIR.relative_to(TOOL_ROOT)}."
    elif in_approved and tile_946_errors:
        status = "needs_review"
        recommendation = f"Move staged tile 946 approval to {TILE_946_QUARANTINE_DIR.relative_to(TOOL_ROOT)} unless it has explicit 946 quarantine safety notes."
    elif in_approved and conflict:
        status = "needs_review"
        recommendation = f"Move conflicting manual approval to {CONFLICT_ROOT.relative_to(TOOL_ROOT)}."
    elif in_approved and confirmation:
        status = "confirmation_only"
        recommendation = f"Move matching manual confirmation to {CONFIRMATION_ROOT.relative_to(TOOL_ROOT)}."
    elif in_approved and json_parses:
        status = "active_validated"
        recommendation = "Leave in approved_tags; validator should scan it."
    if duplicate_conflict:
        recommendation = f"Duplicate of already quarantined conflict; move to {DUPLICATE_QUARANTINE_DIR.relative_to(TOOL_ROOT)}."
    return {
        "path": str(path),
        "relativePath": str(path.relative_to(TOOL_ROOT)),
        "filename": path.name,
        "matchesValidatorGlob": bool(matches_glob),
        "jsonParses": json_parses,
        "parseError": parse_error,
        "tagCount": len(tags),
        "candidateIds": candidate_ids,
        "containsTile946": bool(contains_tile_946),
        "containsAlreadyApprovedCandidate": already_approved,
        "containsConflictWithApprovedDb": conflict,
        "containsManualReviewData": manual_review_data,
        "conflictNotes": sorted(set(conflict_notes))[:20],
        "duplicateBrowserCopyName": duplicate_name,
        "duplicateOfQuarantinedConflict": duplicate_conflict,
        "tile946ValidationErrors": sorted(set(tile_946_errors)),
        "status": status,
        "recommendation": recommendation,
    }


def move_targets(records: list[dict[str, Any]]) -> list[tuple[Path, Path, str]]:
    moves: list[tuple[Path, Path, str]] = []
    for record in records:
        source = Path(record["path"])
        if not source.exists() or APPROVED_TAGS_DIR not in source.resolve().parents:
            continue
        if record["status"] in {"duplicate_browser_copy", "skipped_by_glob"} or record["duplicateOfQuarantinedConflict"]:
            moves.append((source, DUPLICATE_QUARANTINE_DIR, record["recommendation"]))
        elif record["containsTile946"] and record["tile946ValidationErrors"]:
            moves.append((source, TILE_946_QUARANTINE_DIR, record["recommendation"]))
        elif record["containsConflictWithApprovedDb"]:
            moves.append((source, CONFLICT_ROOT, record["recommendation"]))
    return moves


def write_inventory(records: list[dict[str, Any]], move_log: list[dict[str, Any]]) -> None:
    payload = {
        "generatedAt": __import__("approval_validation_utils").now_iso(),
        "records": records,
        "moves": move_log,
    }
    write_json(REPORTS_ROOT / "approval_staging_inventory.json", payload)
    lines = [
        "# Approval Staging Inventory",
        "",
        f"- Files inventoried: {len(records)}",
        f"- Files moved/quarantined: {len(move_log)}",
        "",
        "## Files",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"### `{record['relativePath']}`",
                "",
                f"- matchesValidatorGlob: `{record['matchesValidatorGlob']}`",
                f"- jsonParses: `{record['jsonParses']}`",
                f"- tagCount: `{record['tagCount']}`",
                f"- candidateIds: `{', '.join(record['candidateIds'][:20]) or 'none'}`",
                f"- containsTile946: `{record['containsTile946']}`",
                f"- containsAlreadyApprovedCandidate: `{record['containsAlreadyApprovedCandidate']}`",
                f"- containsConflictWithApprovedDb: `{record['containsConflictWithApprovedDb']}`",
                f"- status: `{record['status']}`",
                f"- recommendation: {record['recommendation']}",
                "",
            ]
        )
    write_text(REPORTS_ROOT / "approval_staging_inventory.md", "\n".join(lines))


def write_move_log(move_log: list[dict[str, Any]]) -> None:
    lines = [
        "# Duplicate Approval File Cleanup",
        "",
        f"- Files moved: {len(move_log)}",
        "",
    ]
    if not move_log:
        lines.append("- No duplicate/suspicious approval staging files needed to be moved.")
    for move in move_log:
        lines.extend(
            [
                f"## `{move['filename']}`",
                "",
                f"- From: `{move['from']}`",
                f"- To: `{move['to']}`",
                f"- Reason: {move['reason']}",
                "",
            ]
        )
    write_text(REPORTS_ROOT / "duplicate_approval_file_cleanup.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move quarantined files. Without this, inventory only.")
    args = parser.parse_args()
    lookup = candidate_lookup()
    approvals = db_approval_lookup(lookup)
    records = [inventory_record(path, lookup, approvals) for path in all_json_files()]
    move_log: list[dict[str, Any]] = []
    if args.apply:
        for source, target_dir, reason in move_targets(records):
            target = safe_move_to_quarantine(source, target_dir)
            move_log.append({
                "filename": source.name,
                "from": str(source.relative_to(TOOL_ROOT)),
                "to": str(target.relative_to(TOOL_ROOT)),
                "reason": reason,
            })
        records = [inventory_record(path, lookup, approvals) for path in all_json_files()]
    write_inventory(records, move_log)
    write_move_log(move_log)
    print(f"Approval staging inventory complete; files={len(records)} moves={len(move_log)} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
