#!/usr/bin/env python3
"""Build the Tile Grammar Template System scaffold and first template library."""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
MISSION = ROOT / "mission_assets"
OUT_ROOT = ROOT / "pattern_learning" / "tile_grammar_templates"
RAW = OUT_ROOT / "raw_patterns"
REF_PATTERNS = OUT_ROOT / "reference_mod_patterns"
LIB = OUT_ROOT / "template_library"
PREVIEWS = OUT_ROOT / "previews"
FALLBACKS = OUT_ROOT / "fallbacks"
REPORTS = ROOT / "reports"
BACKUPS = ROOT / "backups"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))
import tbin_reader  # noqa: E402
from mine_wall_pattern_resolver import TILE_ROLE_CORRECTIONS, VANILLA_MINE_WALL_PATTERNS  # noqa: E402


VALID_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
VALID_COLLISIONS = ["unknown", "walkable", "blocked", "water_blocked", "decorative_front", "overlay_only", "marker_only", "custom_requires_review"]
TEMPLATE_TYPES = [
    "tile_group", "grid", "layer_stack", "neighbor_mask", "edge_mask", "corner_mask",
    "expansion_matrix", "opening_template", "room_template", "corridor_template",
    "transition_template", "floor_registry_template", "placement_rule_template",
    "overlay_template", "map_patch_template", "fallback_template",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE.resolve()))
    except Exception:
        return str(path.resolve())


def safe_load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def ensure_dirs() -> None:
    for d in (OUT_ROOT, RAW, REF_PATTERNS, LIB, PREVIEWS, FALLBACKS, REPORTS, BACKUPS):
        d.mkdir(parents=True, exist_ok=True)


def source_category(path: Path) -> str:
    s = str(path).replace("\\", "/")
    if "/mission_assets/unpacked_basegame/Mine/" in s:
        return "vanilla_mine"
    if "/mission_assets/unpacked_basegame/" in s:
        return "vanilla_basegame"
    if "/mission_assets/New_vanillaeditedmaps/" in s:
        return "New_vanillaeditedmaps"
    if "/mission_assets/moonvillage/" in s:
        return "Moonvillage"
    if "/mission_assets/reference_mods/" in s:
        return "reference_mod"
    if "/mission_assets/stardew_mods/" in s:
        return "stardew_mod"
    return "unknown"


def guess_profile(path: Path, tilesheets: Iterable[str], layers: Iterable[str]) -> str:
    blob = " ".join([path.name, str(path), *tilesheets, *layers]).lower()
    if any(k in blob for k in ("mine", "cave", "dungeon", "shaft", "volcano")):
        return "mine" if "mine" in blob or "shaft" in blob else "dungeon"
    if any(k in blob for k in ("farmhouse", "interior", "shop", "house", "room", "cellar")):
        return "indoor"
    if any(k in blob for k in ("town", "forest", "beach", "mountain", "woods", "outdoor")):
        return "outdoor"
    if "alwaysfront" in blob and "buildings" in blob:
        return "mixed"
    return "unknown"


def parse_tmx(path: Path) -> Optional[dict]:
    try:
        root = ET.parse(path).getroot()
        width = int(root.attrib.get("width", 0))
        height = int(root.attrib.get("height", 0))
        tilesheets = [img.attrib.get("source", "") for img in root.findall(".//tileset/image")]
        layers = [layer.attrib.get("name", "") for layer in root.findall("./layer")]
        return {"width": width, "height": height, "tilesheets": tilesheets, "layers": layers, "parseStatus": "parsed"}
    except Exception as exc:
        return {"width": None, "height": None, "tilesheets": [], "layers": [], "parseStatus": f"failed: {exc}"}


def parse_tmj(path: Path) -> Optional[dict]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        tilesheets = [ts.get("image", ts.get("source", "")) for ts in doc.get("tilesets", [])]
        layers = [layer.get("name", "") for layer in doc.get("layers", []) if layer.get("type") == "tilelayer"]
        return {"width": doc.get("width"), "height": doc.get("height"), "tilesheets": tilesheets, "layers": layers, "parseStatus": "parsed"}
    except Exception as exc:
        return {"width": None, "height": None, "tilesheets": [], "layers": [], "parseStatus": f"failed: {exc}"}


def parse_tbin(path: Path) -> Optional[dict]:
    try:
        mp = tbin_reader.parse(path.read_bytes())
        width, height = mp["layers"][0]["layerSize"] if mp.get("layers") else (None, None)
        tilesheets = [ts.get("imageSource", ts.get("id", "")) for ts in mp.get("tilesheets", [])]
        layers = [layer["id"] for layer in mp.get("layers", [])]
        return {"width": width, "height": height, "tilesheets": tilesheets, "layers": layers, "parseStatus": "parsed"}
    except Exception as exc:
        return {"width": None, "height": None, "tilesheets": [], "layers": [], "parseStatus": f"failed: {exc}"}


