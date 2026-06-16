#!/usr/bin/env python3
"""Mine focused path_base review candidates for the first outdoor visual prototype.

This is review preparation only. It creates no approvals and no production maps.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ijson
from PIL import Image, ImageDraw, ImageFont


TOOL_ROOT = Path(__file__).resolve().parent
REVIEW_ROOT = TOOL_ROOT / "structural_learning" / "path_base_review"
PREVIEW_DIR = REVIEW_ROOT / "previews"
DECISION_DIR = REVIEW_ROOT / "decisions"
REPORT_DIR = TOOL_ROOT / "reports"

VANILLA_USAGE = TOOL_ROOT / "pattern_learning" / "vanilla" / "vanilla_layer_tile_usage.json"
VANILLA_NEIGHBORS = TOOL_ROOT / "pattern_learning" / "vanilla" / "vanilla_layer_neighbor_patterns.json"
VANILLA_STACKS = TOOL_ROOT / "pattern_learning" / "vanilla" / "vanilla_layer_stack_patterns.json"
NVE_LAYER_PATTERNS = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "new_vanillaeditedmaps_layer_patterns.json"
NVE_STACKS = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "new_vanillaeditedmaps_layer_stack_patterns.json"
CANONICAL_CANDIDATES = TOOL_ROOT / "classification" / "canonical_tile_candidates.json"
STRUCTURAL_CANDIDATES = TOOL_ROOT / "structural_learning" / "candidates" / "structural_tile_candidates_by_role.json"

OUT_CANDIDATES = REVIEW_ROOT / "path_base_candidates.json"
OUT_PACK = REVIEW_ROOT / "path_base_review_pack.json"
OUT_TEMPLATE = DECISION_DIR / "path_base_decisions.template.json"
OUT_SUMMARY = REPORT_DIR / "path_base_review_pack_summary.md"
OUT_VALIDATION = REPORT_DIR / "path_base_approval_validation_report.md"

TILE_SIZE = 16
REVIEW_LIMIT = 64
TOP_CANONICAL_LIMIT = 260
FIRST_PASS_REVIEW_SHEET_PREFIXES = (
    "spring_outdoorstilesheet",
    "summer_outdoorstilesheet",
    "fall_outdoorstilesheet",
    "winter_outdoorstilesheet",
    "spring_town",
    "summer_town",
    "fall_town",
    "winter_town",
)
OUTDOOR_SHEET_HINTS = {
    "spring_outdoorstilesheet",
    "summer_outdoorstilesheet",
    "fall_outdoorstilesheet",
    "winter_outdoorstilesheet",
    "spring_town",
    "summer_town",
    "fall_town",
    "winter_town",
    "spring_beach",
    "summer_beach",
    "fall_beach",
    "winter_beach",
    "deserttiles",
    "island_tilesheet_1",
}
POSITIVE_TYPE_VALUES = {"dirt", "stone", "wood", "path", "road"}
NEGATIVE_TYPE_VALUES = {"grass", "water"}
BLOCKING_LAYER_NAMES = {"Buildings", "Buildings2", "Buildings3", "AlwaysFront", "AlwaysFront2"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def base_key(value: Any) -> str:
    text = str(value or "").replace("\\", "/").split("/")[-1].lower()
    for suffix in [".png", ".tsx", ".json", ".tbin"]:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def tile_key(sheet: str, local_id: int) -> str:
    return f"{base_key(sheet)}:{int(local_id)}"


def path_candidate_id(sheet: str, local_id: int) -> str:
    safe = re.sub(r"[^a-z0-9_]+", "_", base_key(sheet))
    return f"path_base_{safe}_{int(local_id)}"


def prop_values(props: dict[str, Any], key: str) -> set[str]:
    values = props.get(key) or []
    if not isinstance(values, list):
        values = [values]
    return {str(value).strip().lower() for value in values}


def is_water(props: dict[str, Any]) -> bool:
    return "t" in prop_values(props, "Water") or "true" in prop_values(props, "Water")


def likely_path_metadata(props: dict[str, Any]) -> bool:
    type_values = prop_values(props, "Type")
    if type_values & POSITIVE_TYPE_VALUES:
        return True
    if prop_values(props, "Diggable"):
        return True
    if prop_values(props, "PathType"):
        return True
    return False


def existing_structural_transition_keys() -> set[tuple[str, int]]:
    doc = load_json(STRUCTURAL_CANDIDATES, {}) or {}
    out = set()
    for item in (doc.get("roles") or {}).get("path_transition", []) or []:
        sheet = item.get("sourceTilesheet")
        local = item.get("localTileId")
        if sheet is not None and local is not None:
            try:
                out.add((base_key(sheet), int(local)))
            except Exception:
                pass
    return out


def candidate_template(sheet: str, local_id: int) -> dict[str, Any]:
    return {
        "candidateId": None,
        "pathBaseCandidateId": path_candidate_id(sheet, int(local_id)),
        "mappedCandidateIds": [],
        "roleName": "path_base",
        "sourceTilesheet": base_key(sheet),
        "localTileId": int(local_id),
        "layer": "Back",
        "dominantLayer": "Back",
        "observedCount": 0,
        "observedMaps": Counter(),
        "intrinsicProperties": {},
        "neighborPatternSummary": Counter(),
        "stackPatternSummary": Counter(),
        "evidenceScoreRaw": 0.0,
        "evidenceReasons": Counter(),
        "canonicalMatches": [],
        "copiedImagePath": None,
        "sourceCategory": None,
        "sourceMod": None,
        "proposedClass": "path_base",
        "proposedPurpose": "walkable_base_path",
        "proposedAllowedLayers": ["Back"],
        "proposedCollision": "walkable",
        "riskFlags": set(),
        "needsHumanReview": True,
        "approved": False,
    }


def add_candidate(candidates: dict[tuple[str, int], dict[str, Any]], sheet: str, local_id: int) -> dict[str, Any]:
    key = (base_key(sheet), int(local_id))
    return candidates.setdefault(key, candidate_template(sheet, int(local_id)))


def add_reason(entry: dict[str, Any], reason: str, amount: float) -> None:
    entry["evidenceReasons"][reason] += 1
    entry["evidenceScoreRaw"] += amount


def add_vanilla_usage(candidates: dict[tuple[str, int], dict[str, Any]]) -> None:
    usage = load_json(VANILLA_USAGE, {}) or {}
    neighbors = load_json(VANILLA_NEIGHBORS, {}) or {}
    neighbor_by_tile: dict[str, Counter] = defaultdict(Counter)
    examples_by_tile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pattern in ((neighbors.get("layers") or {}).get("Back") or {}).get("topTileNeighborPatterns", []) or []:
        key = pattern.get("tileKey")
        if not key:
            continue
        neighbor_by_tile[key][f"{pattern.get('neighborMask')}|{pattern.get('edgeCornerRole')}"] += int(pattern.get("count") or 0)
        examples_by_tile[key].extend(pattern.get("examples") or [])

    for tile in ((usage.get("layers") or {}).get("Back") or {}).get("topTiles", []) or []:
        sheet = tile.get("sheet")
        local = tile.get("localTileId")
        if sheet is None or local is None:
            continue
        local = int(local)
        if local == 946:
            continue
        props = tile.get("intrinsicProperties") or {}
        if is_water(props) or "water_base" in (tile.get("approvedClasses") or []):
            continue
        type_values = prop_values(props, "Type")
        if type_values & NEGATIVE_TYPE_VALUES and not (type_values & POSITIVE_TYPE_VALUES):
            continue
        if not likely_path_metadata(props) and base_key(sheet) not in OUTDOOR_SHEET_HINTS:
            continue
        entry = add_candidate(candidates, sheet, local)
        entry["observedCount"] += int(tile.get("count") or 0)
        entry["intrinsicProperties"].update(props)
        entry["neighborPatternSummary"].update(neighbor_by_tile.get(tile.get("tileKey"), {}))
        for example in examples_by_tile.get(tile.get("tileKey"), [])[:12]:
            if example.get("map"):
                entry["observedMaps"][example["map"]] += 1
        add_reason(entry, "vanilla_back_layer_usage", math.log1p(int(tile.get("count") or 0)) * 120)
        if "NESW|diag=NESESWNW|interior_or_repeated_fill" in entry["neighborPatternSummary"]:
            add_reason(entry, "repeated_fill_neighbor_pattern", 900)
        elif any("interior_or_repeated_fill" in key for key in entry["neighborPatternSummary"]):
            add_reason(entry, "repeated_fill_neighbor_pattern", 500)
        if likely_path_metadata(props):
            add_reason(entry, "walkable_path_like_intrinsic_metadata", 600)
        if base_key(sheet) in OUTDOOR_SHEET_HINTS:
            add_reason(entry, "outdoor_tilesheet_context", 250)
        if tile.get("approvalBacked") and "path_base" not in (tile.get("approvedClasses") or []):
            entry["riskFlags"].add("already_approved_as_non_path_role")
        if (base_key(sheet), local) in existing_structural_transition_keys():
            entry["riskFlags"].add("also_present_in_path_transition_review")


def vanilla_back_tile_info() -> dict[tuple[str, int], dict[str, Any]]:
    usage = load_json(VANILLA_USAGE, {}) or {}
    out = {}
    for tile in ((usage.get("layers") or {}).get("Back") or {}).get("topTiles", []) or []:
        sheet = tile.get("sheet")
        local = tile.get("localTileId")
        if sheet is None or local is None:
            continue
        try:
            out[(base_key(sheet), int(local))] = tile
        except Exception:
            pass
    return out


def add_new_vanillaeditedmaps_evidence(candidates: dict[tuple[str, int], dict[str, Any]]) -> None:
    nve = load_json(NVE_LAYER_PATTERNS, {}) or {}
    vanilla_info = vanilla_back_tile_info()
    back = (nve.get("layers") or {}).get("Back") or {}
    for tile in back.get("commonTileIDs", []) or []:
        key = str(tile.get("key") or "")
        if ":" not in key:
            continue
        sheet, local_text = key.rsplit(":", 1)
        try:
            local = int(local_text)
        except Exception:
            continue
        if local == 946:
            continue
        info = vanilla_info.get((base_key(sheet), local), {})
        props = info.get("intrinsicProperties") or {}
        if is_water(props) or "water_base" in (info.get("approvedClasses") or []):
            continue
        type_values = prop_values(props, "Type")
        if type_values & NEGATIVE_TYPE_VALUES and not (type_values & POSITIVE_TYPE_VALUES):
            continue
        if base_key(sheet) not in OUTDOOR_SHEET_HINTS and not likely_path_metadata(props):
            continue
        entry = add_candidate(candidates, sheet, local)
        if props:
            entry["intrinsicProperties"].update(props)
        entry["observedCount"] += int(tile.get("count") or 0)
        add_reason(entry, "new_vanillaeditedmaps_back_layer_usage", math.log1p(int(tile.get("count") or 0)) * 75)
        entry["evidenceReasons"]["new_vanillaeditedmaps_reference"] += 1


def canonical_sheet_name(item: dict[str, Any]) -> str:
    return base_key(item.get("tilesheetName") or item.get("imageName") or item.get("copiedImagePath"))


def canonical_back_count(item: dict[str, Any]) -> int:
    layers = item.get("observedLayers") or {}
    total = 0
    for key, value in layers.items():
        if str(key).lower().startswith("back"):
            try:
                total += int(value)
            except Exception:
                pass
    return total


def canonical_blocking_count(item: dict[str, Any]) -> int:
    layers = item.get("observedLayers") or {}
    total = 0
    for key, value in layers.items():
        if key in BLOCKING_LAYER_NAMES:
            try:
                total += int(value)
            except Exception:
                pass
    return total


def canonical_paths_only(item: dict[str, Any]) -> bool:
    layers = item.get("observedLayers") or {}
    if not layers:
        return False
    path_count = int(layers.get("Paths") or 0)
    back_count = canonical_back_count(item)
    return path_count > 0 and back_count == 0


def add_canonical_evidence(candidates: dict[tuple[str, int], dict[str, Any]]) -> None:
    if not CANONICAL_CANDIDATES.exists():
        return
    transition_keys = existing_structural_transition_keys()
    vanilla_info = vanilla_back_tile_info()
    with CANONICAL_CANDIDATES.open("rb") as handle:
        for item in ijson.items(handle, "item"):
            local = item.get("localTileId")
            cid = item.get("candidateId")
            if local is None or not cid:
                continue
            try:
                local = int(local)
            except Exception:
                continue
            if local == 946:
                continue
            sheet = canonical_sheet_name(item)
            key = (sheet, local)
            info = vanilla_info.get(key, {})
            props = info.get("intrinsicProperties") or {}
            if is_water(props) or "water_base" in (info.get("approvedClasses") or []):
                continue
            type_values = prop_values(props, "Type")
            if type_values & NEGATIVE_TYPE_VALUES and not (type_values & POSITIVE_TYPE_VALUES):
                continue
            name_blob = f"{sheet} {item.get('copiedImagePath') or ''}".lower()
            back_count = canonical_back_count(item)
            blocking_count = canonical_blocking_count(item)
            should_create_moonvillage = (
                item.get("sourceCategory") == "moonvillage"
                and back_count >= 20
                and back_count >= blocking_count * 3
                and (
                    sheet in OUTDOOR_SHEET_HINTS
                    or any(token in name_blob for token in ["outdoor", "beach", "desert", "island"])
                )
                and "towninterior" not in name_blob
                and "mine_" not in name_blob
                and "mine" != sheet
            )
            if key not in candidates and not should_create_moonvillage:
                continue
            entry = add_candidate(candidates, sheet, local)
            match = {
                "candidateId": cid,
                "sourceCategory": item.get("sourceCategory"),
                "sourceMod": item.get("sourceMod"),
                "tilesheetName": item.get("tilesheetName") or item.get("imageName"),
                "copiedImagePath": item.get("copiedImagePath"),
                "observedLayers": item.get("observedLayers") or {},
                "observedCountTotal": item.get("observedCountTotal"),
            }
            entry["canonicalMatches"].append(match)
            if not entry["candidateId"]:
                entry["candidateId"] = cid
                entry["copiedImagePath"] = item.get("copiedImagePath")
                entry["sourceCategory"] = item.get("sourceCategory")
                entry["sourceMod"] = item.get("sourceMod")
            if back_count:
                add_reason(entry, "moonvillage_or_copied_back_layer_evidence", math.log1p(back_count) * 90)
            if canonical_paths_only(item):
                entry["riskFlags"].add("technical_paths_layer_only")
            if blocking_count:
                entry["riskFlags"].add("mixed_blocking_or_overlay_layer_usage")
            if key in transition_keys:
                entry["riskFlags"].add("also_present_in_path_transition_review")

    for entry in candidates.values():
        # Stable, exact candidate IDs only. Do not broaden to all duplicates here.
        if entry["candidateId"]:
            entry["mappedCandidateIds"] = [entry["candidateId"]]


def flatten_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    risk_flags = sorted(entry["riskFlags"])
    props = entry.get("intrinsicProperties") or {}
    if is_water(props):
        risk_flags.append("intrinsic_water_not_path_base")
    type_values = prop_values(props, "Type")
    if type_values & NEGATIVE_TYPE_VALUES and not (type_values & POSITIVE_TYPE_VALUES):
        risk_flags.append("intrinsic_grass_or_water_not_path_base")
    entry_score = float(entry["evidenceScoreRaw"])
    if "technical_paths_layer_only" in risk_flags:
        entry_score *= 0.35
    if "mixed_blocking_or_overlay_layer_usage" in risk_flags:
        entry_score *= 0.5
    if "already_approved_as_non_path_role" in risk_flags:
        entry_score *= 0.45
    if not entry.get("candidateId"):
        entry_score *= 0.1
        risk_flags.append("missing_canonical_candidate_id")
    if not entry.get("copiedImagePath"):
        risk_flags.append("missing_preview_source_image")
    return {
        "candidateId": entry.get("candidateId"),
        "pathBaseCandidateId": entry["pathBaseCandidateId"],
        "mappedCandidateIds": entry.get("mappedCandidateIds") or [],
        "roleName": "path_base",
        "sourceTilesheet": entry["sourceTilesheet"],
        "localTileId": entry["localTileId"],
        "layer": "Back",
        "observedCount": int(entry.get("observedCount") or 0),
        "observedMaps": [{"mapName": key, "count": int(value)} for key, value in entry["observedMaps"].most_common(12)],
        "dominantLayer": entry.get("dominantLayer") or "Back",
        "intrinsicProperties": entry.get("intrinsicProperties") or {},
        "neighborPatternSummary": [{"key": key, "count": int(value)} for key, value in entry["neighborPatternSummary"].most_common(12)],
        "stackPatternSummary": [{"key": key, "count": int(value)} for key, value in entry["stackPatternSummary"].most_common(12)],
        "evidenceScore": round(entry_score, 3),
        "evidenceReasons": [{"key": key, "count": int(value)} for key, value in entry["evidenceReasons"].most_common(12)],
        "canonicalMatches": entry.get("canonicalMatches") or [],
        "copiedImagePath": entry.get("copiedImagePath"),
        "sourceCategory": entry.get("sourceCategory"),
        "sourceMod": entry.get("sourceMod"),
        "proposedClass": "path_base",
        "proposedPurpose": "walkable_base_path",
        "proposedAllowedLayers": ["Back"],
        "proposedCollision": "walkable",
        "riskFlags": sorted(set(risk_flags)),
        "needsHumanReview": True,
        "approved": False,
    }


def mine_candidates() -> list[dict[str, Any]]:
    candidates: dict[tuple[str, int], dict[str, Any]] = {}
    add_vanilla_usage(candidates)
    add_new_vanillaeditedmaps_evidence(candidates)
    add_canonical_evidence(candidates)
    flattened = [flatten_candidate(entry) for entry in candidates.values()]
    flattened = [
        item
        for item in flattened
        if item["candidateId"]
        and item["localTileId"] != 946
        and "intrinsic_water_not_path_base" not in item["riskFlags"]
        and "intrinsic_grass_or_water_not_path_base" not in item["riskFlags"]
    ]
    flattened.sort(key=lambda item: (item["evidenceScore"], item["observedCount"]), reverse=True)
    return flattened


def select_review_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    seen_ids = set()
    def first_pass_sheet(item: dict[str, Any]) -> bool:
        sheet = str(item.get("sourceTilesheet") or "").lower()
        return sheet.startswith(FIRST_PASS_REVIEW_SHEET_PREFIXES) and "island" not in sheet and "beach" not in sheet and "mine" not in sheet

    strict_blockers = {
        "missing_canonical_candidate_id",
        "missing_preview_source_image",
        "technical_paths_layer_only",
        "mixed_blocking_or_overlay_layer_usage",
        "intrinsic_water_not_path_base",
        "intrinsic_grass_or_water_not_path_base",
        "already_approved_as_non_path_role",
    }
    for item in candidates:
        risks = set(item.get("riskFlags") or [])
        if strict_blockers & risks:
            continue
        if "also_present_in_path_transition_review" in risks:
            continue
        if not first_pass_sheet(item):
            continue
        if item["candidateId"] in seen_ids:
            continue
        seen_ids.add(item["candidateId"])
        selected.append({**item, "humanDecision": None})
        if len(selected) >= REVIEW_LIMIT:
            break
    if len(selected) < 40:
        for item in candidates:
            risks = set(item.get("riskFlags") or [])
            if strict_blockers & risks:
                continue
            if not first_pass_sheet(item):
                continue
            if item["candidateId"] in seen_ids:
                continue
            seen_ids.add(item["candidateId"])
            selected.append({**item, "humanDecision": None})
            if len(selected) >= REVIEW_LIMIT:
                break
    return selected


def crop_tile(image: Image.Image, local_id: int) -> Image.Image:
    columns = max(1, image.width // TILE_SIZE)
    x = (int(local_id) % columns) * TILE_SIZE
    y = (int(local_id) // columns) * TILE_SIZE
    return image.crop((x, y, min(x + TILE_SIZE, image.width), min(y + TILE_SIZE, image.height)))


def crop_context(image: Image.Image, local_id: int, radius: int = 1) -> Image.Image:
    columns = max(1, image.width // TILE_SIZE)
    tx = int(local_id) % columns
    ty = int(local_id) // columns
    x0 = max(0, (tx - radius) * TILE_SIZE)
    y0 = max(0, (ty - radius) * TILE_SIZE)
    x1 = min(image.width, (tx + radius + 1) * TILE_SIZE)
    y1 = min(image.height, (ty + radius + 1) * TILE_SIZE)
    return image.crop((x0, y0, x1, y1))


def make_previews(review_candidates: list[dict[str, Any]]) -> dict[str, str | None]:
    if not review_candidates:
        return {"clean": None, "labeled": None}
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    cell_w, cell_h = 174, 150
    columns = 4
    rows = math.ceil(len(review_candidates) / columns)
    clean = Image.new("RGBA", (columns * cell_w, rows * cell_h), (245, 246, 242, 255))
    labeled = Image.new("RGBA", clean.size, (245, 246, 242, 255))
    clean_draw = ImageDraw.Draw(clean)
    label_draw = ImageDraw.Draw(labeled)

    image_cache: dict[str, Image.Image] = {}
    for index, item in enumerate(review_candidates):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        path = item.get("copiedImagePath")
        source_image = None
        if path and Path(path).exists():
            if path not in image_cache:
                image_cache[path] = Image.open(path).convert("RGBA")
            source_image = image_cache[path]
        if source_image:
            tile = crop_tile(source_image, int(item["localTileId"]))
            context = crop_context(source_image, int(item["localTileId"]))
            tile_big = tile.resize((64, 64), Image.Resampling.NEAREST)
            context_big = context.resize((96, 96), Image.Resampling.NEAREST)
            clean.alpha_composite(context_big, (x + 8, y + 8))
            clean.alpha_composite(tile_big, (x + 108, y + 8))
            labeled.alpha_composite(context_big, (x + 8, y + 8))
            labeled.alpha_composite(tile_big, (x + 108, y + 8))
        else:
            clean_draw.rectangle((x + 8, y + 8, x + 164, y + 72), fill=(220, 220, 220, 255))
            label_draw.rectangle((x + 8, y + 8, x + 164, y + 72), fill=(220, 220, 220, 255))
        label_draw.rectangle((x + 108, y + 8, x + 172, y + 72), outline=(42, 130, 100, 255), width=2)
        label_lines = [
            str(item["candidateId"])[:24],
            f"{item['sourceTilesheet']} #{item['localTileId']}",
            f"score {item['evidenceScore']}",
        ]
        if item.get("riskFlags"):
            label_lines.append("risk: " + ",".join(item["riskFlags"][:2]))
        label_draw.text((x + 8, y + 108), "\n".join(label_lines), fill=(20, 28, 24, 255), font=font)
    clean_path = PREVIEW_DIR / "path_base_clean.png"
    labeled_path = PREVIEW_DIR / "path_base_labeled.png"
    clean.save(clean_path)
    labeled.save(labeled_path)
    return {"clean": str(clean_path), "labeled": str(labeled_path)}


def write_decision_template(review_candidates: list[dict[str, Any]]) -> None:
    decisions = [
        {
            "candidateId": item["candidateId"],
            "roleName": "path_base",
            "decision": "unsure",
            "approvedClass": "path_base",
            "approvedPurpose": "walkable_base_path",
            "allowedLayers": ["Back"],
            "collision": "walkable",
            "notes": "",
        }
        for item in review_candidates
    ]
    write_json(
        OUT_TEMPLATE,
        {
            "reviewType": "path_base_first_visual_unlock",
            "profile": "outdoor",
            "stylepack": "moonvillage_forest_ruins",
            "reviewer": "Joel",
            "instructions": "Approve only clear walkable base path tiles. Use unsure if the tile looks like an edge, transition, decoration, or wall.",
            "decisions": decisions,
        },
    )


def write_reports(candidates: list[dict[str, Any]], review_candidates: list[dict[str, Any]], previews: dict[str, str | None]) -> None:
    source_counter = Counter(item.get("sourceTilesheet") for item in review_candidates)
    risk_counter = Counter(flag for item in candidates for flag in item.get("riskFlags", []))
    write_text(
        OUT_SUMMARY,
        "\n".join(
            [
                "# Path Base Review Pack Summary",
                "",
                f"- Generated: {now_iso()}",
                f"- Candidates mined: {len(candidates)}",
                f"- Candidates selected for review: {len(review_candidates)}",
                "- Auto approvals created: 0",
                "- Production maps generated: 0",
                "- Tile 946 included as path_base: NO",
                f"- Review pack: `{OUT_PACK}`",
                f"- Candidate file: `{OUT_CANDIDATES}`",
                f"- Clean preview: `{previews.get('clean')}`",
                f"- Labeled preview: `{previews.get('labeled')}`",
                f"- Decision template: `{OUT_TEMPLATE}`",
                "- Importer support: `import_structural_manual_decisions.py` imports `path_base_decisions.json` to `path_base_manual_approved.approved_tags.json`.",
                "- Validator status: path_base approval validation report is generated by `validate_structural_approved_tags.py`.",
                "- Reviewer UI support: `path_base` is available as a structural role/preset, exports to `structural_learning/path_base_review/decisions/path_base_decisions.json`, and enforces Back/walkable decisions before save.",
                "- First visual prototype impact: path_base remains a blocker until completed manual decisions are imported and validated.",
                "",
                "## Strongest Evidence Sources",
                "",
                *[f"- `{sheet}`: {count} selected candidates" for sheet, count in source_counter.most_common(20)],
                "",
                "## Risk Flags Seen In Mined Candidates",
                "",
                *([f"- `{flag}`: {count}" for flag, count in risk_counter.most_common(20)] or ["- None."]),
                "",
                "## Next Recommended Step",
                "",
                "Open the clean/labeled path_base previews, fill `path_base_decisions.json` from the template, then run the importer and validators before attempting visual output.",
            ]
        ),
    )
    write_text(
        OUT_VALIDATION,
        "\n".join(
            [
                "# Path Base Approval Validation Report",
                "",
                f"- Generated: {now_iso()}",
                "- Result: SKIPPED",
                f"- Reason: `{DECISION_DIR / 'path_base_decisions.json'}` does not exist yet.",
                "- No path_base approvals were imported or validated.",
            ]
        ),
    )


def main() -> int:
    for path in [REVIEW_ROOT, PREVIEW_DIR, DECISION_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    candidates = mine_candidates()
    review_candidates = select_review_candidates(candidates)
    previews = make_previews(review_candidates)
    write_json(
        OUT_CANDIDATES,
        {
            "generatedAt": now_iso(),
            "source": "vanilla_moonvillage_new_vanillaeditedmaps_path_base_evidence",
            "autoApprovalAllowed": False,
            "productionMapGenerated": False,
            "tile946Policy": "Tile 946 is excluded from path_base candidates. It remains canopy-only AlwaysFront overlay.",
            "candidateCount": len(candidates),
            "candidates": candidates,
        },
    )
    write_json(
        OUT_PACK,
        {
            "reviewPackId": "path_base_review_pack",
            "generatedAt": now_iso(),
            "profile": "outdoor",
            "stylepack": "moonvillage_forest_ruins",
            "roleName": "path_base",
            "candidateCount": len(review_candidates),
            "cleanPreviewPath": str(previews.get("clean")),
            "labeledPreviewPath": str(previews.get("labeled")),
            "autoApprovalAllowed": False,
            "productionMapGenerated": False,
            "candidates": review_candidates,
        },
    )
    write_decision_template(review_candidates)
    write_reports(candidates, review_candidates, previews)
    print(f"path_base candidates mined: {len(candidates)}")
    print(f"path_base review candidates: {len(review_candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
