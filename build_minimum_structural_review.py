#!/usr/bin/env python3
"""Build the smallest structural review pack for a first visual prototype.

This prepares review assets only. It does not approve tiles and does not
generate production maps.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from mine_structural_tile_candidates import ROLE_CLASS_DEFAULTS, base_key, tile_geometry, crop_tile, crop_context


TOOL_ROOT = Path(__file__).resolve().parent
STRUCTURAL_ROOT = TOOL_ROOT / "structural_learning"
MIN_ROOT = STRUCTURAL_ROOT / "minimum_review"
MIN_PREVIEW_DIR = MIN_ROOT / "previews"
MIN_DECISION_DIR = MIN_ROOT / "decisions"
REPORT_DIR = TOOL_ROOT / "reports"
CANDIDATES_PATH = STRUCTURAL_ROOT / "candidates" / "structural_tile_candidates_by_role.json"
UNPACKED_BASEGAME = TOOL_ROOT / "mission_assets" / "unpacked_basegame"

TARGET_ROLES = ["wall_body", "wall_top", "wall_corner", "wall_edge", "path_transition", "shadow"]
OPTIONAL_ROLES = ["canopy_overlay", "water_edge"]
LIMITS = {
    "wall_body": 20,
    "wall_top": 20,
    "wall_corner": 24,
    "wall_edge": 24,
    "path_transition": 24,
    "shadow": 16,
    "canopy_overlay": 16,
    "water_edge": 16,
}


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


def ensure_dirs() -> None:
    for path in [MIN_ROOT, MIN_PREVIEW_DIR, MIN_DECISION_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def build_sheet_image_index() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in UNPACKED_BASEGAME.glob("*.png"):
        key = base_key(path.name)
        current = out.get(key)
        localized = re.search(r"\.[a-z]{2}-[A-Z]{2}\.png$", path.name)
        if current is None or (re.search(r"\.[a-z]{2}-[A-Z]{2}\.png$", current.name) and not localized):
            out[key] = path
    return out


def candidate_score(item: dict[str, Any], role: str) -> tuple:
    risks = set(item.get("riskFlags") or [])
    risky_penalty = len(risks) * 2000
    if item.get("localTileId") == 946:
        risky_penalty += 100000
    mapped_bonus = 2000 if item.get("candidateId") or item.get("mappedCandidateIds") else 0
    map_count = len(item.get("exampleMaps") or {})
    stack_count = len(item.get("stackPatternSummary") or {})
    return (
        float(item.get("evidenceScore") or 0) + mapped_bonus + map_count * 25 + stack_count * 10 - risky_penalty,
        -len(risks),
        map_count,
    )


def select_role_candidates(role: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = []
    for item in items:
        if item.get("localTileId") == 946 and role != "canopy_overlay":
            continue
        if role == "canopy_overlay" and item.get("localTileId") == 946:
            # Keep 946 out of approval candidates. It can be documented as quarantine evidence elsewhere.
            continue
        if "tile_946_forbidden_for_blocking_role" in set(item.get("riskFlags") or []):
            continue
        if item.get("candidateId") is None and not item.get("mappedCandidateIds"):
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda item: candidate_score(item, role), reverse=True)[: LIMITS[role]]


def entry_for_pack(item: dict[str, Any], role: str, preview_path: str) -> dict[str, Any]:
    return {
        "candidateId": item.get("candidateId"),
        "structuralCandidateId": item.get("structuralCandidateId"),
        "mappedCandidateIds": item.get("mappedCandidateIds") or [],
        "roleName": role,
        "proposedClass": item.get("proposedClass"),
        "proposedPurpose": item.get("proposedPurpose"),
        "proposedAllowedLayers": item.get("proposedAllowedLayers"),
        "proposedCollision": item.get("proposedCollision"),
        "sourceTilesheet": item.get("sourceTilesheet"),
        "localTileId": item.get("localTileId"),
        "layer": item.get("layer"),
        "evidenceScore": item.get("evidenceScore"),
        "exampleMaps": item.get("exampleMaps"),
        "exampleCoordinates": item.get("xYExamples"),
        "neighborPatternSummary": item.get("neighborPatternSummary"),
        "stackPatternSummary": item.get("stackPatternSummary"),
        "riskFlags": item.get("riskFlags") or [],
        "previewPath": preview_path,
        "humanDecision": None,
    }


def make_previews(selected: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, str]]:
    sheet_images = build_sheet_image_index()
    font = ImageFont.load_default()
    preview_paths: dict[str, dict[str, str]] = {}
    for role, items in selected.items():
        if not items:
            continue
        cell_w, cell_h = 128, 92
        cols = 4
        rows = math.ceil(len(items) / cols)
        clean = Image.new("RGBA", (cols * cell_w, rows * cell_h), (28, 28, 32, 255))
        labeled = Image.new("RGBA", (cols * cell_w, rows * cell_h), (28, 28, 32, 255))
        dc = ImageDraw.Draw(clean)
        dl = ImageDraw.Draw(labeled)
        for index, item in enumerate(items):
            x0 = (index % cols) * cell_w
            y0 = (index // cols) * cell_h
            sheet = item["sourceTilesheet"]
            local_id = int(item["localTileId"])
            img_path = sheet_images.get(base_key(sheet))
            if img_path and img_path.exists():
                with Image.open(img_path).convert("RGBA") as source:
                    tile_w, tile_h, columns = tile_geometry({}, sheet, source)
                    tile = crop_tile(source, local_id, columns, tile_w, tile_h).resize((32, 32), Image.Resampling.NEAREST)
                    context = crop_context(source, local_id, columns, tile_w, tile_h, radius=2).resize((64, 64), Image.Resampling.NEAREST)
                    for canvas in [clean, labeled]:
                        canvas.alpha_composite(context, (x0 + 4, y0 + 4))
                        canvas.alpha_composite(tile, (x0 + 82, y0 + 12))
            for draw in [dc, dl]:
                draw.rectangle((x0, y0, x0 + cell_w - 1, y0 + cell_h - 1), outline=(75, 75, 84))
                if item.get("riskFlags"):
                    draw.rectangle((x0 + 2, y0 + 2, x0 + cell_w - 3, y0 + cell_h - 3), outline=(255, 178, 65), width=2)
            label = f"{sheet}:{local_id}"
            cid = item.get("candidateId") or item.get("structuralCandidateId", "")
            dl.text((x0 + 4, y0 + 70), label, fill=(235, 235, 235), font=font)
            dl.text((x0 + 4, y0 + 81), str(cid)[0:30], fill=(180, 220, 255), font=font)
            if item.get("localTileId") == 946:
                dl.rectangle((x0 + 76, y0 + 4, x0 + 124, y0 + 18), outline=(255, 75, 75), width=1)
                dl.text((x0 + 79, y0 + 6), "946 Q", fill=(255, 110, 110), font=font)
        clean_path = MIN_PREVIEW_DIR / f"{role}_minimum_clean.png"
        labeled_path = MIN_PREVIEW_DIR / f"{role}_minimum_labeled.png"
        clean.save(clean_path)
        labeled.save(labeled_path)
        preview_paths[role] = {"clean": str(clean_path), "labeled": str(labeled_path)}
    return preview_paths


def write_decision_template(pack: dict[str, Any]) -> Path:
    decisions = []
    for entry in pack["candidates"]:
        decisions.append({
            "candidateId": entry.get("candidateId") or "",
            "structuralCandidateId": entry.get("structuralCandidateId") or "",
            "roleName": entry["roleName"],
            "decision": "approve / reject / unsure",
            "approvedClass": entry["proposedClass"],
            "approvedPurpose": entry["proposedPurpose"],
            "allowedLayers": entry["proposedAllowedLayers"],
            "collision": entry["proposedCollision"],
            "notes": "",
        })
    doc = {
        "reviewType": "minimum_structural_tile_roles",
        "reviewer": "Joel",
        "instructions": "Approve only tiles that clearly match the proposed role. Use unsure if not certain.",
        "decisions": decisions,
    }
    path = MIN_DECISION_DIR / "minimum_structural_decisions.template.json"
    write_json(path, doc)
    return path


def write_instructions(pack: dict[str, Any], previews: dict[str, dict[str, str]], decision_template: Path) -> None:
    lines = [
        "# Minimum Structural Review Instructions",
        "",
        f"- Generated: {now_iso()}",
        f"- Review pack: `{MIN_ROOT / 'minimum_structural_review_pack.json'}`",
        f"- Decision template: `{decision_template}`",
        "",
        "## Preview Files",
        "",
    ]
    for role, paths in previews.items():
        lines.append(f"- `{role}` clean: `{paths['clean']}`")
        lines.append(f"- `{role}` labeled: `{paths['labeled']}`")
    lines.extend([
        "",
        "Use clean previews to inspect art/context without text on top of the tile art. Use labeled previews to map a tile back to `candidateId`, local tile ID, role, and source sheet.",
        "",
        "## What To Approve",
        "",
        "- `wall_body`: a clear blocking body tile suitable for `Buildings`.",
        "- `wall_top`: a clear non-collision top/front overlay paired with wall bodies.",
        "- `wall_corner`: four clear corner/turn pieces.",
        "- `wall_edge`: four clear edge/cap/run pieces.",
        "- `path_transition`: a clear path-to-ground transition group.",
        "- `shadow`: a non-blocking shadow/dark-ground support tile if visually needed.",
        "- `canopy_overlay`: approve only if the first test style requires forest canopy.",
        "- `water_edge`: approve only if the first test map includes water.",
        "",
        "## What To Reject",
        "",
        "- Any tile whose role is unclear from context.",
        "- Any tile that appears to be general ground/floor rather than a structural role.",
        "- Any AlwaysFront tile proposed with blocking collision.",
        "- Tile 946 for wall/body/blocking/collision roles.",
        "",
        "## What To Mark Unsure",
        "",
        "- Tiles that might be correct but need orientation, seasonal, or layer-stack confirmation.",
        "- Candidates with risk flags unless the role is still clearly correct.",
        "",
        "## Tile 946",
        "",
        "Tile 946 remains quarantined. It must not be approved as `wall_body`, `wall_corner`, `wall_edge`, `Buildings`, blocker, or collision. If reviewed at all, it belongs only in a separate overlay/canopy profile review.",
        "",
        "## Minimum Useful Target",
        "",
        "- 1 coherent `wall_body` group",
        "- 1 coherent `wall_top` group",
        "- 4 wall corners",
        "- 4 wall edges/caps",
        "- 1 `path_transition` group",
        "- 1 `shadow` group if visually needed",
        "- `canopy_overlay` only if the selected stylepack requires forest canopy",
        "- `water_edge` only if the first test map includes water",
    ])
    write_text(REPORT_DIR / "minimum_structural_review_instructions.md", "\n".join(lines))


def write_readiness_no_decisions(pack: dict[str, Any]) -> None:
    doc = {
        "generatedAt": now_iso(),
        "completedDecisionsFileExists": False,
        "reviewPackCreated": True,
        "approvalsImported": 0,
        "approvalsRejected": 0,
        "unsureEntries": 0,
        "roleCoverageAfterApproval": {},
        "productionBlockersRemaining": ["waiting_for_human_decisions"],
        "oneVisualPrototypeMapPossible": False,
        "closestStylepack": None,
        "message": "Waiting for human decisions. No approvals imported.",
    }
    write_json(REPORT_DIR / "minimum_structural_readiness_after_decisions.json", doc)
    write_text(
        REPORT_DIR / "minimum_structural_readiness_after_decisions.md",
        "\n".join([
            "# Minimum Structural Readiness After Decisions",
            "",
            f"- Generated: {doc['generatedAt']}",
            "- Completed decisions file exists: NO",
            "- Review pack created: YES",
            "- Approvals imported: 0",
            "- Status: waiting for human decisions.",
            "- One visual prototype map possible now: NO",
        ]),
    )


def write_summary(pack: dict[str, Any], previews: dict[str, dict[str, str]], decision_template: Path) -> None:
    counts = Counter(entry["roleName"] for entry in pack["candidates"])
    lines = [
        "# Minimum Structural Review Summary",
        "",
        f"- Generated: {now_iso()}",
        f"- Review pack path: `{MIN_ROOT / 'minimum_structural_review_pack.json'}`",
        f"- Decision template path: `{decision_template}`",
        "- Import script status: supports completed minimum decision file.",
        "- Validation status: validator supports minimum approvals.",
        "- Tile 946 status: quarantined; excluded from approval candidates.",
        "- Production maps generated: 0",
        "",
        "## Candidate Counts",
        "",
    ]
    for role in TARGET_ROLES + OPTIONAL_ROLES:
        lines.append(f"- {role}: {counts.get(role, 0)}")
    lines.extend(["", "## Preview Paths", ""])
    for role, paths in previews.items():
        lines.append(f"- {role}: clean `{paths['clean']}`, labeled `{paths['labeled']}`")
    lines.extend([
        "",
        "## Next Recommended Mission",
        "",
        "Review the minimum previews, fill `minimum_structural_decisions.json`, then run the focused importer and validator before attempting a controlled visual prototype.",
    ])
    write_text(REPORT_DIR / "minimum_structural_review_summary.md", "\n".join(lines))


def main() -> int:
    ensure_dirs()
    source = load_json(CANDIDATES_PATH)
    selected: dict[str, list[dict[str, Any]]] = {}
    for role in TARGET_ROLES + OPTIONAL_ROLES:
        selected[role] = select_role_candidates(role, source.get("roles", {}).get(role, []))
    previews = make_previews(selected)
    candidates = []
    for role in TARGET_ROLES + OPTIONAL_ROLES:
        for item in selected[role]:
            preview_path = previews.get(role, {}).get("labeled", "")
            candidates.append(entry_for_pack(item, role, preview_path))
    pack = {
        "reviewPackId": "minimum_structural_review_pack",
        "generatedAt": now_iso(),
        "purpose": "Minimum structural approval review for one controlled visual prototype later.",
        "autoApprovalAllowed": False,
        "productionMapGenerated": False,
        "tile946Policy": "Tile 946 excluded from approval candidates and remains quarantined from wall/body/blocking/collision roles.",
        "targetRoles": TARGET_ROLES,
        "optionalRoles": OPTIONAL_ROLES,
        "candidateCounts": dict(Counter(entry["roleName"] for entry in candidates)),
        "candidates": candidates,
    }
    write_json(MIN_ROOT / "minimum_structural_review_pack.json", pack)
    decision_template = write_decision_template(pack)
    write_instructions(pack, previews, decision_template)
    write_readiness_no_decisions(pack)
    write_summary(pack, previews, decision_template)
    print("Minimum structural review pack created")
    for role in TARGET_ROLES + OPTIONAL_ROLES:
        print(f"{role}: {len(selected[role])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