def inventory_maps() -> List[dict]:
    map_files = []
    for ext in ("*.tbin", "*.tmx", "*.tmj"):
        map_files.extend(MISSION.rglob(ext))
    entries = []
    for path in sorted(set(map_files)):
        if path.suffix.lower() == ".tbin":
            parsed = parse_tbin(path)
        elif path.suffix.lower() == ".tmx":
            parsed = parse_tmx(path)
        else:
            parsed = parse_tmj(path)
        parsed = parsed or {"width": None, "height": None, "tilesheets": [], "layers": [], "parseStatus": "failed"}
        category = source_category(path)
        risk = []
        if category in ("reference_mod", "stardew_mod"):
            risk.append("custom_or_third_party_assets_do_not_copy")
        if parsed["parseStatus"] != "parsed":
            risk.append("parse_failed")
        profile = guess_profile(path, parsed["tilesheets"], parsed["layers"])
        entries.append({
            "filePath": rel(path),
            "sourceCategory": category,
            "mapSize": {"width": parsed["width"], "height": parsed["height"]},
            "tilesheetsUsed": parsed["tilesheets"],
            "layersPresent": parsed["layers"],
            "safeToLearnFrom": parsed["parseStatus"] == "parsed",
            "riskFlags": risk,
            "profileGuess": profile,
            "parseStatus": parsed["parseStatus"],
        })
    return entries


