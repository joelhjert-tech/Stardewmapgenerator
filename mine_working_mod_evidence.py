#!/usr/bin/env python3
"""Mine working mod references for tile/map evidence.

This script is intentionally conservative. It indexes useful evidence and
creates proposal/quarantine outputs, but it does not auto-approve anything
unless the evidence meets the high-confidence rules documented in this mission.
"""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TOOL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TOOL_ROOT.parents[1]
WORK_ROOT = TOOL_ROOT / "working_mod_mining"
RAW_DIR = WORK_ROOT / "raw_indexes"
EVIDENCE_DIR = WORK_ROOT / "evidence"
AUTO_DIR = WORK_ROOT / "auto_approval"
PROPOSED_DIR = WORK_ROOT / "proposed"
QUARANTINE_DIR = WORK_ROOT / "quarantine"
REF_DIR = WORK_ROOT / "reference_repos"
REPORT_DIR = TOOL_ROOT / "reports"
APPROVED_TAG_DIR = TOOL_ROOT / "classification" / "approved_tags"
MANUAL_SAFE_PATTERN_DIR = TOOL_ROOT / "pattern_learning" / "manual_safe_patterns"
CANONICAL_PATH = TOOL_ROOT / "classification" / "canonical_tile_candidates.json"
TILE_CLASS_SCHEMA = TOOL_ROOT / "classification" / "tile_class_schema.json"
COLLISION_SCHEMA = TOOL_ROOT / "stylepacks" / "collision_schema.json"
MISSION_ASSETS = TOOL_ROOT / "mission_assets"

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
STANDARD_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
TEXT_EXTENSIONS = {".cs", ".json", ".tmx", ".tmj", ".tsx", ".md", ".txt", ".config", ".xml"}
MAP_EXTENSIONS = {".tmx", ".tmj", ".tsx"}
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".ase", ".aseprite", ".xcf", ".zip", ".rar", ".dll"}
MAX_TEXT_FILE_BYTES = 2_000_000
MAX_INDEX_ENTRIES_PER_FILE = 120
MAX_MAP_EVIDENCE_PER_SOURCE = 300

SAFE_946_SHEETS = {"spring_outdoorstilesheet.png", "fall_outdoorstilesheet.png", "winter_outdoorstilesheet.png"}
UNSAFE_946_CLASSES = {"wall_body", "wall_corner", "wall_edge", "wall_side", "exterior_wall", "collision_blocker", "hedge_body"}
UNSAFE_946_COLLISIONS = {"blocked", "water_blocked", "custom_requires_review"}


