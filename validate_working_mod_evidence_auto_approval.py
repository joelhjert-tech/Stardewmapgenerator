#!/usr/bin/env python3
"""Validate working-mod evidence auto-approval outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TOOL_ROOT = Path(__file__).resolve().parent
WORK_ROOT = TOOL_ROOT / "working_mod_mining"
AUTO_CANDIDATES = WORK_ROOT / "auto_approval" / "working_mod_auto_approval_candidates.json"
APPROVED_TAGS = TOOL_ROOT / "classification" / "approved_tags" / "working_mod_evidence_auto_approved.approved_tags.json"
CANONICAL_PATH = TOOL_ROOT / "classification" / "canonical_tile_candidates.json"
CLASS_SCHEMA = TOOL_ROOT / "classification" / "tile_class_schema.json"
COLLISION_SCHEMA = TOOL_ROOT / "stylepacks" / "collision_schema.json"
REPORT_DIR = TOOL_ROOT / "reports"
VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
SAFE_946_SHEETS = {"spring_outdoorstilesheet.png", "fall_outdoorstilesheet.png", "winter_outdoorstilesheet.png"}
UNSAFE_946_CLASSES = {"wall_body", "wall_corner", "wall_edge", "wall_side", "exterior_wall", "collision_blocker", "hedge_body"}
UNSAFE_946_COLLISIONS = {"blocked", "water_blocked", "custom_requires_review"}


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def iter_json_array_objects(path: Path) -> Iterable[dict[str, Any]]:
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8-sig") as f:
        buf = ""
        started = False
        eof = False
        while not eof:
            chunk = f.read(1024 * 1024)
            if not chunk:
                eof = True
            buf += chunk
            while True:
                stripped = buf.lstrip()
                if not started:
                    if not stripped:
                        buf = ""
                        break
                    if stripped[0] != "[":
                        raise ValueError(f"{path} is not a JSON array")
                    stripped = stripped[1:]
                    started = True
                stripped = stripped.lstrip()
                if stripped.startswith("]"):
                    return
                if stripped.startswith(","):
                    stripped = stripped[1:].lstrip()
                if not stripped:
                    buf = ""
                    break
                try:
                    obj, idx = decoder.raw_decode(stripped)
                except json.JSONDecodeError:
                    buf = stripped
                    break
                if isinstance(obj, dict):
                    yield obj
                buf = stripped[idx:]


def canonical_ids_for(needed: set[str]) -> set[str]:
    if not needed:
        return set()
    found: set[str] = set()
    for obj in iter_json_array_objects(CANONICAL_PATH):
        cid = obj.get("candidateId")
        if cid in needed:
            found.add(cid)
            if found == needed:
                return found
    return found


def tag_uses_unsafe_946(tag: dict[str, Any], candidate_lookup: dict[str, dict[str, Any]]) -> bool:
    for cid in tag.get("candidateIds", []):
        cand = candidate_lookup.get(cid, {})
        if cand.get("localTileId") != 946:
            continue
        sheet = str(tag.get("sourceTilesheet") or cand.get("sourceTilesheet") or "").replace("\\", "/").split("/")[-1].lower()
        klass = tag.get("approvedClass")
        purpose = tag.get("approvedPurpose") or ""
        layers = set(tag.get("allowedLayers") or [])
        collision = tag.get("collision")
        if sheet and sheet not in SAFE_946_SHEETS:
            return True
        if klass in UNSAFE_946_CLASSES:
            return True
        if "Buildings" in layers:
            return True
        if collision in UNSAFE_946_COLLISIONS:
            return True
        if "wall" in purpose.lower() or "block" in purpose.lower() or "body" in purpose.lower():
            return True
    return False


def main() -> int:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    errors: list[str] = []
    warnings: list[str] = []

    class_schema = load_json(CLASS_SCHEMA, {})
    collision_schema = load_json(COLLISION_SCHEMA, {})
    valid_classes = set(class_schema.keys())
    valid_collisions = set(collision_schema.get("enum", []))

    auto_doc = load_json(AUTO_CANDIDATES, {"candidates": []})
    approved_doc = load_json(APPROVED_TAGS, None)
    if approved_doc is None:
        errors.append(f"Missing approved tags file: {APPROVED_TAGS}")
        approved_doc = {"tags": []}
    tags = approved_doc.get("tags")
    if not isinstance(tags, list):
        errors.append("Approved tags file must contain a tags array.")
        tags = []

    candidate_by_id = {cand.get("candidateId"): cand for cand in auto_doc.get("candidates", []) if cand.get("candidateId")}
    tag_ids = {cid for tag in tags for cid in tag.get("candidateIds", [])}
    found_ids = canonical_ids_for(tag_ids)
    missing = sorted(tag_ids - found_ids)
    for cid in missing:
        errors.append(f"Approved candidate does not exist in canonical candidates: {cid}")

    for index, tag in enumerate(tags, start=1):
        prefix = f"tag #{index}"
        confidence = int(tag.get("confidence", 0))
        if confidence < 95:
            errors.append(f"{prefix}: confidence must be >= 95.")
        if tag.get("approvedClass") not in valid_classes:
            errors.append(f"{prefix}: invalid approvedClass {tag.get('approvedClass')}.")
        if not tag.get("approvedPurpose"):
            errors.append(f"{prefix}: approvedPurpose is required.")
        if tag.get("collision") not in valid_collisions:
            errors.append(f"{prefix}: invalid collision {tag.get('collision')}.")
        for layer in tag.get("allowedLayers", []):
            if layer not in VALID_LAYERS:
                errors.append(f"{prefix}: invalid layer {layer}.")
        if tag_uses_unsafe_946(tag, candidate_by_id):
            errors.append(f"{prefix}: tile 946 unsafe role detected.")

        for cid in tag.get("candidateIds", []):
            cand = candidate_by_id.get(cid)
            if cand is None:
                warnings.append(f"{prefix}: candidate {cid} was not present in working_mod_auto_approval_candidates.json.")
                continue
            if not cand.get("safeForAutoApproval"):
                errors.append(f"{prefix}: candidate {cid} is not marked safeForAutoApproval.")
            if cand.get("confidenceScore", 0) < 95:
                errors.append(f"{prefix}: candidate {cid} confidence is below 95.")
            if cand.get("riskFlags"):
                errors.append(f"{prefix}: candidate {cid} has risk flags: {', '.join(cand['riskFlags'])}.")
            if cand.get("conflicts"):
                errors.append(f"{prefix}: candidate {cid} has conflicts.")
            if not cand.get("sourceTilesheet"):
                errors.append(f"{prefix}: candidate {cid} has unknown tilesheet.")

    lines = [
        "# Working Mod Evidence Auto-Approval Validation",
        "",
        f"- Generated: {generated_at}",
        f"- Result: {'PASS' if not errors else 'FAIL'}",
        f"- Approved tag entries: {len(tags)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
        lines.append("")
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    if not tags:
        lines.extend(["## Notes", "", "- The working-mod auto-approved tag file is valid and empty. No working-mod evidence met the strict auto-approval gate."])
    write_text(REPORT_DIR / "working_mod_evidence_auto_approval_validation.md", "\n".join(lines))
    print(f"Working mod evidence auto-approval validation {'PASS' if not errors else 'FAIL'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
