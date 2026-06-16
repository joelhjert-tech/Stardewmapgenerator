#!/usr/bin/env python3
"""Import completed structural manual decisions into approved tag format.

This script does nothing destructive. It only writes approved tags when
`structural_learning/structural_manual_decisions.json` exists and contains
explicit approved decisions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import approval_validation_utils as approval_utils
from mine_structural_tile_candidates import MISSING_ROLES, ROLE_CLASS_DEFAULTS


TOOL_ROOT = Path(__file__).resolve().parent
STRUCTURAL_ROOT = TOOL_ROOT / "structural_learning"
CANDIDATES_PATH = STRUCTURAL_ROOT / "candidates" / "structural_tile_candidates_by_role.json"
PATH_BASE_CANDIDATES_PATH = STRUCTURAL_ROOT / "path_base_review" / "path_base_candidates.json"
DECISIONS_PATH = STRUCTURAL_ROOT / "structural_manual_decisions.json"
MINIMUM_DECISIONS_PATH = STRUCTURAL_ROOT / "minimum_review" / "decisions" / "minimum_structural_decisions.json"
PATH_BASE_DECISIONS_PATH = STRUCTURAL_ROOT / "path_base_review" / "decisions" / "path_base_decisions.json"
APPROVED_OUT = TOOL_ROOT / "classification" / "approved_tags" / "structural_manual_approved.approved_tags.json"
MINIMUM_APPROVED_OUT = TOOL_ROOT / "classification" / "approved_tags" / "minimum_structural_manual_approved.approved_tags.json"
PATH_BASE_APPROVED_OUT = TOOL_ROOT / "classification" / "approved_tags" / "path_base_manual_approved.approved_tags.json"
REPORT_PATH = TOOL_ROOT / "reports" / "structural_manual_import_report.md"
MINIMUM_REPORT_PATH = TOOL_ROOT / "reports" / "minimum_structural_manual_import_report.md"
PATH_BASE_REPORT_PATH = TOOL_ROOT / "reports" / "path_base_manual_import_report.md"
CLASS_SCHEMA = TOOL_ROOT / "classification" / "tile_class_schema.json"
CONFLICT_IMPORT_DIR = TOOL_ROOT / "review" / "manual_approval_conflicts" / "structural_import_conflicts"
PATH_BASE_CONFLICT_IMPORT_DIR = TOOL_ROOT / "review" / "manual_approval_conflicts" / "path_base_import_conflicts"
CONFIRMATION_IMPORT_DIR = TOOL_ROOT / "review" / "approval_confirmations" / "structural_import_confirmations"

VALID_DECISIONS = {"approve", "reject", "unsure"}
VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
VALID_COLLISIONS = {"unknown", "walkable", "blocked", "blocks", "blocked_or_special", "water_blocked", "decorative_front", "overlay_only", "marker_only", "custom_requires_review"}
BLOCKING_ROLES = {"wall_body", "wall_corner", "wall_edge"}
BLOCKING_COLLISIONS = {"blocked", "blocks", "water_blocked"}
EXTRA_ROLE_CLASS_DEFAULTS = {
    "path_base": ("path_base", "walkable_base_path", ["Back"], "walkable"),
}
ALL_ROLE_CLASS_DEFAULTS = {**ROLE_CLASS_DEFAULTS, **EXTRA_ROLE_CLASS_DEFAULTS}
ALL_IMPORT_ROLES = set(MISSING_ROLES) | set(EXTRA_ROLE_CLASS_DEFAULTS)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_candidate_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if CANDIDATES_PATH.exists():
        doc = load_json(CANDIDATES_PATH)
        for role, items in doc.get("roles", {}).items():
            for item in items:
                item = dict(item)
                item["roleName"] = role
                for key in [item.get("structuralCandidateId"), item.get("candidateId")]:
                    if key:
                        lookup[str(key)] = item
                for key in item.get("mappedCandidateIds") or []:
                    lookup[str(key)] = item
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
    return lookup


def normalize_decision(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_layers(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(layer) for layer in value if layer]
    return []


def validate_one(role: str, decision: dict[str, Any], candidate: dict[str, Any], valid_classes: set[str]) -> list[str]:
    errors = []
    approved_class = decision.get("approvedClass")
    layers = normalize_layers(decision.get("allowedLayers") or [])
    collision = decision.get("collision")
    if approved_class not in valid_classes:
        errors.append(f"approvedClass `{approved_class}` is not in tile_class_schema.json")
    for layer in layers:
        if layer not in VALID_LAYERS:
            errors.append(f"invalid layer `{layer}`")
    if collision not in VALID_COLLISIONS:
        errors.append(f"invalid collision `{collision}`")
    try:
        local_id = int(candidate.get("localTileId", -1))
    except Exception:
        local_id = -1
    if local_id == 946 and (role in BLOCKING_ROLES or collision in BLOCKING_COLLISIONS or "Buildings" in layers):
        errors.append("tile 946 cannot be approved for wall/body/blocking/collision roles")
    if local_id == 946 and role == "path_base":
        errors.append("tile 946 cannot be approved as path_base")
    if "AlwaysFront" in layers and collision in BLOCKING_COLLISIONS:
        errors.append("AlwaysFront approvals cannot carry blocking collision")
    if role == "path_base":
        if approved_class != "path_base":
            errors.append("path_base decisions must use approvedClass `path_base`")
        if set(layers) != {"Back"}:
            errors.append("path_base decisions must use allowedLayers exactly [`Back`]")
        if collision != "walkable":
            errors.append("path_base decisions must use collision `walkable`")
        errors.extend(approval_utils.path_base_candidate_gate_errors(candidate, allow_explicit_non_back_note=False))
    return errors


def iter_decisions(decisions_doc: dict[str, Any]):
    if isinstance(decisions_doc.get("decisions"), list):
        for decision in decisions_doc["decisions"]:
            yield decision.get("roleName"), decision
    else:
        for role, entries in (decisions_doc.get("roles") or {}).items():
            for decision in entries or []:
                yield role, decision


def run_import(decisions_path: Path, approved_out: Path, report_path: Path, mode: str) -> tuple[int, dict[str, Any]]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_title = {
        "full": "# Structural Manual Import Report",
        "minimum": "# Minimum Structural Manual Import Report",
        "path_base": "# Path Base Manual Import Report",
    }.get(mode, "# Structural Manual Import Report")
    if not decisions_path.exists():
        write_text(
            report_path,
            "\n".join([
                report_title,
                "",
                f"- Generated: {now_iso()}",
                "- Result: SKIPPED",
                f"- Reason: `{decisions_path}` does not exist.",
                "- No approved tags were written.",
            ]),
        )
        return 0, {"result": "SKIPPED", "tags": 0, "errors": 0, "reason": "decisions file missing"}

    schema = load_json(CLASS_SCHEMA)
    valid_classes = set(schema)
    candidates = load_candidate_lookup()
    approval_candidate_lookup = approval_utils.candidate_lookup()
    approved_db = approval_utils.db_approval_lookup(approval_candidate_lookup)
    decisions_doc = load_json(decisions_path)
    errors: list[str] = []
    warnings: list[str] = []
    tags: list[dict[str, Any]] = []
    conflict_tags: list[dict[str, Any]] = []
    confirmation_tags: list[dict[str, Any]] = []
    approved_at = now_iso()

    rejected = 0
    unsure = 0
    for item_index, (role, decision) in enumerate(iter_decisions(decisions_doc)):
        if role not in ALL_IMPORT_ROLES:
            errors.append(f"Unknown structural role `{role}`.")
            continue
        label = f"{role} decision #{item_index + 1}"
        value = normalize_decision(decision.get("decision"))
        if value not in VALID_DECISIONS:
            errors.append(f"{label}: decision must be approve/reject/unsure.")
            continue
        if value == "reject":
            rejected += 1
            continue
        if value == "unsure":
            unsure += 1
            continue
        key = decision.get("candidateId") or decision.get("structuralCandidateId")
        candidate = candidates.get(key)
        if not candidate:
            errors.append(f"{label}: unknown candidateId/structuralCandidateId `{key}`.")
            continue
        mapped_ids = list(dict.fromkeys(candidate.get("mappedCandidateIds") or ([candidate.get("candidateId")] if candidate.get("candidateId") else [])))
        if not mapped_ids:
            errors.append(f"{label}: candidate has no mapped canonical candidateIds; cannot create mergeable approved tag.")
            continue
        item_errors = validate_one(role, decision, candidate, valid_classes)
        if item_errors:
            errors.extend(f"{label}: {err}" for err in item_errors)
            continue
        defaults = ALL_ROLE_CLASS_DEFAULTS[role]
        review_pack_id = "minimum_structural_review_pack" if mode == "minimum" else f"{role}_review_pack"
        if mode == "path_base":
            review_pack_id = "path_base_review_pack"
        evidence_source = "structural_learning/candidates/structural_tile_candidates_by_role.json"
        evidence_name = "structural_manual_review"
        if mode == "path_base":
            evidence_source = "structural_learning/path_base_review/path_base_candidates.json"
            evidence_name = "path_base_manual_review"
        structural_candidate_id = candidate.get("structuralCandidateId") or candidate.get("pathBaseCandidateId")
        approved_purpose = decision.get("approvedPurpose") or defaults[1]
        approved_layers = normalize_layers(decision.get("allowedLayers")) or list(defaults[2])
        approved_collision = decision.get("collision") or defaults[3]
        tag = {
            "reviewPackId": review_pack_id,
            "candidateIds": mapped_ids,
            "approvedClass": decision.get("approvedClass"),
            "approvedPurpose": approved_purpose,
            "allowedLayers": approved_layers,
            "collision": approved_collision,
            "terrainSet": decision.get("terrainSet"),
            "terrainA": decision.get("terrainA"),
            "terrainB": decision.get("terrainB"),
            "edgeMask": decision.get("edgeMask") or [],
            "cornerMask": decision.get("cornerMask") or [],
            "transitionType": decision.get("transitionType"),
            "footprint": decision.get("footprint"),
            "allowedRooms": decision.get("allowedRooms") or [],
            "avoidNear": decision.get("avoidNear") or [],
            "weight": decision.get("weight", 1),
            "approvedBy": "human",
            "approvedAt": approved_at,
            "source": "manual_review",
            "confidence": 100,
            "evidenceSourceFile": evidence_source,
            "evidenceSummary": f"Manual structural role approval for {role}; mined from vanilla layer grammar and reviewed by {decisions_doc.get('reviewer', 'Joel')}.",
            "safetyNotes": "Structural approval imported only after explicit manual decision. Tile 946 blocking quarantine enforced.",
            "structuralRole": role,
            "structuralCandidateId": structural_candidate_id,
            "vanillaSourceTilesheet": candidate.get("sourceTilesheet"),
            "vanillaLocalTileId": candidate.get("localTileId"),
            "usageProfiles": [
                {
                    "profileId": f"{role}_{decision.get('approvedClass')}",
                    "approvedClass": decision.get("approvedClass"),
                    "approvedPurpose": approved_purpose,
                    "allowedLayers": approved_layers,
                    "collision": approved_collision,
                    "layerRole": role,
                    "evidence": [
                        {
                            "source": evidence_name,
                            "structuralCandidateId": structural_candidate_id,
                            "evidenceScore": candidate.get("evidenceScore"),
                        }
                    ],
                    "notes": decision.get("notes", ""),
                }
            ],
        }
        tile_946_errors = approval_utils.validate_tile_946_tag(tag, approval_candidate_lookup)
        if tile_946_errors:
            errors.extend(f"{label}: {err}" for err in tile_946_errors)
            continue
        status, status_notes = approval_utils.classify_against_stronger_db(tag, approval_candidate_lookup, approved_db)
        if status == "conflict":
            conflict_tags.append({
                **tag,
                "quarantineReason": "manual approval conflicts with stronger existing approved DB metadata",
                "conflictDetails": status_notes,
                "quarantinedAt": now_iso(),
            })
            continue
        if status == "confirmation":
            confirmation_tags.append({
                **tag,
                "confirmationReason": "manual approval matches stronger existing approved DB metadata",
                "confirmedAt": now_iso(),
            })
            continue
        tags.append(tag)

    if errors:
        result = "FAIL"
    else:
        result = "PASS"
        conflict_dir = PATH_BASE_CONFLICT_IMPORT_DIR if mode == "path_base" else CONFLICT_IMPORT_DIR
        if tags:
            write_json(
                approved_out,
                {
                    "generatedAt": approved_at,
                    "approvedBy": "human",
                    "source": "manual_review",
                    "reviewType": {
                        "full": "structural_tile_roles",
                        "minimum": "minimum_structural_tile_roles",
                        "path_base": "path_base_first_visual_unlock",
                    }.get(mode, "structural_tile_roles"),
                    "tags": tags,
                },
            )
        if conflict_tags:
            write_json(
                conflict_dir / f"{mode}_structural_manual_conflicts.json",
                {
                    "generatedAt": approved_at,
                    "source": "manual_review_import_conflict_quarantine",
                    "tags": conflict_tags,
                },
            )
        if confirmation_tags:
            write_json(
                CONFIRMATION_IMPORT_DIR / f"{mode}_structural_manual_confirmations.json",
                {
                    "generatedAt": approved_at,
                    "source": "manual_review_confirmation_only",
                    "tags": confirmation_tags,
                },
            )

    lines = [
        report_title,
        "",
        f"- Generated: {now_iso()}",
        f"- Result: {result}",
        f"- Tags ready/written: {len(tags)}",
        f"- Confirmation-only tags: {len(confirmation_tags)}",
        f"- Conflict-quarantined tags: {len(conflict_tags)}",
        f"- Rejected decisions: {rejected}",
        f"- Unsure decisions: {unsure}",
        f"- Output: `{approved_out}`" if result == "PASS" and tags else "- Output: no approved_tags file written.",
        f"- Conflict output: `{PATH_BASE_CONFLICT_IMPORT_DIR if mode == 'path_base' else CONFLICT_IMPORT_DIR}`" if conflict_tags else "- Conflict output: none.",
        f"- Confirmation output: `{CONFIRMATION_IMPORT_DIR}`" if confirmation_tags else "- Confirmation output: none.",
    ]
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {err}" for err in errors)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warn}" for warn in warnings)
    write_text(report_path, "\n".join(lines))
    return (0 if not errors else 1), {"result": result, "tags": len(tags), "errors": len(errors), "rejected": rejected, "unsure": unsure}


def main() -> int:
    code_full, summary_full = run_import(DECISIONS_PATH, APPROVED_OUT, REPORT_PATH, "full")
    code_min, summary_min = run_import(MINIMUM_DECISIONS_PATH, MINIMUM_APPROVED_OUT, MINIMUM_REPORT_PATH, "minimum")
    code_path, summary_path = run_import(PATH_BASE_DECISIONS_PATH, PATH_BASE_APPROVED_OUT, PATH_BASE_REPORT_PATH, "path_base")
    print(
        "Structural import complete; "
        f"full={summary_full['result']} tags={summary_full['tags']} errors={summary_full['errors']}; "
        f"minimum={summary_min['result']} tags={summary_min['tags']} errors={summary_min['errors']}; "
        f"path_base={summary_path['result']} tags={summary_path['tags']} errors={summary_path['errors']}"
    )
    return 1 if code_full or code_min or code_path else 0


if __name__ == "__main__":
    raise SystemExit(main())