def extract_tbin_stack_patterns(limit_maps: int = 180) -> List[dict]:
    patterns = []
    maps = [p for p in (MISSION / "unpacked_basegame").rglob("*.tbin")]
    maps += [p for p in (MISSION / "New_vanillaeditedmaps").rglob("*.tbin")] if (MISSION / "New_vanillaeditedmaps").exists() else []
    seen_count = Counter()
    examples = {}
    processed = 0
    for path in sorted(maps):
        if processed >= limit_maps:
            break
        try:
            mp = tbin_reader.parse(path.read_bytes())
        except Exception:
            continue
        processed += 1
        layers = {l["id"]: l for l in mp["layers"]}
        width, height = mp["layers"][0]["layerSize"]
        tilesheets = [ts.get("imageSource", ts.get("id", "")) for ts in mp.get("tilesheets", [])]
        profile = guess_profile(path, tilesheets, layers.keys())
        category = source_category(path)
        for y in range(height):
            for x in range(width):
                stack = {}
                for lname in VALID_LAYERS:
                    layer = layers.get(lname)
                    if not layer:
                        continue
                    payload = layer["tiles"].get((x, y))
                    if payload:
                        stack[lname] = payload[1]
                if not stack:
                    continue
                key = json.dumps({"profile": profile, "stack": stack}, sort_keys=True)
                seen_count[key] += 1
                if key not in examples:
                    examples[key] = {"path": path, "x": x, "y": y, "stack": stack, "profile": profile, "category": category, "tilesheets": tilesheets}
    for i, (key, count) in enumerate(seen_count.most_common(900), start=1):
        ex = examples[key]
        role = infer_role(ex["stack"], ex["profile"])
        patterns.append({
            "patternId": f"map_stack_{i:04d}",
            "sourceMap": rel(ex["path"]),
            "sourceCategory": ex["category"],
            "sourceTilesheets": ex["tilesheets"],
            "bounds": {"x": ex["x"], "y": ex["y"], "width": 1, "height": 1},
            "width": 1,
            "height": 1,
            "layerStack": ex["stack"],
            "tileIdsByLayer": ex["stack"],
            "neighborContext": "single coordinate stack; use with vanilla_layer_neighbor_patterns for expansion",
            "frequency": count,
            "profile": ex["profile"],
            "inferredRole": role,
            "confidence": min(95, 60 + min(35, count // 10)),
            "safeForPrototype": True,
            "safeForProduction": False,
            "requiresManualReview": True,
            "riskFlags": [] if ex["category"].startswith("vanilla") else ["non_vanilla_reference_evidence"],
        })
    return patterns


def infer_role(stack: dict, profile: str) -> str:
    if "Buildings" in stack and "Front" in stack:
        return "wall_or_structure_with_front_overlay"
    if "Buildings" in stack:
        return "blocking_structure_or_object"
    if "AlwaysFront" in stack:
        return "overhead_overlay"
    if "Paths" in stack:
        return "technical_path_or_marker"
    if "Back" in stack:
        if profile in ("mine", "dungeon"):
            return "cave_floor_or_ground"
        if profile == "indoor":
            return "floor_base"
        return "ground_or_path_base"
    return "unknown"


def convert_vanilla_mine_patterns() -> List[dict]:
    index = safe_load_json(ROOT / "pattern_learning" / "vanilla_mine_patterns" / "vanilla_mine_wall_pattern_index.json", {})
    out = []
    for item in index.get("patterns", [])[:300]:
        out.append({
            "patternId": item.get("patternId", "vanilla_mine_pattern"),
            "sourceMap": item.get("sourceMap", ""),
            "sourceCategory": "vanilla_mine",
            "sourceTilesheets": [item.get("sourceTilesheet", "mine")],
            "bounds": item.get("bounds", {}),
            "width": item.get("bounds", {}).get("width", 3),
            "height": item.get("bounds", {}).get("height", 3),
            "layerStack": item.get("layerStack", {}),
            "tileIdsByLayer": item.get("localTileIdsByLayer", {}),
            "neighborContext": "vanilla mine 3x3 wall/floor context",
            "frequency": item.get("frequencyCount", 1),
            "profile": "mine",
            "inferredRole": item.get("roleInterpretation", "mine_wall_structure"),
            "confidence": min(95, 72 + min(20, item.get("frequencyCount", 1))),
            "safeForPrototype": True,
            "safeForProduction": False,
            "requiresManualReview": True,
            "riskFlags": ["prototype_only_until_manual_safe_pattern"],
        })
    return out


def template_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Tile Grammar Template",
        "type": "object",
        "required": ["templateId", "templateName", "templateType", "profile", "category", "sourceEvidence", "requiredLayers", "tile946Policy", "confidence", "productionStatus", "fallbackTemplateId", "validationRules"],
        "properties": {
            "templateId": {"type": "string"},
            "templateName": {"type": "string"},
            "templateType": {"enum": TEMPLATE_TYPES},
            "profile": {"enum": ["outdoor", "indoor", "dungeon", "mine", "mixed", "all"]},
            "category": {"type": "string"},
            "sourceEvidence": {"type": "array"},
            "workingModEvidence": {"type": "array"},
            "requiredLayers": {"type": "array", "items": {"enum": VALID_LAYERS}},
            "requiredRoles": {"type": "array"},
            "optionalRoles": {"type": "array"},
            "tileStack": {"type": ["object", "array"]},
            "grid": {"type": ["object", "array"]},
            "neighborRules": {"type": ["object", "array"]},
            "collisionRules": {"type": ["object", "array"]},
            "placementRules": {"type": ["object", "array"]},
            "allowedStylepacks": {"type": "array"},
            "disallowedTiles": {"type": "array"},
            "tile946Policy": {"type": "string"},
            "confidence": {"type": "number"},
            "productionStatus": {"enum": ["prototype_only", "marker_only", "review_needed", "production_ready", "blocked"]},
            "fallbackTemplateId": {"type": "string"},
            "validationRules": {"type": "array"},
            "notes": {"type": "string"},
        },
    }


def make_template(template_id: str, name: str, typ: str, profile: str, category: str, layers: List[str], roles: List[str],
                  stack=None, grid=None, evidence=None, wm_evidence=None, confidence=80, status="review_needed",
                  fallback="marker_only_generic", notes="", collision=None, placement=None) -> dict:
    return {
        "templateId": template_id,
        "templateName": name,
        "templateType": typ,
        "profile": profile,
        "category": category,
        "sourceEvidence": evidence or [],
        "workingModEvidence": wm_evidence or [],
        "requiredLayers": layers,
        "requiredRoles": roles,
        "optionalRoles": [],
        "tileStack": stack or {},
        "grid": grid or {},
        "neighborRules": [],
        "collisionRules": collision or [],
        "placementRules": placement or [],
        "allowedStylepacks": ["moonvillage_forest_ruins", "void_dungeon", "prototype_visual_review"],
        "disallowedTiles": [946],
        "tile946Policy": "forbidden_for_wall_body_blocking_collision; allowed only approved outdoor canopy overlay contexts",
        "confidence": confidence,
        "productionStatus": status,
        "fallbackTemplateId": fallback,
        "validationRules": ["valid_layers", "tile946_policy", "no_production_if_prototype_only", "fallback_available"],
        "notes": notes,
    }


def build_templates(working_patterns: List[dict]) -> List[dict]:
    wm_by_kind = {}
    for p in working_patterns:
        wm_by_kind.setdefault(p.get("evidenceKind", "unknown"), []).append(p)
    templates = []
    templates.append(make_template("marker_only_generic", "Generic Marker-Only Fallback", "fallback_template", "all", "fallback", [], [], confidence=100, status="marker_only", fallback="blocked_with_report", notes="Use semantic marker output when visual template resolution fails."))
    templates.append(make_template("blocked_with_report", "Blocked With Report", "fallback_template", "all", "fallback", [], [], confidence=100, status="blocked", fallback="", notes="Fail closed and write a report."))
    templates.append(make_template("mine_basic_floor", "Mine Basic Floor", "tile_group", "mine", "floor", ["Back"], ["cave_floor_base"], {"Back": [138, 137, 139, 140, 153, 154, 155, 169, 170, 171, 185, 187, 188]}, confidence=88, status="prototype_only", notes="Excludes 186 and 220 from random floor pools."))
    templates.append(make_template("mine_floor_variation", "Mine Floor Variation", "tile_group", "mine", "floor", ["Back"], ["cave_floor_variation"], {"Back": [217, 218, 219, 233, 234, 235, 201, 202, 203]}, confidence=84, status="prototype_only", notes="Prototype-only floor detail pool; wall-context tiles excluded."))
    templates.append(make_template("mine_straight_wall_stack", "Mine Straight Wall Stack", "grid", "mine", "wall", ["Back", "Buildings", "Front"], ["cave_wall_body", "cave_wall_top", "cave_shadow"], grid={"rows": [{"Buildings": [69, 70, 73, 74]}, {"Buildings": [101, 102, 105, 106]}, {"Back": [186], "Buildings": [121, 122, 123, 124], "Front": [213, 214, 215, 216]}]}, evidence=["vanilla_mine_wall_pattern_index"], confidence=92, status="prototype_only"))
    templates.append(make_template("mine_wall_top", "Mine Wall Top", "layer_stack", "mine", "wall", ["Buildings"], ["wall_top"], {"Buildings": [69, 70, 73, 74, 75, 76, 93, 94]}, confidence=90, status="prototype_only"))
    templates.append(make_template("mine_wall_body", "Mine Wall Body", "layer_stack", "mine", "wall", ["Buildings"], ["wall_body"], {"Buildings": [85, 86, 89, 90, 101, 102, 105, 106, 107, 108, 117, 118, 133, 134]}, confidence=88, status="prototype_only"))
    templates.append(make_template("mine_left_edge", "Mine Left Wall Edge", "edge_mask", "mine", "wall_edge", ["Buildings", "Front"], ["wall_edge"], {"Buildings": [68, 84, 100, 116, 132, 148, 196], "Front": [196, 197]}, confidence=88, status="prototype_only"))
    templates.append(make_template("mine_right_edge", "Mine Right Wall Edge", "edge_mask", "mine", "wall_edge", ["Buildings", "Front"], ["wall_edge"], {"Buildings": [72, 88, 104, 120, 158, 191, 207], "Front": [205, 206, 220, 221, 232]}, confidence=88, status="prototype_only"))
    templates.append(make_template("mine_wall_corner", "Mine Wall Corner", "corner_mask", "mine", "wall_corner", ["Buildings"], ["wall_corner"], {"Buildings": [93, 94, 109, 110, 125, 126, 123, 124]}, confidence=86, status="prototype_only"))
    templates.append(make_template("mine_inner_corner", "Mine Inner Corner", "corner_mask", "mine", "wall_corner", ["Back", "Buildings", "Front"], ["inner_corner", "cave_shadow"], {"Back": [186], "Buildings": [119, 120, 123, 124, 158], "Front": [220, 221, 232]}, confidence=84, status="prototype_only"))
    templates.append(make_template("mine_shadow_under_wall", "Mine Shadow Under Wall", "layer_stack", "mine", "shadow", ["Back", "Front"], ["cave_shadow"], {"Back": [186], "Front": [213, 214, 215, 216, 220]}, confidence=92, status="prototype_only", notes="Tile 186 is contextual Back under-wall shadow; tile 220 is Front only."))
    templates.append(make_template("mine_ladder_opening", "Mine Ladder Opening", "opening_template", "mine", "opening", ["Back", "Buildings"], ["ladder", "exit"], {"Buildings": [67, 83, 99, 115], "Back": [77, 186]}, wm_evidence=wm_by_kind.get("code_matrix", [])[:3], confidence=90, status="prototype_only", notes="Ladder stack must be anchored into wall side/cap tiles and remain reachable."))
    templates.append(make_template("mine_shaft_opening", "Mine Shaft Opening", "opening_template", "mine", "opening", ["Back", "Buildings"], ["shaft", "exit"], {"Buildings": [], "Back": []}, confidence=55, status="review_needed", notes="Needs manual review; no safe shaft tile template yet."))
    templates.append(make_template("mine_entrance_opening", "Mine Entrance Opening", "opening_template", "mine", "opening", ["Back"], ["entrance"], {"Back": [138, 137, 139]}, confidence=80, status="prototype_only"))
    templates.append(make_template("mine_blocked_boundary", "Mine Blocked Boundary", "neighbor_mask", "mine", "boundary", ["Back", "Buildings"], ["blocked_boundary"], {"Back": [77], "Buildings": [68, 69, 70, 71, 72, 73, 74, 75, 76]}, confidence=86, status="prototype_only"))
    templates.append(make_template("mine_floor_registry", "Mine Floor Registry", "floor_registry_template", "mine", "registry", [], ["floor_registry"], wm_evidence=wm_by_kind.get("floor_registry", [])[:10], confidence=82, status="prototype_only"))
    templates.append(make_template("mine_level_region", "Mine Level Region", "room_template", "mine", "region", ["Back", "Buildings"], ["level_region"], wm_evidence=wm_by_kind.get("floor_registry", [])[:5], confidence=78, status="prototype_only"))
    templates.append(make_template("mine_weighted_map_pool", "Mine Weighted Map Pool", "floor_registry_template", "mine", "registry", [], ["weighted_map_pool"], wm_evidence=wm_by_kind.get("floor_registry", [])[:10], confidence=82, status="prototype_only"))
    templates.append(make_template("mine_clear_space_placement", "Mine Clear-Space Placement Rule", "placement_rule_template", "mine", "placement", [], ["clear_space", "protected_zone"], wm_evidence=wm_by_kind.get("placement_rule", [])[:5], confidence=88, status="prototype_only", placement=[{"rule": "reject Buildings", "layers": ["Buildings"]}, {"rule": "protect ladder/entrance radius", "radius": 2}]))
    templates.append(make_template("mine_secret_trap_ore_treasure_pocket", "Mine Safe Secret/Ore/Treasure Pocket", "placement_rule_template", "mine", "placement", ["Back", "Buildings"], ["ore_pocket", "treasure_pocket", "secret_pocket"], wm_evidence=wm_by_kind.get("placement_rule", [])[:5], confidence=76, status="review_needed"))
    templates.append(make_template("outdoor_marker_fallback", "Outdoor Marker Fallback", "fallback_template", "outdoor", "fallback", [], [], confidence=100, status="marker_only", fallback="marker_only_generic"))
    templates.append(make_template("indoor_marker_fallback", "Indoor Marker Fallback", "fallback_template", "indoor", "fallback", [], [], confidence=100, status="marker_only", fallback="marker_only_generic"))
    templates.append(make_template("dungeon_marker_fallback", "Dungeon/Mine Marker Fallback", "fallback_template", "dungeon", "fallback", [], [], confidence=100, status="marker_only", fallback="marker_only_generic"))
    return templates


def grammar_rules(profile: str) -> dict:
    if profile in ("dungeon", "mine"):
        required_roles = ["cave_floor_base", "cave_floor_variation", "cave_wall_body", "cave_wall_top", "cave_wall_corner", "cave_wall_edge", "cave_shadow", "ladder", "exit"]
        return {
            "profile": "dungeon_mine",
            "requiredStructuralRoles": required_roles,
            "allowedLayerStacks": ["Back", "Back+Buildings", "Back+Front", "Back+Buildings+Front", "Back+Paths"],
            "forbiddenLayerStacks": ["AlwaysFront_collision", "Buildings_without_Back_in_production", "tile946_wall_or_collision"],
            "defaultFallbackTemplates": ["dungeon_marker_fallback", "marker_only_generic", "blocked_with_report"],
            "requiredOpeningRules": ["mine_ladder_opening", "mine_entrance_opening"],
            "pathFloorConnectivityRules": ["entrance_exit_reachable", "no_out_of_bounds_escape"],
            "wallCornerRules": ["mine_straight_wall_stack", "mine_wall_corner", "mine_inner_corner"],
            "shadowRules": ["mine_shadow_under_wall"],
            "collisionRules": ["Buildings wall templates are blocked", "Back/Front overlays do not define collision"],
            "tile946Rules": "forbidden in dungeon/mine output",
            "stylepackCompatibilityRules": ["void_dungeon marker_only until reviewed", "prototype_visual_review allowed prototype_only"],
            "workingModLessons": ["BiggerMineFloors expansion matrices require sheet binding", "UndergroundSecrets clear-space rules protect ladders", "AdditionalMineMaps suggests floor registry metadata"],
        }
    if profile == "outdoor":
        return {
            "profile": "outdoor",
            "requiredStructuralRoles": ["ground_base", "path_base", "path_transition", "hedge_or_wall_body", "edge", "corner", "shadow"],
            "allowedLayerStacks": ["Back", "Back+Buildings", "Back+Front", "Back+AlwaysFront", "Back+Paths"],
            "forbiddenLayerStacks": ["AlwaysFront_collision", "tile946_non_canopy_context"],
            "defaultFallbackTemplates": ["outdoor_marker_fallback", "marker_only_generic", "blocked_with_report"],
            "requiredOpeningRules": ["entrance_exit_reachable"],
            "pathFloorConnectivityRules": ["protected_exit_capsule", "no_edge_leaks"],
            "wallCornerRules": ["review_needed"],
            "shadowRules": ["review_needed"],
            "collisionRules": ["Buildings define blocking; AlwaysFront never collision"],
            "tile946Rules": "allowed only seasonal outdoors canopy_overlay/tree_canopy_center/AlwaysFront/overlay_only",
            "stylepackCompatibilityRules": ["moonvillage_forest_ruins outdoor-first", "fairy_forest outdoor-first"],
            "workingModLessons": ["DeepWoods border passes and placement protection"],
        }
    return {
        "profile": "indoor",
        "requiredStructuralRoles": ["floor_base", "floor_trim", "interior_wall_body", "interior_wall_top", "doorway", "shadow"],
        "allowedLayerStacks": ["Back", "Back+Buildings", "Back+Buildings+Front", "Back+Front"],
        "forbiddenLayerStacks": ["AlwaysFront_collision", "Buildings_without_Back_in_production"],
        "defaultFallbackTemplates": ["indoor_marker_fallback", "marker_only_generic", "blocked_with_report"],
        "requiredOpeningRules": ["doorway_threshold_reachable"],
        "pathFloorConnectivityRules": ["rooms_connected"],
        "wallCornerRules": ["review_needed"],
        "shadowRules": ["review_needed"],
        "collisionRules": ["Buildings furniture/walls block; rugs/floor trims do not"],
        "tile946Rules": "forbidden unless separately approved in indoor sheet context",
        "stylepackCompatibilityRules": ["future_interiors marker_only until reviewed"],
        "workingModLessons": ["IndoorOutdoor zone metadata can support mixed-profile maps"],
    }


def fallback_rules() -> dict:
    return {
        "generatedAt": now_iso(),
        "fallbackChain": [
            "exact_safe_template",
            "approved_safe_pattern",
            "high_confidence_working_mod_template",
            "high_confidence_reference_map_template",
            "profile_generic_template",
            "marker_only_template",
            "blocked_with_report",
        ],
        "rules": [
            {"condition": "required_template_missing", "action": "marker_only_template", "reason": "Do not place random visual tiles."},
            {"condition": "tile_missing_approval_for_production", "action": "marker_only_template"},
            {"condition": "layer_grammar_failure", "action": "marker_only_template"},
            {"condition": "collision_unknown_for_blocking_role", "action": "marker_only_template"},
            {"condition": "tile946_unsafe_role", "action": "blocked_with_report"},
            {"condition": "prototype_only_template_in_production", "action": "blocked_with_report"},
            {"condition": "provisional_visual_tile_used_in_prototype", "action": "record_provisional_usage"},
            {"condition": "working_mod_evidence_not_independently_safe", "action": "prototype_only_or_review_needed"},
        ],
    }


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_inventory_reports(map_inventory: List[dict]) -> None:
    counts = Counter(item["sourceCategory"] for item in map_inventory)
    profiles = Counter(item["profileGuess"] for item in map_inventory)
    lines = [
        "# Tile Grammar Reference Map Inventory",
        "",
        f"- Total map files inventoried: {len(map_inventory)}",
        "",
        "## By Source Category",
    ]
    for k, v in sorted(counts.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## By Profile Guess"]
    for k, v in sorted(profiles.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Safety", "- Vanilla and Moonvillage maps are learning sources.", "- Reference/stardew mod maps are evidence only; their assets must not be copied."]
    (REPORTS / "tile_grammar_reference_map_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_reports(map_inventory: List[dict], raw_patterns: List[dict], wm_patterns: List[dict], templates: List[dict]) -> None:
    counts = Counter(t["productionStatus"] for t in templates)
    (REPORTS / "unified_tile_grammar_evidence_summary.md").write_text(
        "\n".join([
            "# Unified Tile Grammar Evidence Summary",
            "",
            f"- Reference map patterns: {len(raw_patterns)}",
            f"- Working mod evidence patterns: {len(wm_patterns)}",
            f"- Unified recommendations: template_library for high-confidence vanilla mine templates; prototype_only/review_needed for non-approved visual structures.",
            "- Tile 946 unsafe roles remain blocked.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "profile_tile_grammar_rules_summary.md").write_text(
        "\n".join([
            "# Profile Tile Grammar Rules Summary",
            "",
            "- Dungeon/mine rules were prioritized and include floor, wall stack, shadow, ladder, registry, and placement templates.",
            "- Outdoor and indoor profiles currently receive marker fallback rule sets until their structural templates are manually reviewed.",
            "- All profiles fail closed through marker-only or blocked-with-report fallbacks.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_fallback_system.md").write_text(
        "\n".join([
            "# Tile Grammar Fallback System",
            "",
            "Fallback chain:",
            "1. exact approved template / safe pattern",
            "2. learned high-confidence reference or working-mod template",
            "3. profile-specific generic safe template",
            "4. marker-only fallback",
            "5. blocked with report",
            "",
            "No random visual tile placement is allowed when template resolution fails.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "dungeon_mine_template_learning_summary.md").write_text(
        "\n".join([
            "# Dungeon/Mine Template Learning Summary",
            "",
            "- Vanilla mine wall/floor/ladder patterns were converted into prototype-only templates.",
            "- Tile `220`: Front overlay only; removed from random Back floor use.",
            "- Tile `186`: contextual Back under-wall shadow/floor only.",
            "- Tiles `119-124` and `158`: Buildings wall/edge stack pieces.",
            "- BiggerMineFloors contributed expansion-matrix lessons, but hardcoded IDs remain review evidence unless sheet binding is exact.",
            "- UndergroundSecrets contributed clear-space and ladder-protection placement grammar.",
            "- AdditionalMineMaps contributed floor registry/map-pool grammar.",
            "- DeepWoods contributed procedural pass/order/exit lessons via prior reports; no DeepWoods art is used.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_template_system_summary.md").write_text(
        "\n".join([
            "# Tile Grammar Template System Summary",
            "",
            f"- Reference maps inventoried: {len(map_inventory)}",
            f"- Raw/extracted map patterns: {len(raw_patterns)}",
            f"- Working-mod evidence patterns: {len(wm_patterns)}",
            f"- Templates created: {len(templates)}",
            f"- Template statuses: {dict(counts)}",
            "- Existing marker generator and stylepacks were not deleted or replaced.",
            "- `generate_visual_map_v2.py` is the new parallel generator entry point.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_working_mod_evidence_summary.md").write_text(
        "\n".join([
            "# Tile Grammar Working Mod Evidence Summary",
            "",
            f"- Working-mod grammar entries available: {len(wm_patterns)}",
            "- Code-only hints are quarantined or review-needed unless exact sheet/layer/collision binding exists.",
            "- No working-mod assets were copied.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_template_generator_integration.md").write_text(
        "\n".join([
            "# Tile Grammar Template Generator Integration",
            "",
            "- New integration point: `generate_visual_map_v2.py`.",
            "- Old behavior remains available through `generate_marker_map.py` and the previous prototype builders.",
            "- V2 reads `tile_grammar_template_library.json`, applies profile rules, and falls back to marker-only output when visual templates are unavailable.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_template_safety_status.md").write_text(
        "\n".join([
            "# Tile Grammar Template Safety Status",
            "",
            "- Production maps generated: NO.",
            "- Original Moonvillage maps modified: NO.",
            "- mission_assets modified: NO.",
            "- unpacked basegame modified: NO.",
            "- Approved DB modified: NO.",
            "- Tile 946 policy preserved.",
            "- All visual templates are `prototype_only`, `review_needed`, `marker_only`, or `blocked` unless later manually approved.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "tile_grammar_next_manual_review_targets.md").write_text(
        "\n".join([
            "# Tile Grammar Next Manual Review Targets",
            "",
            "1. Mine wall stack: top/body/lower-face grid.",
            "2. Mine shadow under wall: Back `186` plus Front overlays.",
            "3. Mine ladder opening: `67/83/99/115` with side caps.",
            "4. Mine ore/treasure pocket placement.",
            "5. Outdoor path/hedge/canopy edge templates.",
            "6. Indoor wall/floor/doorway templates.",
        ]) + "\n",
        encoding="utf-8",
    )


def write_backup_manifest(created_files: List[Path]) -> None:
    doc = {
        "generatedAt": now_iso(),
        "purpose": "tile_grammar_template_system_backup_manifest",
        "existingGeneratorsModified": False,
        "oldBehaviorAvailable": ["generate_marker_map.py", "build_dungeon_visual_prototypes.py", "fix_dungeon_visual_wall_patterns.py"],
        "newOrUpdatedFiles": [rel(p) for p in created_files],
    }
    write_json(BACKUPS / "tile_grammar_template_system_backup_manifest.json", doc)
    (REPORTS / "tile_grammar_template_rollback_plan.md").write_text(
        "\n".join([
            "# Tile Grammar Template Rollback Plan",
            "",
            "- Disable visual template generation by not calling `generate_visual_map_v2.py`.",
            "- Return to marker-only generation with `generate_marker_map.py`.",
            "- Existing old prototype builders remain available.",
            "- Remove prototype outputs under `prototype_visual_maps/template_system_tests/` and `custom_03_template_fixed.*` if desired.",
            "- Remove newly created template-system JSON/scripts listed in `backups/tile_grammar_template_system_backup_manifest.json` to fully roll back this scaffold.",
        ]) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ensure_dirs()
    map_inventory = inventory_maps()
    write_json(OUT_ROOT / "reference_map_inventory.json", {"generatedAt": now_iso(), "maps": map_inventory})
    raw_patterns = extract_tbin_stack_patterns()
    raw_patterns += convert_vanilla_mine_patterns()
    write_json(RAW / "extracted_structure_patterns.json", {"generatedAt": now_iso(), "patterns": raw_patterns})
    wm_doc = safe_load_json(REF_PATTERNS / "working_mod_structure_patterns.json", {"patterns": []})
    wm_patterns = wm_doc.get("patterns", [])
    unified = []
    for p in raw_patterns[:700]:
        rec = p.copy()
        rec.update({
            "evidenceFromVanillaMaps": p["sourceCategory"].startswith("vanilla"),
            "evidenceFromReferenceMaps": p["sourceCategory"] in ("reference_mod", "stardew_mod", "Moonvillage", "New_vanillaeditedmaps"),
            "evidenceFromWorkingMods": False,
            "agreementScore": p.get("frequency", 1),
            "conflictScore": 0,
            "sheetBindingStatus": "known" if p.get("sourceTilesheets") else "unknown",
            "layerConfidence": p.get("confidence", 50),
            "collisionConfidence": 65 if "Buildings" in json.dumps(p.get("layerStack", {})) else 45,
            "tile946Status": "not_involved",
            "restrictedAssetStatus": "vanilla_or_evidence_only",
            "finalRecommendation": "template_library" if p["profile"] in ("mine", "dungeon") and p["sourceCategory"].startswith("vanilla") else "manual_safe_pattern_review",
        })
        unified.append(rec)
    for p in wm_patterns[:700]:
        unified.append({
            "patternId": f"working_mod_{len(unified) + 1:04d}",
            "sourceMap": p.get("sourceFile", ""),
            "sourceCategory": "working_mod",
            "sourceTilesheets": [p.get("tilesheetBinding", "")],
            "bounds": {},
            "width": None,
            "height": None,
            "layerStack": p.get("layers", []),
            "tileIdsByLayer": p.get("tileIds", []),
            "neighborContext": p.get("patternShape", ""),
            "frequency": 1,
            "profile": "mine" if "mine" in json.dumps(p).lower() else "mixed",
            "inferredRole": p.get("inferredRole", ""),
            "confidence": p.get("confidence", 50),
            "safeForPrototype": p.get("safeForPrototype", False),
            "safeForProduction": p.get("safeForProduction", False),
            "requiresManualReview": not p.get("safeForProduction", False),
            "riskFlags": p.get("riskFlags", []),
            "evidenceFromVanillaMaps": False,
            "evidenceFromReferenceMaps": False,
            "evidenceFromWorkingMods": True,
            "agreementScore": p.get("confidence", 0),
            "conflictScore": 0 if p.get("safeForPrototype") else 50,
            "sheetBindingStatus": "known" if p.get("tilesheetBinding") and "unknown" not in str(p.get("tilesheetBinding")).lower() else "unknown",
            "layerConfidence": p.get("confidence", 50),
            "collisionConfidence": 40,
            "tile946Status": "blocked_if_unsafe",
            "restrictedAssetStatus": "evidence_only_no_assets_copied",
            "finalRecommendation": "prototype_only" if p.get("safeForPrototype") else "quarantine",
        })
    write_json(RAW / "unified_tile_grammar_evidence_index.json", {"generatedAt": now_iso(), "patterns": unified})
    templates = build_templates(wm_patterns)
    write_json(LIB / "tile_grammar_template_schema.json", template_schema())
    write_json(LIB / "tile_grammar_template_library.json", {"generatedAt": now_iso(), "templates": templates})
    write_json(LIB / "dungeon_mine_template_pack.json", {"generatedAt": now_iso(), "templates": [t for t in templates if t["profile"] in ("mine", "dungeon") or t["templateId"] in ("marker_only_generic", "blocked_with_report")]})
    write_json(LIB / "dungeon_mine_grammar_rules.json", grammar_rules("mine"))
    write_json(LIB / "outdoor_grammar_rules.json", grammar_rules("outdoor"))
    write_json(LIB / "indoor_grammar_rules.json", grammar_rules("indoor"))
    write_json(FALLBACKS / "generator_fallback_rules.json", fallback_rules())
    write_inventory_reports(map_inventory)
    write_summary_reports(map_inventory, raw_patterns, wm_patterns, templates)
    created = [
        OUT_ROOT / "reference_map_inventory.json",
        RAW / "extracted_structure_patterns.json",
        RAW / "unified_tile_grammar_evidence_index.json",
        LIB / "tile_grammar_template_schema.json",
        LIB / "tile_grammar_template_library.json",
        LIB / "dungeon_mine_template_pack.json",
        LIB / "dungeon_mine_grammar_rules.json",
        LIB / "outdoor_grammar_rules.json",
        LIB / "indoor_grammar_rules.json",
        FALLBACKS / "generator_fallback_rules.json",
    ]
    write_backup_manifest(created)
    print(json.dumps({"status": "PASS", "maps": len(map_inventory), "rawPatterns": len(raw_patterns), "templates": len(templates)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