def ensure_dirs() -> None:
    for path in [WORK_ROOT, RAW_DIR, EVIDENCE_DIR, AUTO_DIR, PROPOSED_DIR, QUARANTINE_DIR, REPORT_DIR, MANUAL_SAFE_PATTERN_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        return str(path)


def norm_sheet(value: Any) -> str:
    if not value:
        return ""
    value = str(value).replace("\\", "/").split("/")[-1].strip().lower()
    return value


def iter_json_array_objects(path: Path) -> Iterable[dict[str, Any]]:
    """Stream objects from a top-level JSON array without loading the whole file."""
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


def load_json_if_exists(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def discover_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    deepwoods = PROJECT_ROOT / "tools" / "DeepWoodsMod-main"
    if deepwoods.exists():
        sources.append({"modName": "DeepWoods", "path": deepwoods, "sourceType": "local", "riskLevel": "medium"})

    hedge_dirs = [p for p in PROJECT_ROOT.glob("*") if p.is_dir() and "hedgemaze" in p.name.lower()]
    for path in hedge_dirs:
        sources.append({"modName": path.name, "path": path, "sourceType": "local", "riskLevel": "medium"})

    aed_root = REF_DIR / "StardewValleyMods"
    for name in [
        "BiggerMineFloors",
        "AdditionalMineMaps",
        "UndergroundSecrets",
        "MapEdit",
        "DynamicMapTilesExtended",
        "IndoorOutdoor",
        "FarmCaveDoors",
        "PlaceShaft",
        "StardewOpenWorld",
        "OpenWorldValley",
    ]:
        path = aed_root / name
        if path.exists():
            sources.append({"modName": name, "path": path, "sourceType": "cloned", "riskLevel": "medium"})

    pathos_root = REF_DIR / "StardewMods"
    for name in ["ContentPatcher", "DataLayers"]:
        path = pathos_root / name
        if path.exists():
            sources.append({"modName": f"Pathoschild.{name}", "path": path, "sourceType": "cloned", "riskLevel": "low"})

    if MISSION_ASSETS.exists():
        sources.append({"modName": "mission_assets_reference_maps", "path": MISSION_ASSETS, "sourceType": "mission_assets", "riskLevel": "medium"})

    return sources


def file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".cs"}:
        return "code"
    if ext in {".tmx", ".tmj", ".tbin"}:
        return "map"
    if ext == ".tsx":
        return "tileset"
    if ext == ".json":
        return "config_or_content_pack"
    if ext in ASSET_EXTENSIONS:
        return "asset"
    return "other"


def inventory_source(source: dict[str, Any]) -> dict[str, Any]:
    root = Path(source["path"])
    files = [p for p in root.rglob("*") if p.is_file()]
    by_kind = Counter(file_kind(p) for p in files)
    by_ext = Counter(p.suffix.lower() or "<none>" for p in files)
    asset_files = [rel(p) for p in files if p.suffix.lower() in ASSET_EXTENSIONS]
    restricted_assets = any(p.suffix.lower() in ASSET_EXTENSIONS for p in files) and source["modName"] not in {"Pathoschild.ContentPatcher", "Pathoschild.DataLayers"}
    return {
        "modName": source["modName"],
        "path": rel(root),
        "sourceType": source["sourceType"],
        "fileCount": len(files),
        "codeFiles": by_kind["code"],
        "mapFiles": by_kind["map"],
        "tilesetFiles": by_kind["tileset"],
        "contentPacks": sum(1 for p in files if p.name.lower() == "content.json" or p.suffix.lower() == ".json"),
        "configFiles": by_ext[".json"] + by_ext[".config"],
        "assetFiles": sum(by_ext[ext] for ext in ASSET_EXTENSIONS),
        "sampleAssetFiles": asset_files[:12],
        "assetsRestrictedOrCustom": restricted_assets,
        "mapTileDataCanBeUsedAsEvidence": by_kind["map"] > 0 and not restricted_assets,
        "codeCanBeUsedAsEvidence": by_kind["code"] > 0,
        "riskLevel": "high" if restricted_assets else source.get("riskLevel", "medium"),
        "notes": "Assets remain reference-only. Code/map evidence is never sufficient by itself for auto-approval unless exact sheet, layer, collision, and metadata checks pass.",
    }


def extract_line_entries(source: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(source["path"])
    out: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        per_file = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            if per_file >= MAX_INDEX_ENTRIES_PER_FILE:
                break
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            entries = []
            if any(token in stripped for token in STANDARD_LAYERS):
                for layer in STANDARD_LAYERS:
                    if re.search(rf"\b{layer}\b", stripped):
                        entries.append(("layer_name", layer))
            if re.search(r"\b(Warp|NPCWarp|TouchAction|Action|Passable|Water|MapProperties|MapTiles|PatchMode|FromArea|ToArea|SetIndex|SetTilesheet)\b", stripped):
                for key in ["Warp", "NPCWarp", "TouchAction", "Action", "Passable", "Water", "MapProperties", "MapTiles", "PatchMode", "FromArea", "ToArea", "SetIndex", "SetTilesheet"]:
                    if key.lower() in lower:
                        entries.append(("map_property_or_patch_field", key))
            if re.search(r"\b(TileIndex|tileIndex|setMapTileIndex|SetIndex|case|localTileId|Index|Indexes)\b", stripped):
                for num in re.findall(r"(?<![A-Za-z])\b\d{1,4}\b", stripped):
                    entries.append(("tile_id_or_index", int(num)))
            if re.search(r"(outdoorsTileSheet|spring_outdoorsTileSheet|fall_outdoorsTileSheet|winter_outdoorsTileSheet|townInterior|mine|TileSheets|tilesheet|TileSheet)", stripped, re.IGNORECASE):
                for sheet in re.findall(r"[A-Za-z0-9_./\\-]*(?:TileSheet|tilesheet|townInterior|mine)[A-Za-z0-9_./\\-]*", stripped):
                    entries.append(("tilesheet_name_or_path", sheet.strip("\"',;()")))
            for warp in re.findall(r"(-?\d+\s+-?\d+\s+[A-Za-z0-9_./\\:-]+\s+-?\d+\s+-?\d+)", stripped):
                entries.append(("warp_string", warp))
            for mp in re.findall(r"(?:Maps[/\\][A-Za-z0-9_./\\-]+|MineShaft|FarmCave|Town|Forest|Mountain|Beach)", stripped):
                entries.append(("map_or_location_name", mp))
            for label in ["wall", "corner", "floor", "ladder", "shaft", "entrance", "water", "shadow", "trap", "secret", "chest", "vine", "slant", "puzzle", "clearSpots", "clearCenters", "superClearCenters"]:
                if label.lower() in lower:
                    entries.append(("structure_label", label))
            if not entries:
                continue
            for id_type, value in entries[:8]:
                out.append({
                    "sourceMod": source["modName"],
                    "sourceFile": rel(path),
                    "lineNumber": line_no,
                    "idType": id_type,
                    "rawValue": value,
                    "parsedValue": value,
                    "nearbyCodeContext": stripped[:280],
                    "evidenceKind": "code_or_config_scan" if path.suffix.lower() != ".tmx" else "map_text_scan",
                    "riskFlags": risk_flags_for_line(source, path, stripped, id_type, value),
                })
                per_file += 1
                if per_file >= MAX_INDEX_ENTRIES_PER_FILE:
                    break
    return out


def risk_flags_for_line(source: dict[str, Any], path: Path, line: str, id_type: str, value: Any) -> list[str]:
    flags: list[str] = []
    if source["modName"] == "DeepWoods" and "assets" in path.parts:
        flags.append("restricted_or_custom_asset_context")
    if source["modName"] in {"BiggerMineFloors", "StardewOpenWorld", "OpenWorldValley"} and id_type == "tile_id_or_index":
        flags.append("hardcoded_tile_id_requires_sheet_binding")
    if value == 946 or str(value) == "946":
        flags.append("tile946_requires_canopy_only_policy")
    if "Harmony" in line or "Prefix" in line or "Postfix" in line:
        flags.append("runtime_patch_behavior")
    if id_type == "tilesheet_name_or_path" and any(ext in str(value).lower() for ext in [".png", ".xcf"]):
        flags.append("asset_path_reference_not_asset_approval")
    return flags


def build_candidate_lookup() -> dict[tuple[str, int], list[str]]:
    lookup: dict[tuple[str, int], list[str]] = defaultdict(list)
    if not CANONICAL_PATH.exists():
        return lookup
    for obj in iter_json_array_objects(CANONICAL_PATH):
        cid = obj.get("candidateId")
        local = obj.get("localTileId")
        if cid is None or local is None:
            continue
        try:
            local_id = int(local)
        except Exception:
            continue
        sheets = {
            norm_sheet(obj.get("tilesheetName")),
            norm_sheet(obj.get("imageName")),
            norm_sheet(obj.get("copiedImagePath")),
        }
        for sheet in sheets:
            if sheet:
                lookup[(sheet, local_id)].append(str(cid))
    return lookup


def load_approved_candidate_ids() -> set[str]:
    ids: set[str] = set()
    for path in APPROVED_TAG_DIR.glob("*.approved_tags.json"):
        data = load_json_if_exists(path, {})
        for tag in data.get("tags", []):
            for cid in tag.get("candidateIds", []):
                ids.add(str(cid))
    return ids


def infer_role(layer: str, sheet: str, local_id: int, props: dict[str, Any] | None = None) -> tuple[str, str, str, int, list[str]]:
    props = props or {}
    flags: list[str] = []
    sheet_key = norm_sheet(sheet)
    if local_id == 946:
        if layer == "AlwaysFront" and sheet_key in SAFE_946_SHEETS:
            return "canopy_overlay", "tree_canopy_center", "overlay_only", 100, ["tile946_approved_canopy_context"]
        flags.append("tile946_unapproved_or_unsafe_context")
        return "unknown", "tile946_requires_review", "unknown", 0, flags
    if props.get("Water") in {"T", "true", True}:
        return "water_base", "water", "water_blocked", 100, ["explicit_water_property"]
    if layer == "Back":
        return "floor_base" if "mine" in sheet_key else "ground_base", "walkable_base", "walkable", 85, []
    if layer == "Buildings":
        return "wall_body", "blocking_structure", "blocked", 85, ["buildings_layer_collision_requires_confirmation"]
    if layer == "Front":
        return "wall_top", "front_overlay_or_wall_top", "decorative_front", 80, ["front_layer_role_requires_review"]
    if layer == "AlwaysFront":
        return "canopy_overlay", "alwaysfront_overlay", "overlay_only", 85, ["alwaysfront_overlay_requires_review"]
    if layer == "Paths":
        return "warp_marker", "technical_path_marker", "marker_only", 70, ["paths_layer_is_technical_not_visual"]
    return "unknown", "unknown", "unknown", 0, ["unknown_layer"]


def parse_tmx_map(source: dict[str, Any], path: Path, candidate_lookup: dict[tuple[str, int], list[str]]) -> list[dict[str, Any]]:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []

    tilesets = []
    for ts in root.findall("tileset"):
        firstgid = int(ts.get("firstgid", "1"))
        name = ts.get("name") or ""
        image = ""
        img = ts.find("image")
        if img is not None:
            image = img.get("source") or ""
        tilesets.append({"firstgid": firstgid, "name": name, "image": image})
    tilesets.sort(key=lambda x: x["firstgid"])

    def gid_to_sheet_local(gid: int) -> tuple[str, int] | None:
        gid &= 0x1FFFFFFF
        if gid <= 0:
            return None
        chosen = None
        for ts in tilesets:
            if gid >= ts["firstgid"]:
                chosen = ts
            else:
                break
        if not chosen:
            return None
        sheet = chosen["image"] or chosen["name"]
        return sheet, gid - chosen["firstgid"]

    counts: Counter[tuple[str, str, int]] = Counter()
    examples: dict[tuple[str, str, int], list[dict[str, int]]] = defaultdict(list)
    for layer in root.findall("layer"):
        layer_name = layer.get("name") or "unknown"
        data = layer.find("data")
        if data is None:
            continue
        gids: list[int] = []
        if data.get("encoding") == "csv":
            text = (data.text or "").strip()
            for row in csv.reader(text.splitlines()):
                gids.extend(int(v.strip() or "0") for v in row)
        else:
            for tile in data.findall("tile"):
                gids.append(int(tile.get("gid", "0")))
        width = int(layer.get("width") or root.get("width") or 0)
        for idx, gid in enumerate(gids):
            resolved = gid_to_sheet_local(gid)
            if not resolved:
                continue
            sheet, local = resolved
            key = (layer_name, norm_sheet(sheet), local)
            counts[key] += 1
            if len(examples[key]) < 5 and width:
                examples[key].append({"x": idx % width, "y": idx // width})

    return map_counts_to_evidence(source, path, counts, examples, candidate_lookup)


def parse_tmj_map(source: dict[str, Any], path: Path, candidate_lookup: dict[tuple[str, int], list[str]]) -> list[dict[str, Any]]:
    data = load_json_if_exists(path, {})
    if not isinstance(data, dict):
        return []
    tilesets = []
    for ts in data.get("tilesets", []):
        if isinstance(ts, dict):
            tilesets.append({"firstgid": int(ts.get("firstgid", 1)), "name": ts.get("name") or "", "image": ts.get("image") or ts.get("source") or ""})
    tilesets.sort(key=lambda x: x["firstgid"])

    def gid_to_sheet_local(gid: int) -> tuple[str, int] | None:
        gid &= 0x1FFFFFFF
        if gid <= 0:
            return None
        chosen = None
        for ts in tilesets:
            if gid >= ts["firstgid"]:
                chosen = ts
            else:
                break
        if not chosen:
            return None
        return chosen["image"] or chosen["name"], gid - chosen["firstgid"]

    counts: Counter[tuple[str, str, int]] = Counter()
    examples: dict[tuple[str, str, int], list[dict[str, int]]] = defaultdict(list)
    for layer in data.get("layers", []):
        if not isinstance(layer, dict) or layer.get("type") != "tilelayer":
            continue
        layer_name = layer.get("name") or "unknown"
        width = int(layer.get("width") or data.get("width") or 0)
        for idx, gid in enumerate(layer.get("data") or []):
            if not isinstance(gid, int):
                continue
            resolved = gid_to_sheet_local(gid)
            if not resolved:
                continue
            sheet, local = resolved
            key = (layer_name, norm_sheet(sheet), local)
            counts[key] += 1
            if len(examples[key]) < 5 and width:
                examples[key].append({"x": idx % width, "y": idx // width})
    return map_counts_to_evidence(source, path, counts, examples, candidate_lookup)


def map_counts_to_evidence(
    source: dict[str, Any],
    path: Path,
    counts: Counter[tuple[str, str, int]],
    examples: dict[tuple[str, str, int], list[dict[str, int]]],
    candidate_lookup: dict[tuple[str, int], list[str]],
) -> list[dict[str, Any]]:
    evidence = []
    for (layer, sheet, local_id), count in counts.most_common(MAX_MAP_EVIDENCE_PER_SOURCE):
        proposed_class, purpose, collision, base_score, flags = infer_role(layer, sheet, local_id)
        candidate_ids = candidate_lookup.get((sheet, local_id), [])
        conflicts = []
        score = base_score
        if not candidate_ids:
            flags.append("candidate_not_found_in_canonical_db")
            score = min(score, 85)
        if source.get("riskLevel") == "high":
            flags.append("restricted_or_custom_asset_context")
            score = min(score, 70)
        if layer not in STANDARD_LAYERS:
            flags.append("nonstandard_layer")
            score = min(score, 70)
        safe = score >= 95 and not flags and not conflicts
        evidence.append({
            "sourceMod": source["modName"],
            "sourceFile": rel(path),
            "sourceLine": None,
            "tilesheet": sheet,
            "localTileId": local_id,
            "candidateIds": candidate_ids,
            "layer": layer,
            "proposedClass": proposed_class,
            "proposedPurpose": purpose,
            "collision": collision,
            "evidenceType": "explicit_map_layer_placement",
            "observedCount": count,
            "exampleCoordinates": examples[(layer, sheet, local_id)],
            "evidenceStrength": "authoritative" if score >= 95 else "strong" if score >= 85 else "medium" if score >= 70 else "weak",
            "confidenceScore": score,
            "explanation": f"Map layer placement: {count} uses on {layer} for {sheet} local tile {local_id}.",
            "conflicts": conflicts,
            "riskFlags": flags,
            "safeForAutoApproval": safe,
        })
    return evidence


def mine_map_evidence(sources: list[dict[str, Any]], candidate_lookup: dict[tuple[str, int], list[str]]) -> list[dict[str, Any]]:
    out = []
    for source in sources:
        root = Path(source["path"])
        parsed_for_source = 0
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".tmx", ".tmj"}:
                continue
            if source["sourceType"] == "mission_assets" and parsed_for_source >= 80:
                continue
            if path.suffix.lower() == ".tmx":
                out.extend(parse_tmx_map(source, path, candidate_lookup))
            elif path.suffix.lower() == ".tmj":
                out.extend(parse_tmj_map(source, path, candidate_lookup))
            parsed_for_source += 1
    return out


def special_biggerminefloors(path: Path) -> dict[str, Any]:
    mod_entry = path / "ModEntry.cs"
    lines = mod_entry.read_text(encoding="utf-8-sig", errors="ignore").splitlines() if mod_entry.exists() else []
    cases = []
    current_comments: list[str] = []
    pending_cases: list[int] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            current_comments.append(stripped.lstrip("/").strip())
            current_comments = current_comments[-3:]
        m = re.match(r"case\s+(\d+)\s*:", stripped)
        if m:
            pending_cases.append(int(m.group(1)))
            continue
        if "TileIndex" in stripped and "=" in stripped and pending_cases:
            offsets = sorted(set(re.findall(r"[-+]\s*\d+", stripped)))
            for case_id in pending_cases:
                cases.append({
                    "sourceFile": rel(mod_entry),
                    "lineNumber": i,
                    "baseTileIndex": case_id,
                    "roleLabelFromComments": "; ".join(current_comments[-2:]) or None,
                    "assignmentExpression": stripped,
                    "generatedTileOffsets": offsets,
                    "matrixShape": "scale-matrix branch",
                    "offsetAssumes16Columns": "16" in stripped,
                    "sheetBindingKnown": False,
                    "canBecomeSafePatternProposal": True,
                    "autoApprovalAllowed": False,
                    "riskFlags": ["hardcoded_tile_id_requires_sheet_binding", "sheet_width_unknown_for_offset_math"],
                })
            pending_cases = []
    return {
        "sourceMod": "BiggerMineFloors",
        "sourceFile": rel(mod_entry),
        "totalExpansionCases": len(cases),
        "cases": cases,
        "summary": "Expansion matrix logic is useful, but direct IDs are not auto-approved because sheet binding and sheet width must be proven first.",
    }


def grep_records(root: Path, pattern: str, source_mod: str, category: str) -> list[dict[str, Any]]:
    rx = re.compile(pattern, re.IGNORECASE)
    records = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                records.append({
                    "sourceMod": source_mod,
                    "sourceFile": rel(path),
                    "lineNumber": i,
                    "category": category,
                    "context": line.strip()[:280],
                })
    return records


def special_outputs() -> dict[str, Any]:
    aed = REF_DIR / "StardewValleyMods"
    pathos = REF_DIR / "StardewMods"
    outputs: dict[str, Any] = {}

    outputs["biggerminefloors"] = special_biggerminefloors(aed / "BiggerMineFloors")
    write_json(EVIDENCE_DIR / "biggerminefloors_expansion_matrix_index.json", outputs["biggerminefloors"])

    add_records = grep_records(aed / "AdditionalMineMaps", r"mapPath|mapType|minLevel|maxLevel|forceLevel|Treasure|Monster|Quarry|Dino|Slime|MineShaft", "AdditionalMineMaps", "floor_registry")
    outputs["additionalMineMaps"] = {"sourceMod": "AdditionalMineMaps", "records": add_records}
    write_json(EVIDENCE_DIR / "additional_mine_maps_floor_registry_evidence.json", outputs["additionalMineMaps"])

    underground = grep_records(aed / "UndergroundSecrets", r"clearSpots|clearCenters|superClearCenters|ladder|Buildings|Back|Front|TouchAction|Action|trap|puzzle|secret|setMapTileIndex|setTileProperty", "UndergroundSecrets", "placement_rule")
    outputs["undergroundSecrets"] = {"sourceMod": "UndergroundSecrets", "records": underground}
    write_json(EVIDENCE_DIR / "underground_secrets_placement_evidence.json", outputs["undergroundSecrets"])

    mapedit = grep_records(aed / "MapEdit", r"TileLayers|tileDataDict|customSheets|TileIndex|Properties|AnimatedTile|StaticTile|SaveMapTile|AddTilesheet|layer", "MapEdit", "tile_stack_format")
    outputs["mapEdit"] = {"sourceMod": "MapEdit", "records": mapedit}
    write_json(EVIDENCE_DIR / "mapedit_tile_stack_format_evidence.json", outputs["mapEdit"])

    dmt = grep_records(aed / "DynamicMapTilesExtended", r"DMT/|Trigger|Action|Locations|Layers|TileSheets|TileSheetPaths|Indexes|Rectangles|Tiles|Teleport|Chest|Animation|Message", "DynamicMapTilesExtended", "interactive_tile_rule")
    outputs["dynamicMapTilesExtended"] = {"sourceMod": "DynamicMapTilesExtended", "records": dmt}
    write_json(EVIDENCE_DIR / "dynamic_tile_action_key_index.json", outputs["dynamicMapTilesExtended"])

    cp = grep_records(pathos / "ContentPatcher", r"EditMap|FromArea|ToArea|PatchMode|MapTiles|MapProperties|AddWarps|AddNpcWarps|TextOperations|ValidateWarp|TryValidateArea|ExtendMap|PatchMap", "Pathoschild.ContentPatcher", "map_patch_model")
    outputs["contentPatcher"] = {"sourceMod": "Pathoschild.ContentPatcher", "records": cp}
    write_json(EVIDENCE_DIR / "content_patcher_map_patch_model_evidence.json", outputs["contentPatcher"])

    dl = grep_records(pathos / "DataLayers", r"ILayer|DataLayerOverlay|TileGroup|LegendEntry|visibleArea|visibleTiles|cursorTile|Export|Grid|Shortcut", "Pathoschild.DataLayers", "overlay_model")
    outputs["dataLayers"] = {"sourceMod": "Pathoschild.DataLayers", "records": dl}
    write_json(EVIDENCE_DIR / "data_layers_overlay_model_evidence.json", outputs["dataLayers"])

    return outputs


def evidence_rules() -> dict[str, Any]:
    return {
        "autoApprovalThreshold": 95,
        "rules": [
            {"score": 100, "meaning": "vanilla authoritative metadata + exact candidate match + no conflict"},
            {"score": 98, "meaning": "Content Patcher or real map patch places exact tile on known layer with known sheet + matches vanilla/approved DB"},
            {"score": 97, "meaning": "working mod map file uses exact tile/layer repeatedly + matches vanilla/approved DB"},
            {"score": 96, "meaning": "structure matrix where every tile maps to approved/metadata-backed role"},
            {"score": 95, "meaning": "multiple independent working mods agree on exact tile/sheet/layer/role with no conflict"},
            {"score": 90, "meaning": "exact duplicate of approved tile/pattern with same sheet dimensions and layer/collision"},
            {"score": 85, "meaning": "proposal only; strong usage evidence but missing one proof"},
            {"score": 70, "meaning": "weak proposal; code variable name or single usage only"},
            {"score": 0, "meaning": "unsafe, conflicting, restricted, or ambiguous"},
        ],
        "neverAutoApproveIf": [
            "tile 946 unsafe role",
            "tilesheet unknown",
            "sheet width unknown for offset math",
            "layer unknown",
            "collision unknown for blocker/wall/path",
            "runtime transformation changes meaning",
            "variable name conflicts with observed usage",
            "restricted/custom asset",
            "Content Patcher target/source area ambiguous",
            "map patch extends outside known bounds",
            "hardcoded ID depends on unknown tilesheet column count",
            "conflicts with vanilla metadata",
            "conflicts with approved DB",
        ],
    }


def build_auto_approval_candidates(evidence: list[dict[str, Any]], approved_ids: set[str]) -> list[dict[str, Any]]:
    candidates = []
    for item in evidence:
        for cid in item.get("candidateIds", []):
            already_approved = cid in approved_ids
            flags = list(item.get("riskFlags", []))
            conflicts = list(item.get("conflicts", []))
            score = int(item.get("confidenceScore", 0))
            safe = (
                score >= 95
                and not flags
                and not conflicts
                and not already_approved
                and item.get("tilesheet")
                and item.get("layer") in STANDARD_LAYERS
            )
            if item.get("localTileId") == 946:
                safe = False
                flags.append("tile946_auto_approval_blocked_use_manual_override_only")
            candidates.append({
                "candidateId": cid,
                "sourceTilesheet": item.get("tilesheet"),
                "localTileId": item.get("localTileId"),
                "approvedClass": item.get("proposedClass"),
                "approvedPurpose": item.get("proposedPurpose"),
                "allowedLayers": [item.get("layer")] if item.get("layer") else [],
                "collision": item.get("collision"),
                "evidenceSources": [{
                    "sourceMod": item.get("sourceMod"),
                    "sourceFile": item.get("sourceFile"),
                    "evidenceType": item.get("evidenceType"),
                    "explanation": item.get("explanation"),
                }],
                "confidenceScore": score,
                "autoApprovalReason": "working_mod_evidence_threshold_met" if safe else "proposal_only_or_blocked_by_safety_gate",
                "conflicts": conflicts,
                "riskFlags": sorted(set(flags)),
                "alreadyApproved": already_approved,
                "tile946Status": "manual_canopy_override_only" if item.get("localTileId") == 946 else "not_tile_946",
                "restrictedAssetStatus": "blocked" if "restricted_or_custom_asset_context" in flags else "not_detected",
                "safeForAutoApproval": safe,
            })
    return candidates


def approved_tags_from_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    tags = []
    for cand in candidates:
        if not cand.get("safeForAutoApproval"):
            continue
        tags.append({
            "reviewPackId": "working_mod_evidence_auto_approved",
            "candidateIds": [cand["candidateId"]],
            "approvedClass": cand["approvedClass"],
            "approvedPurpose": cand["approvedPurpose"],
            "allowedLayers": cand["allowedLayers"],
            "collision": cand["collision"],
            "terrainSet": null_to_none(None),
            "terrainA": null_to_none(None),
            "terrainB": null_to_none(None),
            "edgeMask": [],
            "cornerMask": [],
            "transitionType": None,
            "footprint": None,
            "allowedRooms": [],
            "avoidNear": [],
            "weight": 1,
            "approvedBy": "codex_working_mod_evidence",
            "approvedAt": NOW,
            "source": "working_mod_cross_checked_evidence",
            "confidence": cand["confidenceScore"],
            "evidenceSourceFile": cand["evidenceSources"][0]["sourceFile"],
            "evidenceSummary": cand["evidenceSources"][0]["explanation"],
            "safetyNotes": "Auto-approved only because working mod evidence met the >=95 no-conflict gate.",
        })
    return {
        "generatedAt": NOW,
        "approvedBy": "codex_working_mod_evidence",
        "source": "working_mod_cross_checked_evidence",
        "tags": tags,
    }


def null_to_none(value: Any) -> Any:
    return value


def build_safe_pattern_candidates(special: dict[str, Any], evidence: list[dict[str, Any]], approved_ids: set[str]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for case in special.get("biggerminefloors", {}).get("cases", [])[:80]:
        patterns.append({
            "patternId": f"biggerminefloors_expansion_{case['baseTileIndex']}_{case['lineNumber']}",
            "patternName": f"BiggerMineFloors expansion seed {case['baseTileIndex']}",
            "patternType": "expansion_matrix",
            "sourceMod": "BiggerMineFloors",
            "evidenceSources": [{"sourceFile": case["sourceFile"], "lineNumber": case["lineNumber"]}],
            "tiles": [{"localTileId": case["baseTileIndex"], "role": case.get("roleLabelFromComments") or "unknown", "sheetBindingKnown": False}],
            "layerStack": {},
            "rules": {
                "requiresApprovedTiles": True,
                "requiresKnownTilesheetColumns": True,
                "forbidTile946UnsafeRoles": True,
                "canUseInProduction": False,
            },
            "confidenceScore": 70,
            "productionReady": False,
            "requiresHumanReview": True,
            "recommendedAction": "propose_for_review",
            "riskFlags": case.get("riskFlags", []),
        })
    for key, label in [
        ("additionalMineMaps", "floor_registry"),
        ("undergroundSecrets", "placement_rule"),
        ("mapEdit", "layer_stack"),
        ("dynamicMapTilesExtended", "interactive_tile_rule"),
        ("contentPatcher", "map_patch_model"),
        ("dataLayers", "overlay_model"),
    ]:
        records = special.get(key, {}).get("records", [])
        if records:
            patterns.append({
                "patternId": f"working_mod_{key}_{label}",
                "patternName": f"{special[key]['sourceMod']} {label}",
                "patternType": label,
                "sourceMod": special[key]["sourceMod"],
                "evidenceSources": records[:20],
                "tiles": [],
                "layerStack": {},
                "rules": {"requiresApprovedTiles": False, "forbidTile946UnsafeRoles": True, "canUseInProduction": False},
                "confidenceScore": 85,
                "productionReady": False,
                "requiresHumanReview": False if label in {"map_patch_model", "overlay_model", "floor_registry", "placement_rule"} else True,
                "recommendedAction": "propose_for_review",
                "riskFlags": ["non_tile_pattern_no_auto_tile_approval"],
            })
    for item in sorted(evidence, key=lambda e: e.get("confidenceScore", 0), reverse=True)[:100]:
        cids = item.get("candidateIds", [])
        if cids and any(cid in approved_ids for cid in cids):
            patterns.append({
                "patternId": f"approved_usage_{item['sourceMod']}_{item['layer']}_{item['localTileId']}",
                "patternName": f"Approved usage support {item['layer']} {item['localTileId']}",
                "patternType": "tile_group",
                "sourceMod": item["sourceMod"],
                "evidenceSources": [{"sourceFile": item["sourceFile"], "explanation": item["explanation"]}],
                "tiles": [{"candidateId": cid, "localTileId": item["localTileId"], "approved": cid in approved_ids} for cid in cids[:8]],
                "layerStack": {item["layer"]: cids[0]},
                "rules": {"requiresApprovedTiles": True, "forbidTile946UnsafeRoles": True, "canUseInProduction": False},
                "confidenceScore": min(90, item.get("confidenceScore", 0)),
                "productionReady": False,
                "requiresHumanReview": True,
                "recommendedAction": "propose_for_review",
                "riskFlags": item.get("riskFlags", []),
            })
    return patterns


def build_quarantine(id_entries: list[dict[str, Any]], evidence: list[dict[str, Any]], patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for entry in id_entries:
        flags = entry.get("riskFlags", [])
        if flags:
            out.append({"kind": "id_code_entry", "reason": ", ".join(flags), **entry})
    for item in evidence:
        flags = item.get("riskFlags", [])
        if flags or item.get("conflicts"):
            out.append({"kind": "tile_role_evidence", "reason": ", ".join(flags or item.get("conflicts", [])), **item})
    for pattern in patterns:
        flags = pattern.get("riskFlags", [])
        if flags or not pattern.get("productionReady"):
            out.append({"kind": "safe_pattern_candidate", "reason": ", ".join(flags) or "not production ready", **pattern})
    return out


def write_reports(inventory: list[dict[str, Any]], id_entries: list[dict[str, Any]], evidence: list[dict[str, Any]], auto_candidates: list[dict[str, Any]], patterns: list[dict[str, Any]], quarantine: list[dict[str, Any]]) -> None:
    inv_lines = ["# Working Mod Inventory", "", f"- Generated: {NOW}", f"- Sources inventoried: {len(inventory)}", ""]
    inv_lines.extend(["| Mod | Source | Code | Maps | Config/content | Assets | Risk | Evidence use |", "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |"])
    for item in inventory:
        use = []
        if item["codeCanBeUsedAsEvidence"]:
            use.append("code")
        if item["mapTileDataCanBeUsedAsEvidence"]:
            use.append("map")
        inv_lines.append(f"| {item['modName']} | {item['sourceType']} | {item['codeFiles']} | {item['mapFiles']} | {item['contentPacks']} | {item['assetFiles']} | {item['riskLevel']} | {', '.join(use) or 'reference only'} |")
    write_text(REPORT_DIR / "working_mod_inventory.md", "\n".join(inv_lines))

    score = evidence_rules()
    score_lines = ["# Working Mod Evidence Scoring Rules", "", f"- Generated: {NOW}", "", "## Auto-Approval Gate", "", f"- Minimum confidence: {score['autoApprovalThreshold']}", "- No conflicts.", "- No restricted/custom asset dependency.", "- Exact tilesheet, local tile ID, layer, and collision must be known.", "- Tile 946 canopy-only rule is enforced.", "", "## Scores", ""]
    score_lines.extend(f"- {rule['score']}: {rule['meaning']}" for rule in score["rules"])
    score_lines.extend(["", "## Never Auto-Approve If", ""])
    score_lines.extend(f"- {item}" for item in score["neverAutoApproveIf"])
    write_text(REPORT_DIR / "working_mod_evidence_scoring_rules.md", "\n".join(score_lines))

    id_counts = Counter(e["idType"] for e in id_entries)
    summary = [
        "# Working Mod ID/Code Mining Summary",
        "",
        f"- Generated: {NOW}",
        f"- ID/code entries indexed: {len(id_entries)}",
        f"- Tile role evidence entries: {len(evidence)}",
        "",
        "## ID Types",
        "",
    ]
    summary.extend(f"- {k}: {v}" for k, v in id_counts.most_common())
    summary.extend(["", "## Notes", "", "- Code-derived IDs are proposal evidence unless exact tilesheet/layer/collision can be proven.", "- BiggerMineFloors expansion matrices are useful but quarantined for sheet-width validation."])
    write_text(REPORT_DIR / "working_mod_id_code_mining_summary.md", "\n".join(summary))

    safe_count = sum(1 for c in auto_candidates if c.get("safeForAutoApproval"))
    auto_lines = [
        "# Working Mod Auto-Approval Report",
        "",
        f"- Generated: {NOW}",
        f"- Auto-approval candidates evaluated: {len(auto_candidates)}",
        f"- Safe auto-approvals written: {safe_count}",
        f"- Approved tag file: `tools/tiled-map-assistant/classification/approved_tags/working_mod_evidence_auto_approved.approved_tags.json`",
        "",
    ]
    if safe_count == 0:
        auto_lines.extend(["## Result", "", "No new tiles met the >=95 no-conflict auto-approval gate. The approved tag file is intentionally empty."])
    write_text(REPORT_DIR / "working_mod_auto_approval_report.md", "\n".join(auto_lines))

    pattern_lines = [
        "# Working Mod Safe Pattern Report",
        "",
        f"- Generated: {NOW}",
        f"- Pattern candidates created: {len(patterns)}",
        f"- Pattern suggestions file: `tools/tiled-map-assistant/pattern_learning/manual_safe_patterns/working_mod_pattern_suggestions.json`",
        "",
        "## Pattern Types",
        "",
    ]
    pattern_counts = Counter(p["patternType"] for p in patterns)
    pattern_lines.extend(f"- {k}: {v}" for k, v in pattern_counts.most_common())
    pattern_lines.extend(["", "## Safety", "", "- Suggestions are not merged into `manual_safe_patterns.json` automatically.", "- Production-ready remains false unless every tile is approved and pattern validation passes."])
    write_text(REPORT_DIR / "working_mod_safe_pattern_report.md", "\n".join(pattern_lines))

    q_counts = Counter(item.get("kind", "unknown") for item in quarantine)
    q_lines = [
        "# Working Mod Quarantine Report",
        "",
        f"- Generated: {NOW}",
        f"- Quarantined records: {len(quarantine)}",
        "",
        "## Categories",
        "",
    ]
    q_lines.extend(f"- {k}: {v}" for k, v in q_counts.most_common())
    q_lines.extend(["", "## Main Reasons", "", "- Unknown tilesheet binding.", "- Hardcoded tile IDs with unknown sheet width.", "- Restricted/custom asset contexts.", "- Runtime-only patch behavior.", "- Tile 946 unsafe or unapproved contexts."])
    write_text(REPORT_DIR / "working_mod_quarantine_report.md", "\n".join(q_lines))

    plan_lines = [
        "# Working Mod Generator Improvement Plan",
        "",
        f"- Generated: {NOW}",
        "",
        "## Safe Next Steps",
        "",
        "1. Add a tilesheet-aware offset resolver for BiggerMineFloors-style expansion matrices.",
        "2. Add clear-space scanner rules inspired by UndergroundSecrets.",
        "3. Add Content Patcher-style generated patch manifests with area/layer/warp validation.",
        "4. Add Data Layers-style reviewer overlay providers for validator heatmaps.",
        "5. Convert high-value expansion and placement patterns into manual safe pattern review packs.",
        "",
        "## Still Blocked",
        "",
        "- Auto-approval from hardcoded working-mod IDs remains blocked until exact sheet binding and metadata match are proven.",
        "- Restricted/custom working-mod assets remain reference-only.",
        "- Tile 946 remains canopy-center overlay only in approved seasonal outdoors contexts.",
    ]
    write_text(REPORT_DIR / "working_mod_generator_improvement_plan.md", "\n".join(plan_lines))


def main() -> int:
    ensure_dirs()
    sources = discover_sources()
    inventory = [inventory_source(src) for src in sources]
    write_json(RAW_DIR / "working_mod_inventory.json", {"generatedAt": NOW, "sources": inventory})

    id_entries: list[dict[str, Any]] = []
    for src in sources:
        id_entries.extend(extract_line_entries(src))
    write_json(RAW_DIR / "working_mod_id_code_index.json", {"generatedAt": NOW, "entries": id_entries})

    candidate_lookup = build_candidate_lookup()
    approved_ids = load_approved_candidate_ids()
    evidence = mine_map_evidence(sources, candidate_lookup)
    write_json(EVIDENCE_DIR / "tile_role_evidence_from_working_mods.json", {"generatedAt": NOW, "evidence": evidence})

    rules = evidence_rules()
    write_json(EVIDENCE_DIR / "evidence_scoring_rules.json", rules)

    special = special_outputs()
    auto_candidates = build_auto_approval_candidates(evidence, approved_ids)
    write_json(AUTO_DIR / "working_mod_auto_approval_candidates.json", {"generatedAt": NOW, "candidates": auto_candidates})
    approved_doc = approved_tags_from_candidates(auto_candidates)
    write_json(APPROVED_TAG_DIR / "working_mod_evidence_auto_approved.approved_tags.json", approved_doc)

    patterns = build_safe_pattern_candidates(special, evidence, approved_ids)
    write_json(PROPOSED_DIR / "working_mod_safe_pattern_candidates.json", {"generatedAt": NOW, "patterns": patterns})
    write_json(MANUAL_SAFE_PATTERN_DIR / "working_mod_pattern_suggestions.json", {"generatedAt": NOW, "patterns": patterns})

    quarantine = build_quarantine(id_entries, evidence, patterns)
    write_json(QUARANTINE_DIR / "working_mod_unsafe_or_ambiguous_evidence.json", {"generatedAt": NOW, "records": quarantine})

    write_reports(inventory, id_entries, evidence, auto_candidates, patterns, quarantine)

    print(f"Working mod mining complete: {len(inventory)} sources, {len(id_entries)} ID entries, {len(evidence)} evidence entries, {sum(1 for c in auto_candidates if c.get('safeForAutoApproval'))} auto-approvals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
