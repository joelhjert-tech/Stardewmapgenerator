#!/usr/bin/env python3
"""Learn Stardew layer and stack patterns from vanilla maps.

This is a read-only pattern-learning pass. It parses unpacked vanilla .tbin maps,
uses vanilla authoritative metadata where available, derives aggregate layer and
stack grammar, then lightly compares copied Moonvillage/reference maps without
modifying mission_assets or original maps.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import re
import struct
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import tbin_reader as T
from tma_path_helpers import resolve_vanilla_authoritative_index


TOOL_ROOT = Path(__file__).resolve().parent
UNPACKED_BASEGAME = TOOL_ROOT / "mission_assets" / "unpacked_basegame"
PATTERN_ROOT = TOOL_ROOT / "pattern_learning"
VANILLA_ROOT = PATTERN_ROOT / "vanilla"
MOON_ROOT = PATTERN_ROOT / "moonvillage"
REFERENCE_ROOT = PATTERN_ROOT / "reference_mods"
COMBO_ROOT = PATTERN_ROOT / "layer_combinations"
REPORTS_ROOT = TOOL_ROOT / "reports"
DATABASE_ROOT = TOOL_ROOT / "database"
STYLEPACK_ROOT = TOOL_ROOT / "stylepacks"
MAP_CATALOG_PATH = DATABASE_ROOT / "map_catalog.json"
APPROVED_DB_PATH = DATABASE_ROOT / "tile_database_v1_human_approved.json"

STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
VALID_OUTPUT_LAYERS = set(STANDARD_LAYERS)
GID_MASK = 0x1FFFFFFF
MAX_EXAMPLES = 12
MAX_TOP = 100
MAX_TILE_USAGE = 250


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for path in [PATTERN_ROOT, VANILLA_ROOT, MOON_ROOT, REFERENCE_ROOT, COMBO_ROOT, REPORTS_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def base_key(name: str | None) -> str:
    if not name:
        return "unknown"
    n = str(name).replace("\\", "/").split("/")[-1].lower()
    for suffix in [".png", ".tsx", ".tbin", ".json"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def tile_key(sheet_base: str | None, idx: int | None) -> str:
    return f"{base_key(sheet_base)}:{idx if idx is not None else 'unknown'}"


def split_tile_key(key: str) -> tuple[str, int | None]:
    if ":" not in key:
        return key, None
    sheet, idx = key.rsplit(":", 1)
    try:
        return sheet, int(idx)
    except ValueError:
        return sheet, None


def path_stem_key(value: Any) -> str:
    if value is None:
        return ""
    return base_key(Path(str(value).replace("\\", "/")).name)


def short_hash(value: Any) -> str:
    return hashlib.sha1(str(value).encode("utf-8", errors="ignore")).hexdigest()[:12]


def safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def add_example(target: list[dict[str, Any]], example: dict[str, Any], limit: int = MAX_EXAMPLES) -> None:
    if len(target) < limit:
        target.append(example)


def top_counter(counter: Counter, limit: int = MAX_TOP) -> list[dict[str, Any]]:
    return [{"key": str(k), "count": int(v)} for k, v in counter.most_common(limit)]


def counter_dict(counter: Counter, limit: int | None = None) -> dict[str, int]:
    items = counter.most_common(limit) if limit else counter.items()
    return {str(k): int(v) for k, v in items}


def infer_map_category(map_name: str) -> str:
    n = map_name.lower()
    if any(word in n for word in ["festival", "fair", "halloween", "christmas", "luau", "jellies", "eggfestival", "flowerfestival", "icefestival", "squidfest", "nightmarket"]):
        return "festival"
    if re.fullmatch(r"\d+", Path(n).stem) or any(word in n for word in ["mine", "skullcave", "volcano", "caldera", "cave"]):
        return "mine"
    if "beach" in n or "submarine" in n or "elliottsea" in n:
        return "beach exterior"
    if any(word in n for word in ["mountain", "railroad", "backwoods", "summit"]):
        return "mountain exterior"
    if any(word in n for word in ["forest", "woods", "witchswamp", "bugland"]):
        return "forest exterior"
    if any(word in n for word in ["town", "busstop", "desert", "farm", "island_", "island-", "islandw", "islands", "islandn"]):
        if "farmhouse" not in n and "farmcave" not in n and "island_house" not in n:
            return "town exterior"
    if any(word in n for word in ["farmhouse", "spouseroom", "cellar", "sunroom"]):
        return "farmhouse/interior"
    if any(word in n for word in ["shop", "saloon", "blacksmith", "animalshop", "seedshop", "fishshop", "jojalmart", "hospital", "adventureguild", "archaeologyhouse"]):
        return "shop/interior"
    if any(word in n for word in ["house", "room", "hut", "barn", "coop", "shed", "theater", "club", "bathhouse", "communitycenter", "trailer", "tent", "manor", "wizard"]):
        return "farmhouse/interior"
    if any(word in n for word in ["event", "dream", "scene", "show", "targetgame", "fishinggame", "stadium"]):
        return "special/event"
    return "unknown"


def load_vanilla_index() -> dict[str, Any]:
    resolution = resolve_vanilla_authoritative_index(TOOL_ROOT)
    if not resolution["actualPath"]:
        raise FileNotFoundError("vanilla_authoritative_index.json could not be resolved")
    return load_json(Path(resolution["actualPath"]))


def load_approved_lookup() -> dict[str, dict[int, list[dict[str, Any]]]]:
    """Load only approved entries into a compact sheet -> tile -> profile lookup."""
    lookup: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    if not APPROVED_DB_PATH.exists():
        return lookup
    data = load_json(APPROVED_DB_PATH)
    for entry in data:
        if not entry.get("approved"):
            continue
        idx = safe_int(entry.get("localTileId"))
        if idx is None:
            continue
        keys = {
            path_stem_key(entry.get("imageName")),
            path_stem_key(entry.get("tilesetName")),
            path_stem_key(entry.get("copiedImagePath")),
        }
        profile = {
            "candidateId": entry.get("candidateId"),
            "finalClass": entry.get("finalClass"),
            "finalPurpose": entry.get("finalPurpose"),
            "allowedLayers": entry.get("allowedLayers") or [],
            "collision": entry.get("collision", "unknown"),
            "approvalSource": entry.get("approvalSource"),
            "approvalConfidence": entry.get("approvalConfidence"),
        }
        for key in sorted(k for k in keys if k):
            lookup[key][idx].append(profile)
    return lookup


def tile_metadata(
    sheet_base: str,
    idx: int,
    vanilla_index: dict[str, Any],
    approved_lookup: dict[str, dict[int, list[dict[str, Any]]]],
) -> dict[str, Any]:
    sheet = vanilla_index.get("sheets", {}).get(base_key(sheet_base), {})
    vanilla = sheet.get(str(idx), {})
    props = vanilla.get("props", {}) if isinstance(vanilla, dict) else {}
    approved_profiles = approved_lookup.get(base_key(sheet_base), {}).get(idx, [])
    approved_classes = sorted({p.get("finalClass") for p in approved_profiles if p.get("finalClass")})
    collisions = sorted({p.get("collision") for p in approved_profiles if p.get("collision")})
    approved_layers = sorted({layer for p in approved_profiles for layer in p.get("allowedLayers", [])})
    return {
        "props": props,
        "vanillaLayers": vanilla.get("layers", {}) if isinstance(vanilla, dict) else {},
        "vanillaMapCount": vanilla.get("mapCount", 0) if isinstance(vanilla, dict) else 0,
        "approvedProfiles": approved_profiles[:6],
        "approvedClasses": approved_classes,
        "approvedCollision": collisions,
        "approvedLayers": approved_layers,
    }


def coarse_role_from_meta(meta: dict[str, Any], layer: str | None = None) -> str:
    props = {str(k).lower(): [str(v).lower() for v in vals] for k, vals in (meta.get("props") or {}).items()}
    approved = set(meta.get("approvedClasses") or [])
    if "Water" in (meta.get("props") or {}) or "water" in props:
        return "intrinsic_water"
    if approved & {"water_base", "water_transition"}:
        return "approved_water"
    if approved & {"ground_base", "floor_base", "path_base", "ground_transition", "floor_trim"}:
        return "approved_walkable_base"
    if approved & {"wall_front", "wall_top", "exterior_wall", "roof", "tree_canopy", "overlay"}:
        return "approved_overlay_or_structure"
    if approved & {"collision_blocker", "wall_side", "wall_corner"}:
        return "approved_blocker"
    if any("diggable" in k for k in props):
        return "intrinsic_diggable_ground"
    if any("type" == k and any(v in {"grass", "dirt", "stone", "wood", "sand"} for v in vals) for k, vals in props.items()):
        return "intrinsic_typed_ground"
    if layer == "Buildings":
        return "building_layer_structure_or_object"
    if layer == "Front":
        return "front_overlay_or_decoration"
    if layer == "AlwaysFront":
        return "alwaysfront_overlay"
    if layer == "Paths":
        return "technical_path_marker"
    if layer == "Back":
        return "back_base_unknown"
    return "unknown"


def collision_from_stack(layers_present: set[str], back_meta: dict[str, Any] | None = None) -> str:
    if back_meta and "Water" in (back_meta.get("props") or {}):
        return "blocked_or_special_water"
    if "Buildings" in layers_present:
        return "blocked_by_buildings"
    if layers_present & {"Back", "Front", "AlwaysFront", "Paths"}:
        return "collision_depends_on_back_and_buildings_empty"
    return "empty_or_out_of_bounds"


def classify_region_role(cardinal_present: dict[str, bool], diagonal_present: dict[str, bool]) -> str:
    n = cardinal_present["N"]
    e = cardinal_present["E"]
    s = cardinal_present["S"]
    w = cardinal_present["W"]
    count = sum(1 for v in cardinal_present.values() if v)
    if count == 4:
        return "interior_or_repeated_fill"
    if count == 0:
        return "isolated"
    if count == 1:
        return "cap_or_endpoint"
    if count == 2:
        if (n and s) or (e and w):
            return "line_segment"
        return "corner_or_turn"
    if count == 3:
        return "edge_or_t_junction"
    return "unknown"


def canonical_layer_name(name: str | None) -> str | None:
    if not name:
        return None
    clean = str(name).strip()
    lower = clean.lower().replace(" ", "")
    aliases = {
        "back": "Back",
        "buildings": "Buildings",
        "building": "Buildings",
        "front": "Front",
        "alwaysfront": "AlwaysFront",
        "always front": "AlwaysFront",
        "paths": "Paths",
        "path": "Paths",
    }
    return aliases.get(lower, clean)


def parse_vanilla_maps(
    vanilla_index: dict[str, Any],
    approved_lookup: dict[str, dict[int, list[dict[str, Any]]]],
) -> dict[str, Any]:
    maps: list[dict[str, Any]] = []
    layer_stats: dict[str, dict[str, Any]] = {
        layer: {
            "mapCount": 0,
            "totalCells": 0,
            "nonEmptyTiles": 0,
            "densitySamples": [],
            "tileCounts": Counter(),
            "sheetCounts": Counter(),
            "propertyCounts": Counter(),
            "approvedClassCounts": Counter(),
            "collisionCounts": Counter(),
            "roleCounts": Counter(),
            "categoryCounts": Counter(),
            "edgeTileCount": 0,
            "examples": [],
        }
        for layer in STANDARD_LAYERS
    }
    neighbor_stats: dict[str, dict[str, Any]] = {
        layer: {
            "totalNonEmptyObserved": 0,
            "occupancyMasks": Counter(),
            "regionRoles": Counter(),
            "sameTileCardinalCounts": Counter(),
            "neighborTilePairs": Counter(),
            "neighborApprovedClassPairs": Counter(),
            "examplesByMask": defaultdict(list),
            "tilePatternCounts": Counter(),
            "tilePatternExamples": defaultdict(list),
        }
        for layer in STANDARD_LAYERS
    }
    stack_counter: Counter = Counter()
    stack_category_counter: dict[str, Counter] = defaultdict(Counter)
    stack_combo_counter: dict[str, Counter] = defaultdict(Counter)
    stack_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tile_stack_counter: Counter = Counter()
    tile_stack_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tile_946_examples: list[dict[str, Any]] = []
    map_category_counter: Counter = Counter()
    parse_failures: list[dict[str, Any]] = []

    tbin_files = sorted(UNPACKED_BASEGAME.glob("*.tbin"))
    for path in tbin_files:
        map_name = path.stem
        category = infer_map_category(path.name)
        map_category_counter[category] += 1
        try:
            parsed = T.parse(path.read_bytes())
            if not parsed.get("ok"):
                raise ValueError(f"parser did not fully consume file ({parsed.get('trailingBytes')} trailing)")
        except Exception as exc:
            parse_failures.append({"map": path.name, "error": str(exc)})
            continue

        id_to_sheet = {ts["id"]: base_key(ts.get("imageSource")) for ts in parsed.get("tilesheets", [])}
        layer_records: dict[str, dict[str, Any]] = {}
        layer_counts: dict[str, dict[str, int]] = {}
        map_intrinsic_props: Counter = Counter()
        map_intrinsic_tile_count = 0
        map_width = 0
        map_height = 0

        for layer in parsed.get("layers", []):
            layer_name = canonical_layer_name(layer.get("id")) or layer.get("id")
            w, h = layer.get("layerSize", (0, 0))
            map_width = max(map_width, int(w or 0))
            map_height = max(map_height, int(h or 0))
            non_empty = len(layer.get("tiles", {}))
            layer_counts[layer_name] = {
                "width": int(w or 0),
                "height": int(h or 0),
                "totalCells": int((w or 0) * (h or 0)),
                "nonEmptyTiles": non_empty,
            }
            tiles_by_coord: dict[tuple[int, int], tuple[str, int]] = {}
            unique_tiles = set()
            intrinsic_here = 0
            property_counts_here: Counter = Counter()
            for (x, y), (sheet_id, idx) in layer.get("tiles", {}).items():
                sheet_base = id_to_sheet.get(sheet_id, base_key(sheet_id))
                idx = int(idx)
                tiles_by_coord[(x, y)] = (sheet_base, idx)
                key = tile_key(sheet_base, idx)
                unique_tiles.add(key)
                meta = tile_metadata(sheet_base, idx, vanilla_index, approved_lookup)
                if meta["props"]:
                    intrinsic_here += 1
                    map_intrinsic_tile_count += 1
                    for prop in meta["props"]:
                        map_intrinsic_props[prop] += 1
                        property_counts_here[prop] += 1
                if idx == 946:
                    add_example(tile_946_examples, {"map": path.name, "layer": layer_name, "sheet": sheet_base, "x": x, "y": y}, 40)
            layer_records[layer_name] = {
                "width": int(w or 0),
                "height": int(h or 0),
                "tiles": tiles_by_coord,
                "uniqueTiles": len(unique_tiles),
                "intrinsicTileCount": intrinsic_here,
                "propertyCounts": property_counts_here,
            }

        for layer_name in STANDARD_LAYERS:
            record = layer_records.get(layer_name)
            if not record:
                continue
            stats = layer_stats[layer_name]
            stats["mapCount"] += 1
            total_cells = record["width"] * record["height"]
            non_empty = len(record["tiles"])
            stats["totalCells"] += total_cells
            stats["nonEmptyTiles"] += non_empty
            density = non_empty / total_cells if total_cells else 0
            stats["densitySamples"].append(density)
            stats["categoryCounts"][category] += 1
            add_example(stats["examples"], {"map": path.name, "category": category, "density": round(density, 4)}, 10)
            for (x, y), (sheet_base, idx) in record["tiles"].items():
                key = tile_key(sheet_base, idx)
                meta = tile_metadata(sheet_base, idx, vanilla_index, approved_lookup)
                stats["tileCounts"][key] += 1
                stats["sheetCounts"][base_key(sheet_base)] += 1
                stats["roleCounts"][coarse_role_from_meta(meta, layer_name)] += 1
                for prop in meta["props"]:
                    stats["propertyCounts"][prop] += 1
                for approved_class in meta["approvedClasses"]:
                    stats["approvedClassCounts"][approved_class] += 1
                for collision in meta["approvedCollision"]:
                    stats["collisionCounts"][collision] += 1
                if x <= 1 or y <= 1 or x >= record["width"] - 2 or y >= record["height"] - 2:
                    stats["edgeTileCount"] += 1

            neighbors = neighbor_stats[layer_name]
            for (x, y), (sheet_base, idx) in record["tiles"].items():
                neighbors["totalNonEmptyObserved"] += 1
                key = tile_key(sheet_base, idx)
                cardinal = {
                    "N": (x, y - 1) in record["tiles"],
                    "E": (x + 1, y) in record["tiles"],
                    "S": (x, y + 1) in record["tiles"],
                    "W": (x - 1, y) in record["tiles"],
                }
                diagonal = {
                    "NE": (x + 1, y - 1) in record["tiles"],
                    "SE": (x + 1, y + 1) in record["tiles"],
                    "SW": (x - 1, y + 1) in record["tiles"],
                    "NW": (x - 1, y - 1) in record["tiles"],
                }
                mask = "".join(d for d in ["N", "E", "S", "W"] if cardinal[d]) or "none"
                diag_mask = "".join(d for d in ["NE", "SE", "SW", "NW"] if diagonal[d]) or "none"
                role = classify_region_role(cardinal, diagonal)
                same_count = 0
                for direction, (nx, ny) in {
                    "N": (x, y - 1),
                    "E": (x + 1, y),
                    "S": (x, y + 1),
                    "W": (x - 1, y),
                }.items():
                    neighbor_tile = record["tiles"].get((nx, ny))
                    if not neighbor_tile:
                        continue
                    neighbor_key = tile_key(neighbor_tile[0], neighbor_tile[1])
                    neighbors["neighborTilePairs"][f"{key}->{direction}:{neighbor_key}"] += 1
                    if neighbor_key == key:
                        same_count += 1
                    meta_a = tile_metadata(sheet_base, idx, vanilla_index, approved_lookup)
                    meta_b = tile_metadata(neighbor_tile[0], neighbor_tile[1], vanilla_index, approved_lookup)
                    class_a = (meta_a.get("approvedClasses") or [coarse_role_from_meta(meta_a, layer_name)])[0]
                    class_b = (meta_b.get("approvedClasses") or [coarse_role_from_meta(meta_b, layer_name)])[0]
                    neighbors["neighborApprovedClassPairs"][f"{class_a}->{direction}:{class_b}"] += 1
                full_mask = f"{mask}|diag={diag_mask}"
                neighbors["occupancyMasks"][full_mask] += 1
                neighbors["regionRoles"][role] += 1
                neighbors["sameTileCardinalCounts"][same_count] += 1
                add_example(
                    neighbors["examplesByMask"][full_mask],
                    {"map": path.name, "category": category, "layer": layer_name, "tile": key, "x": x, "y": y, "role": role},
                    4,
                )
                pattern_key = f"{key}|{full_mask}|{role}"
                neighbors["tilePatternCounts"][pattern_key] += 1
                add_example(
                    neighbors["tilePatternExamples"][pattern_key],
                    {"map": path.name, "x": x, "y": y, "layer": layer_name},
                    4,
                )

        stack_width = max((r["width"] for r in layer_records.values()), default=map_width)
        stack_height = max((r["height"] for r in layer_records.values()), default=map_height)
        for y in range(stack_height):
            for x in range(stack_width):
                stack_tiles: dict[str, str] = {}
                present: list[str] = []
                for layer_name in STANDARD_LAYERS:
                    record = layer_records.get(layer_name)
                    if not record:
                        continue
                    tile = record["tiles"].get((x, y))
                    if not tile:
                        continue
                    present.append(layer_name)
                    stack_tiles[layer_name] = tile_key(tile[0], tile[1])
                stack_id = "+".join(present) if present else "empty"
                stack_counter[stack_id] += 1
                stack_category_counter[stack_id][category] += 1
                if present:
                    combo_key = "|".join(f"{layer}={stack_tiles.get(layer, '0')}" for layer in STANDARD_LAYERS if layer in present)
                    stack_combo_counter[stack_id][combo_key] += 1
                    tile_stack_counter[combo_key] += 1
                    add_example(tile_stack_examples[combo_key], {"map": path.name, "category": category, "x": x, "y": y, "stack": stack_id}, 5)
                add_example(stack_examples[stack_id], {"map": path.name, "category": category, "x": x, "y": y, "tiles": stack_tiles}, 10)

        maps.append(
            {
                "mapName": path.stem,
                "fileName": path.name,
                "path": str(path),
                "mapCategory": category,
                "mapWidth": map_width,
                "mapHeight": map_height,
                "tilesheetsUsed": [
                    {
                        "id": ts.get("id"),
                        "imageSource": ts.get("imageSource"),
                        "sheetBase": base_key(ts.get("imageSource")),
                        "sheetSize": list(ts.get("sheetSize", [])),
                        "tileSize": list(ts.get("tileSize", [])),
                    }
                    for ts in parsed.get("tilesheets", [])
                ],
                "layerNames": [layer.get("id") for layer in parsed.get("layers", [])],
                "layerDimensions": {
                    layer.get("id"): {
                        "width": layer.get("layerSize", [None, None])[0],
                        "height": layer.get("layerSize", [None, None])[1],
                    }
                    for layer in parsed.get("layers", [])
                },
                "tileCountsByLayer": {k: v["totalCells"] for k, v in layer_counts.items()},
                "nonEmptyTilesByLayer": {k: v["nonEmptyTiles"] for k, v in layer_counts.items()},
                "tilesWithIntrinsicProperties": map_intrinsic_tile_count,
                "intrinsicProperties": counter_dict(map_intrinsic_props, 20),
                "parseStatus": "parsed",
            }
        )

    return {
        "generatedAt": now_iso(),
        "vanillaMapCount": len(tbin_files),
        "mapsParsed": len(maps),
        "parseFailures": parse_failures,
        "mapCategoryCounter": map_category_counter,
        "maps": maps,
        "layerStats": layer_stats,
        "neighborStats": neighbor_stats,
        "stackCounter": stack_counter,
        "stackCategoryCounter": stack_category_counter,
        "stackComboCounter": stack_combo_counter,
        "stackExamples": stack_examples,
        "tileStackCounter": tile_stack_counter,
        "tileStackExamples": tile_stack_examples,
        "tile946Examples": tile_946_examples,
    }


def serialize_layer_patterns(raw: dict[str, Any], vanilla_index: dict[str, Any], approved_lookup: dict[str, dict[int, list[dict[str, Any]]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    layer_patterns: dict[str, Any] = {
        "generatedAt": raw["generatedAt"],
        "source": "vanilla_tbin_maps",
        "mapsParsed": raw["mapsParsed"],
        "layers": {},
        "notes": [
            "Approved classes come only from tile_database_v1_human_approved.json.",
            "Intrinsic properties come only from vanilla @TileIndex@ metadata.",
            "Neighbor-derived roles are proposals/patterns, not final tile approvals.",
        ],
    }
    tile_usage: dict[str, Any] = {
        "generatedAt": raw["generatedAt"],
        "source": "vanilla_tbin_maps",
        "layers": {},
    }
    for layer_name, stats in raw["layerStats"].items():
        densities = stats["densitySamples"]
        density_avg = sum(densities) / len(densities) if densities else 0
        non_empty = stats["nonEmptyTiles"]
        total = stats["totalCells"]
        layer_patterns["layers"][layer_name] = {
            "mapCount": stats["mapCount"],
            "totalCells": total,
            "nonEmptyTiles": non_empty,
            "averageDensity": round(density_avg, 5),
            "emptyDensity": round(1 - density_avg, 5),
            "edgeTileFraction": round(stats["edgeTileCount"] / non_empty, 5) if non_empty else 0,
            "mostCommonTilesheets": top_counter(stats["sheetCounts"], 30),
            "dominantIntrinsicProperties": top_counter(stats["propertyCounts"], 30),
            "commonApprovedClasses": top_counter(stats["approvedClassCounts"], 30),
            "commonCollisionBehavior": top_counter(stats["collisionCounts"], 30),
            "coarseRolePatterns": top_counter(stats["roleCounts"], 30),
            "mapCategories": top_counter(stats["categoryCounts"], 20),
            "layerInterpretation": interpret_layer(layer_name, stats),
            "examples": stats["examples"],
        }
        entries = []
        for key, count in stats["tileCounts"].most_common(MAX_TILE_USAGE):
            sheet, idx = split_tile_key(key)
            meta = tile_metadata(sheet, idx if idx is not None else -1, vanilla_index, approved_lookup)
            entries.append(
                {
                    "tileKey": key,
                    "sheet": sheet,
                    "localTileId": idx,
                    "count": int(count),
                    "intrinsicProperties": meta["props"],
                    "approvedClasses": meta["approvedClasses"],
                    "approvedLayers": meta["approvedLayers"],
                    "approvedCollision": meta["approvedCollision"],
                    "coarseRole": coarse_role_from_meta(meta, layer_name),
                    "approvalBacked": bool(meta["approvedClasses"]),
                    "metadataBacked": bool(meta["props"]),
                }
            )
        tile_usage["layers"][layer_name] = {
            "totalObserved": int(non_empty),
            "topTiles": entries,
        }
    return layer_patterns, tile_usage


def interpret_layer(layer_name: str, stats: dict[str, Any]) -> dict[str, Any]:
    if layer_name == "Back":
        return {
            "usualMeaning": "ground/floor/water/base visual layer",
            "collisionExpectation": "walkable unless intrinsic water/special properties or Buildings blocks above",
            "generatorUse": "base terrain and floors",
        }
    if layer_name == "Buildings":
        return {
            "usualMeaning": "blocking structures, wall bodies, doors, furniture, structural boundaries",
            "collisionExpectation": "normally blocks movement unless a specific game rule overrides it",
            "generatorUse": "collision-bearing wall/body/object placement",
        }
    if layer_name == "Front":
        return {
            "usualMeaning": "front overlays, wall tops, signs, windows, upper furniture, decoration",
            "collisionExpectation": "drawn over base but should not be used as sole collision source",
            "generatorUse": "visual top/overlay paired with Back/Buildings",
        }
    if layer_name == "AlwaysFront":
        return {
            "usualMeaning": "over-player canopy, roof, treetop, tall overlay",
            "collisionExpectation": "draw order only; collision should come from Buildings or base properties",
            "generatorUse": "canopy/roof/overhead effects; tile 946 remains quarantined from collision roles",
        }
    if layer_name == "Paths":
        return {
            "usualMeaning": "technical path/route layer",
            "collisionExpectation": "technical route data, not final visual collision by itself",
            "generatorUse": "NPC/route/technical markers only",
        }
    return {"usualMeaning": "unknown", "collisionExpectation": "unknown", "generatorUse": "unknown"}


def serialize_neighbor_patterns(raw: dict[str, Any]) -> dict[str, Any]:
    out = {
        "generatedAt": raw["generatedAt"],
        "source": "vanilla_tbin_maps",
        "proposalOnly": True,
        "layers": {},
    }
    for layer_name, stats in raw["neighborStats"].items():
        top_masks = []
        for mask, count in stats["occupancyMasks"].most_common(80):
            top_masks.append(
                {
                    "mask": mask,
                    "count": int(count),
                    "examples": stats["examplesByMask"].get(mask, []),
                }
            )
        top_tile_patterns = []
        for pattern, count in stats["tilePatternCounts"].most_common(120):
            tile, mask, role = pattern.split("|", 2)
            top_tile_patterns.append(
                {
                    "tileKey": tile,
                    "neighborMask": mask,
                    "edgeCornerRole": role,
                    "count": int(count),
                    "examples": stats["tilePatternExamples"].get(pattern, []),
                    "classificationStatus": "pattern_only_not_approved",
                }
            )
        out["layers"][layer_name] = {
            "totalNonEmptyObserved": int(stats["totalNonEmptyObserved"]),
            "commonOccupancyMasks": top_masks,
            "regionRoleCounts": top_counter(stats["regionRoles"], 30),
            "sameTileCardinalCounts": top_counter(stats["sameTileCardinalCounts"], 10),
            "commonNeighborTilePairs": top_counter(stats["neighborTilePairs"], 80),
            "commonNeighborApprovedClassPairs": top_counter(stats["neighborApprovedClassPairs"], 80),
            "topTileNeighborPatterns": top_tile_patterns,
        }
    return out


def infer_stack_role(stack_id: str, combo_key: str | None = None, vanilla_index: dict[str, Any] | None = None) -> str:
    layers = set([] if stack_id == "empty" else stack_id.split("+"))
    if not layers:
        return "empty_stack"
    if layers == {"Back"}:
        return "base_ground_floor_or_water"
    if layers == {"Back", "Paths"}:
        return "technical_path_over_base"
    if "Buildings" in layers and "Front" in layers:
        return "blocked_structure_with_front_overlay"
    if "Buildings" in layers and "AlwaysFront" in layers:
        return "blocked_structure_with_overhead_overlay"
    if "Buildings" in layers:
        return "blocking_structure_or_object"
    if "AlwaysFront" in layers and "Buildings" not in layers:
        return "overhead_overlay_collision_from_lower_layers"
    if "Front" in layers and "Buildings" not in layers:
        return "front_decoration_or_overlay"
    if "Paths" in layers:
        return "technical_path_or_route_data"
    return "mixed_or_special_stack"


def serialize_stack_patterns(raw: dict[str, Any], vanilla_index: dict[str, Any], approved_lookup: dict[str, dict[int, list[dict[str, Any]]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    stack_out = {
        "generatedAt": raw["generatedAt"],
        "source": "vanilla_tbin_maps",
        "stackPatterns": [],
    }
    for stack_id, count in raw["stackCounter"].most_common(80):
        layers = [] if stack_id == "empty" else stack_id.split("+")
        combos = []
        for combo, combo_count in raw["stackComboCounter"].get(stack_id, Counter()).most_common(40):
            combos.append(
                {
                    "combination": combo,
                    "count": int(combo_count),
                    "inferredRole": infer_stack_role(stack_id, combo, vanilla_index),
                    "examples": raw["tileStackExamples"].get(combo, []),
                }
            )
        stack_out["stackPatterns"].append(
            {
                "stackId": stack_id,
                "layersPresent": layers,
                "count": int(count),
                "mapCategories": top_counter(raw["stackCategoryCounter"].get(stack_id, Counter()), 20),
                "mostCommonTileCombinations": combos,
                "inferredRole": infer_stack_role(stack_id),
                "collisionResultIfInferable": collision_from_stack(set(layers)),
                "examples": raw["stackExamples"].get(stack_id, []),
            }
        )

    tile_stack_roles = {
        "generatedAt": raw["generatedAt"],
        "source": "vanilla_tbin_maps",
        "topTileStackRolePatterns": [],
        "notes": "These are stack role patterns/proposals derived from vanilla placement. They are not tile approvals.",
    }
    for combo, count in raw["tileStackCounter"].most_common(200):
        present = [part.split("=", 1)[0] for part in combo.split("|") if "=" in part]
        stack_id = "+".join([layer for layer in STANDARD_LAYERS if layer in present])
        tiles = {}
        approved_classes = {}
        intrinsic_props = {}
        for part in combo.split("|"):
            if "=" not in part:
                continue
            layer, key = part.split("=", 1)
            tiles[layer] = key
            sheet, idx = split_tile_key(key)
            if idx is not None:
                meta = tile_metadata(sheet, idx, vanilla_index, approved_lookup)
                if meta["approvedClasses"]:
                    approved_classes[layer] = meta["approvedClasses"]
                if meta["props"]:
                    intrinsic_props[layer] = meta["props"]
        tile_stack_roles["topTileStackRolePatterns"].append(
            {
                "stackId": stack_id,
                "count": int(count),
                "tilesByLayer": tiles,
                "approvedClassesByLayer": approved_classes,
                "intrinsicPropertiesByLayer": intrinsic_props,
                "inferredRole": infer_stack_role(stack_id, combo, vanilla_index),
                "collisionResultIfInferable": collision_from_stack(set(present)),
                "examples": raw["tileStackExamples"].get(combo, []),
            }
        )
    return stack_out, tile_stack_roles


def make_grammar_rules(stack_patterns: dict[str, Any]) -> dict[str, Any]:
    counts = {entry["stackId"]: entry["count"] for entry in stack_patterns["stackPatterns"]}

    def examples(stack_id: str) -> list[dict[str, Any]]:
        for entry in stack_patterns["stackPatterns"]:
            if entry["stackId"] == stack_id:
                return entry.get("examples", [])[:5]
        return []

    rules = [
        {
            "ruleId": "walkable_ground",
            "ruleName": "walkable ground or floor",
            "layerRequirements": {"Back": "required", "Buildings": "empty", "Front": "empty_or_decorative", "AlwaysFront": "empty", "Paths": "optional_technical"},
            "allowedApprovedClasses": ["ground_base", "floor_base", "path_base", "ground_transition", "floor_trim"],
            "forbiddenClasses": ["collision_blocker", "wall_front", "wall_side"],
            "collisionExpectation": "walkable unless Back has Water=T or another special intrinsic property",
            "drawOrderExpectation": "Back provides the visible base; optional Paths is technical.",
            "validatorChecks": ["Back tile approved or intrinsic metadata-backed", "Buildings empty", "AlwaysFront not used for collision"],
            "examples": examples("Back") + examples("Back+Paths"),
            "confidence": 95 if counts.get("Back", 0) else 70,
            "source": "vanilla_pattern_learning",
        },
        {
            "ruleId": "blocking_structure",
            "ruleName": "blocking structure or object",
            "layerRequirements": {"Back": "required_or_strongly_preferred", "Buildings": "required", "Front": "optional", "AlwaysFront": "optional", "Paths": "optional"},
            "allowedApprovedClasses": ["collision_blocker", "exterior_wall", "wall_front", "wall_side", "furniture", "machine", "container"],
            "forbiddenClasses": ["overlay_only", "tree_canopy_without_buildings_profile"],
            "collisionExpectation": "blocked by Buildings layer",
            "drawOrderExpectation": "Buildings carries body/collision; Front/AlwaysFront may add top/overhead visuals.",
            "validatorChecks": ["Buildings profile approved for blocking", "Back beneath is valid", "tile 946 is not used as Buildings/blocker"],
            "examples": examples("Back+Buildings") + examples("Back+Buildings+Front"),
            "confidence": 90 if counts.get("Back+Buildings", 0) else 70,
            "source": "vanilla_pattern_learning",
        },
        {
            "ruleId": "wall_with_overhead_top",
            "ruleName": "wall or building with front/overhead top",
            "layerRequirements": {"Back": "required", "Buildings": "required", "Front": "required_or_common", "AlwaysFront": "optional"},
            "allowedApprovedClasses": ["exterior_wall", "wall_front", "wall_top", "roof", "window", "door", "sign"],
            "forbiddenClasses": ["unprofiled_canopy_as_blocker"],
            "collisionExpectation": "blocked by Buildings; Front/AlwaysFront are draw layers",
            "drawOrderExpectation": "Back base, Buildings body, Front top/face, AlwaysFront over-player cap if needed.",
            "validatorChecks": ["Buildings body has matching approved Front/AlwaysFront top when style requires it", "top tile allowed on Front/AlwaysFront"],
            "examples": examples("Back+Buildings+Front") + examples("Back+Buildings+Front+AlwaysFront"),
            "confidence": 88,
            "source": "vanilla_pattern_learning",
        },
        {
            "ruleId": "canopy_overlay",
            "ruleName": "canopy or roof overlay",
            "layerRequirements": {"Back": "required_or_common", "Buildings": "empty_or_trunk_body", "AlwaysFront": "required"},
            "allowedApprovedClasses": ["tree_canopy", "roof", "overlay", "exterior_decoration"],
            "forbiddenClasses": ["collision_blocker_without_buildings_profile"],
            "collisionExpectation": "AlwaysFront does not create collision; collision comes from Buildings or Back metadata.",
            "drawOrderExpectation": "AlwaysFront draws above player.",
            "validatorChecks": ["AlwaysFront tile has overlay profile", "no collision assigned to AlwaysFront profile", "tile 946 remains overlay-only until separately approved"],
            "examples": examples("Back+AlwaysFront") + examples("Back+Buildings+AlwaysFront"),
            "confidence": 85,
            "source": "vanilla_pattern_learning",
        },
        {
            "ruleId": "water",
            "ruleName": "water or special liquid base",
            "layerRequirements": {"Back": "required_with_Water_property", "Buildings": "usually_empty", "Front": "optional_edge_overlay", "AlwaysFront": "optional"},
            "allowedApprovedClasses": ["water_base", "water_transition"],
            "forbiddenClasses": ["walkable_ground_without_water_profile"],
            "collisionExpectation": "blocked_or_special unless explicit passability exists",
            "drawOrderExpectation": "Water is primarily Back-layer with optional edge/overlay decorations.",
            "validatorChecks": ["Water tile must carry Water=T or approved water profile", "water edge transitions must be approved before production output"],
            "examples": examples("Back"),
            "confidence": 90,
            "source": "vanilla_pattern_learning",
        },
        {
            "ruleId": "technical_path",
            "ruleName": "technical path or route data",
            "layerRequirements": {"Paths": "optional_or_required_by_map_logic", "Back": "usually_required"},
            "allowedApprovedClasses": ["path_base", "event_marker", "npc_marker", "warp_marker"],
            "forbiddenClasses": ["final_visual_only_on_paths"],
            "collisionExpectation": "technical route data, not visual collision",
            "drawOrderExpectation": "Paths should not be treated as main visual output unless a map specifically uses it that way.",
            "validatorChecks": ["Paths layer does not replace Back visual base", "entrance/exit path markers do not block routes"],
            "examples": examples("Back+Paths"),
            "confidence": 82,
            "source": "vanilla_pattern_learning",
        },
    ]
    return {
        "generatedAt": now_iso(),
        "source": "vanilla_pattern_learning",
        "rules": rules,
        "notes": [
            "Rules are grammar learned from vanilla placement and metadata.",
            "They do not approve unapproved custom tiles.",
            "Production output remains blocked where structural stylepack roles are marker-only.",
        ],
    }


def make_structure_patterns(stack_patterns: dict[str, Any], neighbor_patterns: dict[str, Any]) -> dict[str, Any]:
    def stack_examples(stack_id: str) -> list[dict[str, Any]]:
        for entry in stack_patterns["stackPatterns"]:
            if entry["stackId"] == stack_id:
                return entry.get("examples", [])[:6]
        return []

    specs = [
        ("exterior_ground_fields", "Exterior ground fields", ["town exterior", "forest exterior", "mountain exterior", "beach exterior"], "Back", "large repeated Back-layer regions", ["ground_base", "ground_transition"], ["transitionTiles"], True),
        ("dirt_grass_path_roads", "Dirt/grass/path roads", ["town exterior", "forest exterior", "farmhouse/interior"], "Back+Paths", "Back visual base with optional technical Paths", ["path_base", "ground_base"], ["pathTransitionTiles"], True),
        ("water_edges", "Water edges", ["beach exterior", "forest exterior", "town exterior"], "Back", "Back tiles with Water metadata next to non-water Back tiles", ["water_base", "water_transition"], ["waterEdgeTiles"], False),
        ("forest_tree_canopy_stacks", "Forest/tree/canopy stacks", ["forest exterior", "mountain exterior"], "Back+AlwaysFront", "Back ground with AlwaysFront canopy/top overlay", ["tree_canopy", "overlay"], ["canopyOverlayTiles", "shadowTiles"], False),
        ("house_exterior_walls_roofs", "House exterior walls and roofs", ["town exterior"], "Back+Buildings+Front", "Buildings body with Front/AlwaysFront upper visual layers", ["exterior_wall", "roof", "door", "window"], ["wallBodyTiles", "wallTopTiles", "cornerMatrices"], False),
        ("interior_walls", "Interior walls", ["farmhouse/interior", "shop/interior"], "Back+Buildings+Front", "Back floors with Buildings blockers and Front wall tops", ["floor_base", "wall_front", "wall_top"], ["wallBodyTiles", "wallTopTiles"], False),
        ("floors_and_rugs", "Floors and rugs", ["farmhouse/interior", "shop/interior"], "Back", "walkable Back floor/rug patterns", ["floor_base", "rug"], ["floor_trim"], True),
        ("counters_tables_furniture", "Counters/tables/furniture", ["farmhouse/interior", "shop/interior"], "Back+Buildings", "Buildings objects over Back floor", ["counter", "table", "chair", "furniture"], ["wallBodyTiles"], False),
        ("doors_thresholds", "Doors and thresholds", ["town exterior", "farmhouse/interior", "shop/interior"], "Back+Buildings+Front", "transition points combining floor, blocker/body, and overlay", ["door", "warp_marker"], ["door", "pathTransitionTiles"], False),
        ("cave_mine_floors", "Cave/mine floors", ["mine"], "Back", "Back base floors with clustered structure overlays", ["floor_base", "rock"], ["edgeMatrices", "wallBodyTiles"], True),
        ("mine_walls", "Mine walls", ["mine"], "Back+Buildings", "blocking cave walls with Back floor beneath", ["wall_front", "collision_blocker"], ["wallBodyTiles", "cornerMatrices"], False),
        ("mine_ladders_holes", "Mine ladders/holes", ["mine"], "Back+Buildings", "special floor transitions or ladder-like stacks", ["stairs", "warp_marker"], ["stairs", "event_marker"], False),
        ("festival_decoration_stacks", "Festival decoration stacks", ["festival"], "Back+Front", "seasonal decorations layered over normal bases", ["decoration", "overlay"], ["decorationTiles"], True),
    ]
    return {
        "generatedAt": now_iso(),
        "source": "vanilla_pattern_learning",
        "patterns": [
            {
                "patternId": pid,
                "name": name,
                "mapCategories": cats,
                "layerStackPattern": stack,
                "neighborPattern": neighbor,
                "exampleMaps": sorted({ex.get("map") for ex in stack_examples(stack) if ex.get("map")})[:8],
                "exampleCoordinates": stack_examples(stack),
                "requiredApprovedTileClasses": required,
                "unresolvedTileClasses": unresolved,
                "canUseForGenerator": can_use,
                "reason": (
                    "Usable for marker-only generator and production only where all required classes are approved."
                    if can_use
                    else "Blocked for production because structural/edge/corner/canopy classes remain unapproved."
                ),
            }
            for pid, name, cats, stack, neighbor, required, unresolved, can_use in specs
        ],
    }


def decode_tmx_data(data_node: ET.Element | None) -> list[int]:
    if data_node is None:
        return []
    encoding = data_node.get("encoding")
    compression = data_node.get("compression")
    text = "".join(data_node.itertext()).strip()
    if not text:
        return []
    if encoding == "csv":
        return [int(x) for x in re.split(r"[,\s]+", text) if x and re.match(r"^\d+$", x)]
    if encoding == "base64":
        raw = base64.b64decode(re.sub(r"\s+", "", text))
        if compression == "zlib":
            raw = zlib.decompress(raw)
        elif compression == "gzip":
            raw = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
        elif compression:
            raise ValueError(f"unsupported TMX compression {compression}")
        return list(struct.unpack("<" + "I" * (len(raw) // 4), raw))
    raise ValueError(f"unsupported TMX encoding {encoding}")


def resolve_gid(clean_gid: int, tilesets: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int | None]:
    if clean_gid <= 0:
        return None, None
    match = None
    for ts in sorted(tilesets, key=lambda item: int(item.get("firstgid") or 1)):
        if int(ts.get("firstgid") or 1) <= clean_gid:
            match = ts
        else:
            break
    if not match:
        return None, clean_gid
    return match, clean_gid - int(match.get("firstgid") or 1)


def parse_tmx_stack(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    width = safe_int(root.get("width"), 0) or 0
    height = safe_int(root.get("height"), 0) or 0
    tilesets = []
    for ts in root.findall("tileset"):
        image = ts.find("image")
        source = ts.get("source") or (image.get("source") if image is not None else ts.get("name"))
        tilesets.append(
            {
                "firstgid": safe_int(ts.get("firstgid"), 1) or 1,
                "name": ts.get("name") or path_stem_key(source),
                "image": image.get("source") if image is not None else source,
            }
        )
    layers = {}
    for layer in root.findall("layer"):
        name = canonical_layer_name(layer.get("name")) or layer.get("name")
        if name not in STANDARD_LAYERS:
            continue
        lw = safe_int(layer.get("width"), width) or width
        lh = safe_int(layer.get("height"), height) or height
        width = max(width, lw)
        height = max(height, lh)
        data = decode_tmx_data(layer.find("data"))
        tiles = {}
        for i, gid in enumerate(data):
            clean = gid & GID_MASK
            if clean == 0:
                continue
            ts, local = resolve_gid(clean, tilesets)
            sheet = base_key((ts or {}).get("image") or (ts or {}).get("name"))
            tiles[(i % lw, i // lw)] = (sheet, local if local is not None else clean)
        layers[name] = {"width": lw, "height": lh, "tiles": tiles}
    return {"width": width, "height": height, "layers": layers}


def parse_tmj_stack(path: Path) -> dict[str, Any]:
    data = load_json(path)
    width = safe_int(data.get("width"), 0) or 0
    height = safe_int(data.get("height"), 0) or 0
    tilesets = []
    for ts in data.get("tilesets", []):
        source = ts.get("source") or ts.get("image") or ts.get("name")
        tilesets.append(
            {
                "firstgid": safe_int(ts.get("firstgid"), 1) or 1,
                "name": ts.get("name") or path_stem_key(source),
                "image": ts.get("image") or source,
            }
        )
    layers = {}
    for layer in data.get("layers", []):
        if layer.get("type") != "tilelayer":
            continue
        name = canonical_layer_name(layer.get("name")) or layer.get("name")
        if name not in STANDARD_LAYERS:
            continue
        lw = safe_int(layer.get("width"), width) or width
        lh = safe_int(layer.get("height"), height) or height
        raw = layer.get("data") or []
        if not isinstance(raw, list):
            continue
        tiles = {}
        for i, gid in enumerate(raw):
            clean = int(gid) & GID_MASK
            if clean == 0:
                continue
            ts, local = resolve_gid(clean, tilesets)
            sheet = base_key((ts or {}).get("image") or (ts or {}).get("name"))
            tiles[(i % lw, i // lw)] = (sheet, local if local is not None else clean)
        layers[name] = {"width": lw, "height": lh, "tiles": tiles}
    return {"width": width, "height": height, "layers": layers}


def stack_stats_for_parsed_map(parsed: dict[str, Any]) -> tuple[Counter, dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
    width = parsed.get("width", 0) or max((layer["width"] for layer in parsed.get("layers", {}).values()), default=0)
    height = parsed.get("height", 0) or max((layer["height"] for layer in parsed.get("layers", {}).values()), default=0)
    layers = parsed.get("layers", {})
    stack_counts: Counter = Counter()
    non_empty_by_layer = {layer: len(layers.get(layer, {}).get("tiles", {})) for layer in STANDARD_LAYERS}
    unusual_examples: list[dict[str, Any]] = []
    tile_946: list[dict[str, Any]] = []
    for layer_name, layer in layers.items():
        for (x, y), (sheet, local) in layer.get("tiles", {}).items():
            if local == 946:
                add_example(tile_946, {"layer": layer_name, "sheet": sheet, "x": x, "y": y}, 20)
    for y in range(height):
        for x in range(width):
            present = []
            for layer_name in STANDARD_LAYERS:
                if (x, y) in layers.get(layer_name, {}).get("tiles", {}):
                    present.append(layer_name)
            stack_id = "+".join(present) if present else "empty"
            stack_counts[stack_id] += 1
            if ("Buildings" in present and "Back" not in present) or ("AlwaysFront" in present and "Back" not in present and "Buildings" not in present) or (present == ["Paths"]):
                add_example(unusual_examples, {"x": x, "y": y, "stackId": stack_id}, 20)
    return stack_counts, non_empty_by_layer, unusual_examples, tile_946


def compare_mod_maps(vanilla_stack_patterns: dict[str, Any], source_categories: set[str], output_name: str) -> dict[str, Any]:
    if not MAP_CATALOG_PATH.exists():
        return {"generatedAt": now_iso(), "error": "map_catalog.json not found", "mapsCompared": 0}
    vanilla_stack_ids = {entry["stackId"] for entry in vanilla_stack_patterns.get("stackPatterns", [])}
    catalog = load_json(MAP_CATALOG_PATH)
    maps = [m for m in catalog if m.get("sourceCategory") in source_categories and m.get("parseStatus") == "parsed"]
    aggregate_stacks: Counter = Counter()
    density_by_layer: dict[str, list[float]] = defaultdict(list)
    comparison_maps = []
    dangerous_findings = []
    tile_946_usage = []
    parse_failures = []
    source_mod_counter: Counter = Counter()
    for item in maps:
        path = Path(item.get("copiedPath", ""))
        if not path.exists():
            parse_failures.append({"mapId": item.get("mapId"), "path": str(path), "error": "copiedPath not found"})
            continue
        try:
            if item.get("mapFormat") == "tmx" or path.suffix.lower() == ".tmx":
                parsed = parse_tmx_stack(path)
            elif item.get("mapFormat") == "tmj" or path.suffix.lower() == ".tmj":
                parsed = parse_tmj_stack(path)
            else:
                continue
            stacks, non_empty_by_layer, unusual_examples, tile_946 = stack_stats_for_parsed_map(parsed)
        except Exception as exc:
            parse_failures.append({"mapId": item.get("mapId"), "path": str(path), "error": str(exc)})
            continue
        source_mod_counter[item.get("sourceMod", "unknown")] += 1
        aggregate_stacks.update(stacks)
        total_cells = max(1, (parsed.get("width", 0) or 0) * (parsed.get("height", 0) or 0))
        for layer_name, count in non_empty_by_layer.items():
            density_by_layer[layer_name].append(count / total_cells)
        unusual_stack_counts = {k: int(v) for k, v in stacks.items() if k not in vanilla_stack_ids}
        risk_notes = []
        if unusual_examples:
            risk_notes.append("contains layer stacks that vanilla grammar treats as risky or unusual")
        if tile_946:
            risk_notes.append("tile 946 appears and must remain profile-specific/quarantined from blocking roles")
            for ex in tile_946[:8]:
                tile_946_usage.append({"mapId": item.get("mapId"), "sourceMod": item.get("sourceMod"), **ex})
        if unusual_stack_counts or risk_notes:
            dangerous_findings.append(
                {
                    "mapId": item.get("mapId"),
                    "sourceCategory": item.get("sourceCategory"),
                    "sourceMod": item.get("sourceMod"),
                    "copiedPath": item.get("copiedPath"),
                    "unusualStackCounts": unusual_stack_counts,
                    "unusualExamples": unusual_examples,
                    "riskNotes": risk_notes,
                }
            )
        comparison_maps.append(
            {
                "mapId": item.get("mapId"),
                "sourceCategory": item.get("sourceCategory"),
                "sourceMod": item.get("sourceMod"),
                "mapWidth": parsed.get("width"),
                "mapHeight": parsed.get("height"),
                "layerDensity": {k: round(v / total_cells, 5) for k, v in non_empty_by_layer.items()},
                "topStackPatterns": top_counter(stacks, 20),
                "unusualStacksRelativeToVanilla": unusual_stack_counts,
                "tile946UsageExamples": tile_946,
            }
        )
    return {
        "generatedAt": now_iso(),
        "sourceCategories": sorted(source_categories),
        "mapsAvailable": len(maps),
        "mapsCompared": len(comparison_maps),
        "parseFailures": parse_failures[:40],
        "sourceMods": top_counter(source_mod_counter, 50),
        "aggregateLayerStackPatterns": top_counter(aggregate_stacks, 80),
        "layerDensityAverages": {
            layer: round(sum(values) / len(values), 5) if values else 0 for layer, values in density_by_layer.items()
        },
        "maps": comparison_maps[:500],
        "dangerousOrUnusualFindings": dangerous_findings[:200],
        "tile946Usage": tile_946_usage[:200],
        "notes": [
            "Comparison is grammar-level only; no tile approvals are created.",
            "Unusual does not always mean wrong. It means the stack deserves review before the generator copies the pattern.",
        ],
    }


def make_generator_rules(grammar: dict[str, Any]) -> dict[str, Any]:
    specs = [
        ("ground_open", "walkable_ground", "marker_ground", ["Back"], ["ground_base", "floor_base"], "walkable"),
        ("path", "technical_path", "marker_path", ["Back", "Paths"], ["path_base", "path_transition"], "walkable"),
        ("wall_body", "blocking_structure", "marker_wall_body", ["Back", "Buildings"], ["wall_body", "exterior_wall", "collision_blocker"], "blocked"),
        ("wall_top", "wall_with_overhead_top", "marker_wall_top", ["Front"], ["wall_top", "wall_front"], "blocked_by_buildings"),
        ("corner", "wall_with_overhead_top", "marker_corner", ["Buildings", "Front"], ["wall_corner", "wall_top"], "blocked_by_buildings"),
        ("edge", "wall_with_overhead_top", "marker_edge", ["Buildings", "Front"], ["wall_side", "wall_front"], "blocked_by_buildings"),
        ("terrain_transition", "walkable_ground", "marker_transition", ["Back"], ["ground_transition", "path_transition", "water_transition"], "depends_on_material"),
        ("canopy_overlay", "canopy_overlay", "marker_overlay", ["AlwaysFront"], ["tree_canopy", "overlay"], "overlay_only"),
        ("water", "water", "marker_water", ["Back"], ["water_base", "water_transition"], "water_blocked"),
        ("entrance_exit", "technical_path", "marker_entrance", ["Back", "Paths"], ["warp_marker", "path_base"], "walkable_required"),
        ("decoration_zone", "walkable_ground", "marker_decoration_zone", ["Front"], ["decoration", "grass_detail", "interior_decoration"], "decorative_front"),
    ]
    return {
        "generatedAt": now_iso(),
        "source": "vanilla_pattern_learning",
        "rules": [
            {
                "semanticMarkerInput": marker,
                "derivedFromGrammarRule": rule,
                "requiredLayers": layers,
                "allowedTileClasses": classes,
                "requiredApprovedTileClasses": classes,
                "fallbackMarkerBehavior": fallback,
                "collisionExpectation": collision,
                "validationRule": f"Use `{fallback}` unless all required classes are approved for {', '.join(layers)}.",
                "productionOutputAllowedNow": False,
                "reason": "Current stylepacks are marker-only for structural roles; production output remains gated.",
            }
            for marker, rule, fallback, layers, classes, collision in specs
        ],
        "tile946Policy": "Tile 946 may not satisfy wall_body, edge, corner, Buildings, blocker, or collision rules. It requires a separate overlay profile before any non-marker use.",
    }


def write_reports(
    raw: dict[str, Any],
    layer_patterns: dict[str, Any],
    stack_patterns: dict[str, Any],
    grammar: dict[str, Any],
    structure_patterns: dict[str, Any],
    moon_compare: dict[str, Any],
    ref_compare: dict[str, Any],
    generator_rules: dict[str, Any],
) -> None:
    def fmt_top(items: list[dict[str, Any]], limit: int = 5) -> str:
        if not items:
            return "none"
        return ", ".join(f"{item['key']} ({item['count']})" for item in items[:limit])

    top_stacks = stack_patterns["stackPatterns"][:12]
    vanilla_summary = [
        "# Vanilla Layer Pattern Summary",
        "",
        f"- Generated: {now_iso()}",
        f"- Vanilla `.tbin` maps found: {raw['vanillaMapCount']}",
        f"- Vanilla maps parsed: {raw['mapsParsed']}",
        f"- Parse failures: {len(raw['parseFailures'])}",
        "",
        "## Sources",
        "",
        "- Vanilla maps: `tools/tiled-map-assistant/mission_assets/unpacked_basegame/*.tbin` read-only",
        "- Vanilla metadata: `tools/tiled-map-assistant/review/auto_resolution/vanilla_authoritative_index.json`",
        "- Approved profiles: `tools/tiled-map-assistant/database/tile_database_v1_human_approved.json`",
        "- Map comparison catalog: `tools/tiled-map-assistant/database/map_catalog.json`",
        "- Stylepack safety state: `tools/tiled-map-assistant/stylepacks/`",
        "",
        "## Map Categories",
        "",
    ]
    for item in top_counter(raw["mapCategoryCounter"], 20):
        vanilla_summary.append(f"- {item['key']}: {item['count']}")
    vanilla_summary += ["", "## Layer Findings", ""]
    for layer_name, layer in layer_patterns["layers"].items():
        vanilla_summary += [
            f"### {layer_name}",
            "",
            f"- Non-empty tiles: {layer['nonEmptyTiles']}",
            f"- Average density: {layer['averageDensity']}",
            f"- Usual meaning: {layer['layerInterpretation']['usualMeaning']}",
            f"- Collision expectation: {layer['layerInterpretation']['collisionExpectation']}",
            f"- Top coarse roles: {fmt_top(layer['coarseRolePatterns'])}",
            f"- Top intrinsic properties: {fmt_top(layer['dominantIntrinsicProperties'])}",
            f"- Top approved classes: {fmt_top(layer['commonApprovedClasses'])}",
            "",
        ]
    vanilla_summary += [
        "## Most Common Layer Stacks",
        "",
    ]
    for entry in top_stacks:
        vanilla_summary.append(f"- `{entry['stackId']}`: {entry['count']} cells, role `{entry['inferredRole']}`")
    vanilla_summary += [
        "",
        "## Tile 946 Note",
        "",
        f"- Vanilla tile 946 observations captured: {len(raw['tile946Examples'])}",
        "- This mission preserves the existing quarantine: tile 946 is not approved as Buildings/wall/body/blocker.",
    ]
    write_text(REPORTS_ROOT / "vanilla_layer_pattern_summary.md", "\n".join(vanilla_summary))

    grammar_summary = [
        "# Layer Combination Grammar Summary",
        "",
        f"- Generated: {now_iso()}",
        f"- Grammar rules discovered/curated: {len(grammar['rules'])}",
        f"- Generator rules derived: {len(generator_rules['rules'])}",
        "",
        "## Discovered Grammar Rules",
        "",
    ]
    for rule in grammar["rules"]:
        grammar_summary += [
            f"### {rule['ruleId']}",
            "",
            f"- Name: {rule['ruleName']}",
            f"- Collision: {rule['collisionExpectation']}",
            f"- Confidence: {rule['confidence']}",
            f"- Validator checks: {', '.join(rule['validatorChecks'])}",
            "",
        ]
    blocked = [r for r in generator_rules["rules"] if not r["productionOutputAllowedNow"]]
    grammar_summary += [
        "## Output Readiness",
        "",
        f"- Rules ready for marker-only output: {len(generator_rules['rules'])}",
        f"- Rules ready for production output now: {len(generator_rules['rules']) - len(blocked)}",
        f"- Rules blocked by missing approved structural tiles: {len(blocked)}",
        "",
        "Production output remains blocked until stylepacks have approved structural roles for wall bodies, wall tops, corners, edges, transitions, canopy overlays, shadows, path transitions, and water edges.",
    ]
    write_text(REPORTS_ROOT / "layer_combination_grammar_summary.md", "\n".join(grammar_summary))

    moon_report = [
        "# Moonvillage Pattern Gap Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Moonvillage maps available: {moon_compare.get('mapsAvailable', 0)}",
        f"- Moonvillage maps compared: {moon_compare.get('mapsCompared', 0)}",
        f"- Parse failures: {len(moon_compare.get('parseFailures', []))}",
        f"- Dangerous or unusual findings recorded: {len(moon_compare.get('dangerousOrUnusualFindings', []))}",
        f"- Tile 946 usage examples recorded: {len(moon_compare.get('tile946Usage', []))}",
        "",
        "## Where Moonvillage Follows Vanilla Grammar",
        "",
        "- Common Back-only, Back+Buildings, Back+Front, and Back+Buildings+Front stacks can be compared directly to vanilla grammar.",
        "- Layer density and stack reports are now available for generator tuning.",
        "",
        "## Safe Differences",
        "",
        "- Custom tilesheets can use vanilla-like layer stacks without being visually identical to vanilla.",
        "- Unusual stacks are not automatically wrong; they are queued for review when they diverge from vanilla grammar.",
        "",
        "## Dangerous Differences",
        "",
        "- Any tile 946 use remains profile-specific and cannot be copied into wall/body/blocking generation.",
        "- Buildings without Back, AlwaysFront without supporting lower layers, and Paths-only stacks are review-needed layer grammar. Vanilla has some sparse/edge-case uses of these stacks, so they are not automatic map bugs, but the generator must not copy them blindly.",
        "",
        "## Stylepack Improvements Needed",
        "",
        "- Add approved wall body, wall top, edge, corner, transition, canopy overlay, shadow, path transition, and water edge profiles.",
        "- Keep marker fallback active until those structural profiles validate.",
    ]
    if moon_compare.get("dangerousOrUnusualFindings"):
        moon_report += ["", "## Example Findings", ""]
        for finding in moon_compare["dangerousOrUnusualFindings"][:12]:
            moon_report.append(f"- `{finding.get('mapId')}` from `{finding.get('sourceMod')}`: {', '.join(finding.get('riskNotes') or ['unusual stack usage'])}")
    write_text(REPORTS_ROOT / "moonvillage_pattern_gap_report.md", "\n".join(moon_report))

    next_steps = [
        "# Next Pattern Learning Steps",
        "",
        f"- Generated: {now_iso()}",
        "",
        "## Learn Next",
        "",
        "- Extract edge/corner matrices from high-confidence vanilla structures.",
        "- Separate interior wall grammar from exterior building grammar.",
        "- Learn water-edge transition orientation from vanilla maps with Water=T metadata.",
        "- Learn canopy overlays as non-collision profiles, keeping tile 946 quarantined from blockers.",
        "",
        "## Human Review Targets",
        "",
        "- wallBodyTiles",
        "- wallTopTiles",
        "- cornerMatrices",
        "- edgeMatrices",
        "- transitionTiles",
        "- canopyOverlayTiles",
        "- shadowTiles",
        "- pathTransitionTiles",
        "- waterEdgeTiles",
        "",
        "## Generator Use",
        "",
        "- Feed `generator_layer_rules_from_vanilla.json` into the marker generator first.",
        "- Extend validators to reject illegal stacks before TMX/TMJ output is allowed.",
        "- Keep production output disabled until stylepack structural roles resolve to approved profiles.",
    ]
    write_text(REPORTS_ROOT / "next_pattern_learning_steps.md", "\n".join(next_steps))

    validator_design = [
        "# Layer Grammar Validator Design",
        "",
        f"- Generated: {now_iso()}",
        "",
        "## Future Checks",
        "",
        "- Reject illegal Back/Buildings/Front/AlwaysFront combinations that do not appear in vanilla grammar or approved Moonvillage exceptions.",
        "- Reject unapproved wall stacks where Buildings has no approved blocking/body profile.",
        "- Reject AlwaysFront as a collision source; collision must come from Buildings or intrinsic Back metadata.",
        "- Warn on Buildings without valid Back beneath it unless explicitly approved as a special technical map.",
        "- Require Water=T or approved water profile for production water tiles.",
        "- Keep tile 946 quarantined from Buildings, wall body, blocker, collision, and wall base roles.",
        "- Check entrance and exit paths against blocking Buildings stacks.",
        "- Require style-defined top/front overlays for wall bodies when the stylepack says those are mandatory.",
        "- Reject stylepack tile roles that refer to unapproved final tile IDs while marker fallback is required.",
        "",
        "## Implementation Path",
        "",
        "1. Load `layer_combination_grammar.json` and `generator_layer_rules_from_vanilla.json`.",
        "2. Validate generated semantic stacks before tile resolution.",
        "3. Validate resolved tile stacks after tile resolution.",
        "4. Fail production output on any unresolved structural marker or unapproved tile profile.",
    ]
    write_text(REPORTS_ROOT / "layer_grammar_validator_design.md", "\n".join(validator_design))


def main() -> None:
    ensure_dirs()
    vanilla_index = load_vanilla_index()
    approved_lookup = load_approved_lookup()
    raw = parse_vanilla_maps(vanilla_index, approved_lookup)

    vanilla_map_index = {
        "generatedAt": raw["generatedAt"],
        "source": "unpacked_basegame_tbin",
        "mapsFound": raw["vanillaMapCount"],
        "mapsParsed": raw["mapsParsed"],
        "parseFailures": raw["parseFailures"],
        "mapCategories": counter_dict(raw["mapCategoryCounter"]),
        "maps": raw["maps"],
    }
    write_json(VANILLA_ROOT / "vanilla_map_pattern_index.json", vanilla_map_index)

    layer_patterns, tile_usage = serialize_layer_patterns(raw, vanilla_index, approved_lookup)
    write_json(VANILLA_ROOT / "vanilla_layer_patterns.json", layer_patterns)
    write_json(VANILLA_ROOT / "vanilla_layer_tile_usage.json", tile_usage)

    neighbor_patterns = serialize_neighbor_patterns(raw)
    write_json(VANILLA_ROOT / "vanilla_layer_neighbor_patterns.json", neighbor_patterns)

    stack_patterns, tile_stack_roles = serialize_stack_patterns(raw, vanilla_index, approved_lookup)
    write_json(VANILLA_ROOT / "vanilla_layer_stack_patterns.json", stack_patterns)
    write_json(COMBO_ROOT / "tile_stack_role_patterns.json", tile_stack_roles)

    grammar = make_grammar_rules(stack_patterns)
    write_json(COMBO_ROOT / "layer_combination_grammar.json", grammar)

    structure_patterns = make_structure_patterns(stack_patterns, neighbor_patterns)
    write_json(COMBO_ROOT / "common_structure_patterns.json", structure_patterns)

    moon_compare = compare_mod_maps(stack_patterns, {"moonvillage"}, "moonvillage")
    write_json(MOON_ROOT / "moonvillage_layer_pattern_comparison.json", moon_compare)

    ref_compare = compare_mod_maps(stack_patterns, {"reference_mods", "stardew_mods"}, "reference_mods")
    write_json(REFERENCE_ROOT / "reference_layer_pattern_comparison.json", ref_compare)

    generator_rules = make_generator_rules(grammar)
    write_json(COMBO_ROOT / "generator_layer_rules_from_vanilla.json", generator_rules)

    write_reports(raw, layer_patterns, stack_patterns, grammar, structure_patterns, moon_compare, ref_compare, generator_rules)

    print(f"Parsed vanilla maps: {raw['mapsParsed']}/{raw['vanillaMapCount']}")
    print(f"Layer grammar rules: {len(grammar['rules'])}")
    print(f"Moonvillage maps compared: {moon_compare.get('mapsCompared', 0)}")
    print(f"Reference/Stardew maps compared: {ref_compare.get('mapsCompared', 0)}")
    print("Pattern learning outputs written under tools/tiled-map-assistant/pattern_learning")


if __name__ == "__main__":
    main()
