#!/usr/bin/env python3
"""Freshly relearn mine/dungeon structural templates from vanilla and Moonvillage maps.

This script is read-only with respect to source maps. It writes a new database
under pattern_learning/mine_dungeon_fresh_relearn/ and reports/.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Optional

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
BASEGAME_MINE = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
MOON_DUNGEON = ROOT / "mission_assets" / "moonvillage" / "maps" / "MainMoonvillage-git" / "[CP] Moonvillage" / "assets" / "Maps" / "Dungeon"
MOON_TILE_DUNGEON = ROOT / "mission_assets" / "moonvillage" / "tilesheets" / "MainMoonvillage-git" / "[CP] Moonvillage" / "assets" / "Maps" / "Dungeon"
MOON_TILESET = ROOT / "mission_assets" / "moonvillage" / "tilesheets" / "MainMoonvillage-git" / "[CP] Moonvillage" / "assets" / "Maps" / "Tilesheet"

OUT_ROOT = ROOT / "pattern_learning" / "mine_dungeon_fresh_relearn"
RAW_DIR = OUT_ROOT / "raw_windows"
CLUSTER_DIR = OUT_ROOT / "clusters"
TEMPLATE_DIR = OUT_ROOT / "templates"
PREVIEW_DIR = OUT_ROOT / "previews"
REPORTS = ROOT / "reports"

LAYERS = ("Back", "Buildings", "Front", "AlwaysFront", "Paths")
WINDOW_SIZES = [(1, 3), (3, 1), (3, 3), (5, 5), (1, 5), (5, 1)]
STRUCTURAL_DESIGNS = [
    "deep_void", "floor_base", "straight_wall", "wall_top", "wall_body", "lower_face",
    "left_edge", "right_edge", "inner_corner", "outer_corner", "angled_wall_left",
    "angled_wall_right", "diagonal_transition", "ladder_opening", "shaft_opening",
    "shadow_strip", "floor_transition", "blocked_boundary",
]
DEEP_VOID_IDS = {77, 135}
LADDER_IDS = {67, 83, 99, 115}
SHAFT_IDS = {174, 175, 190, 191, 206, 207, 222, 223}
FRONT_SHADOW_IDS = {196, 197, 205, 206, 213, 214, 215, 216, 220, 221, 232}

sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for d in (RAW_DIR, CLUSTER_DIR, TEMPLATE_DIR, PREVIEW_DIR, REPORTS):
        d.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return str(path.resolve())


def resolve_image(image_source: str, map_path: Optional[Path] = None) -> Optional[Path]:
    names = [image_source]
    if not image_source.lower().endswith(".png"):
        names.append(image_source + ".png")
    roots = []
    if map_path:
        roots.append(map_path.parent)
    roots.extend([BASEGAME_MINE, MOON_TILE_DUNGEON, MOON_TILESET, ROOT / "mission_assets" / "unpacked_basegame"])
    for name in names:
        for root in roots:
            cand = root / name
            if cand.exists():
                return cand
    return None


def image_info(image_path: Optional[Path], columns: Optional[int] = None) -> dict[str, Any]:
    if not image_path or not image_path.exists():
        return {"imageResolved": False}
    try:
        img = Image.open(image_path)
        cols = columns or max(1, img.width // 16)
        rows = max(1, img.height // 16)
        return {
            "imageResolved": True,
            "imagePath": str(image_path.resolve()),
            "widthPx": img.width,
            "heightPx": img.height,
            "columns": cols,
            "rows": rows,
            "tileCount": cols * rows,
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        }
    except Exception as exc:
        return {"imageResolved": False, "error": str(exc)}


def parse_tmx(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    width = int(root.attrib["width"])
    height = int(root.attrib["height"])
    tilesets = []
    for ts in root.findall("tileset"):
        image = ts.find("image")
        source = image.attrib.get("source", "") if image is not None else ""
        img_path = resolve_image(source, path)
        columns = int(ts.attrib.get("columns", "0") or "0")
        tilecount = int(ts.attrib.get("tilecount", "0") or "0")
        tilesets.append({
            "firstgid": int(ts.attrib["firstgid"]),
            "id": ts.attrib.get("name", source or f"firstgid_{ts.attrib['firstgid']}"),
            "name": ts.attrib.get("name", ""),
            "imageSource": source,
            "tilecount": tilecount,
            "columns": columns,
            "tilewidth": int(ts.attrib.get("tilewidth", "16")),
            "tileheight": int(ts.attrib.get("tileheight", "16")),
            "imageInfo": image_info(img_path, columns or None),
        })
    tilesets = sorted(tilesets, key=lambda t: t["firstgid"])

    def gid_to_tile(gid: int) -> Optional[tuple[str, int]]:
        if gid <= 0:
            return None
        active = None
        for ts in tilesets:
            if gid >= ts["firstgid"]:
                active = ts
            else:
                break
        if active is None:
            return None
        return active["id"], gid - active["firstgid"]

    layers = {}
    for layer in root.findall("layer"):
        name = layer.attrib["name"]
        data = layer.find("data")
        if data is None or data.attrib.get("encoding") != "csv":
            continue
        nums = []
        for row in csv.reader(StringIO((data.text or "").strip())):
            nums.extend(int(v) for v in row if v.strip())
        tiles = {}
        for y in range(height):
            for x in range(width):
                idx = y * width + x
                if idx < len(nums):
                    val = gid_to_tile(nums[idx])
                    if val is not None:
                        tiles[(x, y)] = val
        layers[name] = {"id": name, "layerSize": (width, height), "tiles": tiles, "tileProperties": {}}
    return {
        "path": path,
        "category": "moonvillage_dungeon",
        "fileType": ".tmx",
        "width": width,
        "height": height,
        "layers": layers,
        "tilesheets": tilesets,
        "tilesheetById": {ts["id"]: ts for ts in tilesets},
        "mapProperties": {},
        "parsed": True,
    }


def parse_tbin(path: Path) -> dict[str, Any]:
    mp = tbin_reader.parse(path.read_bytes())
    layers = {l["id"]: l for l in mp.get("layers", [])}
    back = layers.get("Back") or next(iter(layers.values()))
    width, height = back["layerSize"]
    tilesets = []
    for ts in mp.get("tilesheets", []):
        img_path = resolve_image(ts.get("imageSource", ""), path)
        cols, rows = ts.get("sheetSize", (0, 0))
        tilesets.append({
            "firstgid": None,
            "id": ts["id"],
            "name": ts["id"],
            "imageSource": ts.get("imageSource", ""),
            "tilecount": int(cols) * int(rows),
            "columns": int(cols),
            "rows": int(rows),
            "tilewidth": ts.get("tileSize", (16, 16))[0],
            "tileheight": ts.get("tileSize", (16, 16))[1],
            "imageInfo": image_info(img_path, int(cols) or None),
        })
    return {
        "path": path,
        "category": "vanilla_mine",
        "fileType": ".tbin",
        "width": width,
        "height": height,
        "layers": layers,
        "tilesheets": tilesets,
        "tilesheetById": {ts["id"]: ts for ts in tilesets},
        "mapProperties": mp.get("properties", {}),
        "parsed": True,
        "ok": mp.get("ok", False),
    }


def source_files() -> list[Path]:
    files: list[Path] = []
    if BASEGAME_MINE.exists():
        files.extend(sorted(BASEGAME_MINE.glob("*.tbin"), key=lambda p: p.name))
    if MOON_DUNGEON.exists():
        files.extend(sorted(MOON_DUNGEON.glob("*.tmx"), key=lambda p: p.name))
    return files


def parse_source(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".tbin":
            return parse_tbin(path)
        if path.suffix.lower() == ".tmx":
            return parse_tmx(path)
        raise ValueError(f"unsupported type {path.suffix}")
    except Exception as exc:
        return {
            "path": path,
            "category": "vanilla_mine" if str(path).startswith(str(BASEGAME_MINE)) else "moonvillage_dungeon",
            "fileType": path.suffix.lower(),
            "parsed": False,
            "error": str(exc),
            "riskFlags": ["parse_failed"],
        }


def is_mine_compatible_tilesheet(src: dict[str, Any], sheet_id: str) -> bool:
    ts = src.get("tilesheetById", {}).get(sheet_id, {})
    hay = " ".join([sheet_id, ts.get("name", ""), ts.get("imageSource", "")]).lower()
    return "mine" in hay or "dungeon" in hay or "volcano" in hay or "shaft" in hay


def get_tile(src: dict[str, Any], layer: str, x: int, y: int) -> Optional[tuple[str, int]]:
    ly = src.get("layers", {}).get(layer)
    if not ly:
        return None
    val = ly.get("tiles", {}).get((x, y))
    if val is None:
        return None
    if not is_mine_compatible_tilesheet(src, val[0]):
        return None
    return val


def tile_id(src: dict[str, Any], layer: str, x: int, y: int) -> Optional[int]:
    val = get_tile(src, layer, x, y)
    return None if val is None else int(val[1])


def has(src: dict[str, Any], layer: str, x: int, y: int) -> bool:
    return get_tile(src, layer, x, y) is not None


def is_deep_void(src: dict[str, Any], x: int, y: int) -> bool:
    return tile_id(src, "Back", x, y) in DEEP_VOID_IDS or tile_id(src, "Buildings", x, y) in DEEP_VOID_IDS


def is_wall(src: dict[str, Any], x: int, y: int) -> bool:
    b = get_tile(src, "Buildings", x, y)
    if b is None:
        return False
    return int(b[1]) not in DEEP_VOID_IDS


def is_floor(src: dict[str, Any], x: int, y: int) -> bool:
    return 0 <= x < src["width"] and 0 <= y < src["height"] and has(src, "Back", x, y) and not is_wall(src, x, y) and not is_deep_void(src, x, y)


def neighbors8(src: dict[str, Any], x: int, y: int) -> dict[str, bool]:
    return {
        "N": is_floor(src, x, y - 1), "NE": is_floor(src, x + 1, y - 1),
        "E": is_floor(src, x + 1, y), "SE": is_floor(src, x + 1, y + 1),
        "S": is_floor(src, x, y + 1), "SW": is_floor(src, x - 1, y + 1),
        "W": is_floor(src, x - 1, y), "NW": is_floor(src, x - 1, y - 1),
    }


def role_guess(src: dict[str, Any], x: int, y: int) -> tuple[str, str]:
    b = tile_id(src, "Buildings", x, y)
    f = tile_id(src, "Front", x, y)
    back = tile_id(src, "Back", x, y)
    n = neighbors8(src, x, y)
    card = {d for d in ("N", "E", "S", "W") if n[d]}
    diag = {d for d in ("NE", "SE", "SW", "NW") if n[d]}
    if b in LADDER_IDS:
        return "ladder_opening", "ladder_opening"
    if b in SHAFT_IDS:
        return "shaft_opening", "shaft_opening"
    if b in DEEP_VOID_IDS or (back in DEEP_VOID_IDS and not card and not diag):
        return "deep_void_fill", "deep_void"
    if is_floor(src, x, y):
        if any(is_wall(src, x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            return "floor_to_wall_transition", "floor_transition"
        return "floor_base", "floor_base"
    if f in FRONT_SHADOW_IDS and not is_wall(src, x, y):
        return "shadow_under_wall", "shadow_strip"
    if card == {"S"}:
        return "lower_face_3_tile_stack", "lower_face"
    if "S" in card and ("E" in card or "W" in card):
        return ("lower_right_inner_corner" if "W" in card else "lower_left_inner_corner"), "inner_corner"
    if "N" in card and ("E" in card or "W" in card):
        return ("upper_right_inner_corner" if "W" in card else "upper_left_inner_corner"), "inner_corner"
    if not card and diag:
        d = sorted(diag)[0]
        return {
            "SE": "upper_left_outer_corner", "SW": "upper_right_outer_corner",
            "NE": "lower_left_outer_corner", "NW": "lower_right_outer_corner",
        }[d], "outer_corner"
    if card == {"E"}:
        return "left_wall_edge", "left_edge"
    if card == {"W"}:
        return "right_wall_edge", "right_edge"
    if card == {"N"}:
        return "wall_body", "wall_body"
    if len(diag) >= 2 and not card:
        return "diagonal_wall_transition", "diagonal_transition"
    if is_wall(src, x, y):
        return "wall_top" if not n["N"] and not n["S"] else "blocked_boundary", "wall_top"
    return "unclassified", "unknown"


def cell_stack(src: dict[str, Any], x: int, y: int) -> dict[str, Any]:
    layers = {}
    for layer in LAYERS:
        val = get_tile(src, layer, x, y)
        if val is not None:
            layers[layer] = {"tilesheetId": val[0], "localTileId": int(val[1])}
    return layers


def extract_window(src: dict[str, Any], x: int, y: int, w: int, h: int, role: str, design: str) -> Optional[dict[str, Any]]:
    ax, ay = w // 2, h // 2
    x0, y0 = x - ax, y - ay
    if x0 < 0 or y0 < 0 or x0 + w > src["width"] or y0 + h > src["height"]:
        return None
    cells = []
    wall_mask = []
    floor_mask = []
    void_mask = []
    for dy in range(h):
        for dx in range(w):
            sx, sy = x0 + dx, y0 + dy
            stack = cell_stack(src, sx, sy)
            cells.append({"dx": dx - ax, "dy": dy - ay, "stack": stack})
            wall_mask.append(bool(is_wall(src, sx, sy)))
            floor_mask.append(bool(is_floor(src, sx, sy)))
            void_mask.append(bool(is_deep_void(src, sx, sy) or not stack))
    layers_used = sorted({layer for c in cells for layer in c["stack"]})
    if not layers_used:
        return None
    tile_ids_by_layer: dict[str, list[int]] = {}
    for layer in LAYERS:
        vals = sorted({c["stack"][layer]["localTileId"] for c in cells if layer in c["stack"]})
        if vals:
            tile_ids_by_layer[layer] = vals
    signature_payload = {
        "size": [w, h],
        "role": role,
        "design": design,
        "cells": cells,
        "wallMask": wall_mask,
        "floorMask": floor_mask,
        "voidMask": void_mask,
    }
    signature = hashlib.sha1(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "signatureId": f"sig_{signature[:16]}",
        "sourceMap": src["path"].name,
        "sourcePath": str(src["path"].resolve()),
        "sourceCategory": src["category"],
        "sourceCoordinate": {"x": x, "y": y},
        "width": w,
        "height": h,
        "size": f"{w}x{h}",
        "anchor": {"x": ax, "y": ay},
        "roleGuess": role,
        "structuralDesign": design,
        "orientation": "vertical" if h > w else ("horizontal" if w > h else "square"),
        "layersUsed": layers_used,
        "tileIdsByLayer": tile_ids_by_layer,
        "cells": cells,
        "wallMask": wall_mask,
        "floorMask": floor_mask,
        "voidMask": void_mask,
        "neighborContext": neighbors8(src, x, y),
        "tilesheets": sorted({v["tilesheetId"] for c in cells for v in c["stack"].values()}),
    }


def build_inventory(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory = []
    for src in sources:
        if not src.get("parsed"):
            inventory.append({
                "path": str(src["path"].resolve()),
                "mapName": src["path"].name,
                "sourceCategory": src["category"],
                "fileType": src["fileType"],
                "canBeParsed": False,
                "safeToLearnFrom": False,
                "riskFlags": src.get("riskFlags", ["parse_failed"]),
                "error": src.get("error", ""),
            })
            continue
        risk = []
        if not {"Back", "Buildings"} <= set(src["layers"]):
            risk.append("missing_expected_layers")
        if not src["tilesheets"]:
            risk.append("missing_tilesheets")
        inventory.append({
            "path": str(src["path"].resolve()),
            "mapName": src["path"].name,
            "sourceCategory": src["category"],
            "fileType": src["fileType"],
            "mapSize": {"width": src["width"], "height": src["height"]},
            "layersPresent": sorted(src["layers"].keys()),
            "tilesheetsUsed": [
                {
                    "tilesheetId": ts["id"],
                    "tilesheetName": ts.get("name", ts["id"]),
                    "imageSource": ts.get("imageSource", ""),
                    "columns": ts.get("columns"),
                    "rows": ts.get("rows") or (math.ceil((ts.get("tilecount") or 0) / max(1, ts.get("columns") or 1))),
                    "tileCount": ts.get("tilecount"),
                    "tileWidth": ts.get("tilewidth"),
                    "tileHeight": ts.get("tileheight"),
                    "imageInfo": ts.get("imageInfo", {}),
                }
                for ts in src["tilesheets"]
            ],
            "canBeParsed": True,
            "safeToLearnFrom": not risk,
            "riskFlags": risk,
        })
    return inventory


def compatibility_report(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sheet_paths: dict[str, Path] = {}
    for root in (BASEGAME_MINE, MOON_TILE_DUNGEON, MOON_TILESET):
        if root.exists():
            for p in root.glob("*.png"):
                if "mine" in p.name.lower() or "dungeon" in p.name.lower() or p.name.lower() == "volcano_dungeon.png":
                    sheet_paths[str(p.resolve()).lower()] = p
    rows = []
    vanilla = BASEGAME_MINE / "mine.png"
    vanilla_info = image_info(vanilla)
    for path in sorted(sheet_paths.values(), key=lambda p: str(p)):
        info = image_info(path)
        aligns = (
            info.get("widthPx") == vanilla_info.get("widthPx")
            and info.get("heightPx") == vanilla_info.get("heightPx")
            and info.get("columns") == vanilla_info.get("columns")
            and info.get("tileCount") == vanilla_info.get("tileCount")
        )
        rows.append({
            "tilesheetName": path.stem,
            "imageSource": str(path.resolve()),
            "columns": info.get("columns"),
            "rows": info.get("rows"),
            "tileCount": info.get("tileCount"),
            "sameLayoutAsVanillaMine": bool(aligns),
            "visualPaletteDiffers": info.get("sha256") != vanilla_info.get("sha256"),
            "mismatchedTileIds": [] if aligns else ["layout_or_dimension_mismatch"],
            "safeToTransferStructuralTemplateAcrossSheets": bool(aligns),
            "notes": "ID layout matches vanilla mine.png; structural IDs can transfer by local ID." if aligns else "Do not transfer local-ID templates without conversion.",
        })
    return rows


def extract_windows(sources: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    role_counts: Counter[str] = Counter()
    total = 0
    for src in sources:
        if not src.get("parsed") or not src.get("layers"):
            continue
        per_source_role: Counter[str] = Counter()
        for y in range(src["height"]):
            for x in range(src["width"]):
                role, design = role_guess(src, x, y)
                if role == "unclassified":
                    continue
                near_structure = any(
                    is_wall(src, x + dx, y + dy) or is_floor(src, x + dx, y + dy)
                    for dx in range(-2, 3)
                    for dy in range(-2, 3)
                    if dx or dy
                )
                # Open floors and far deep void dominate real maps and drown out
                # the structural grammar. Keep deterministic representative
                # samples, but mine every wall/boundary/opening cell.
                if role == "floor_base" and (x * 31 + y * 17 + len(src["path"].name)) % 89 != 0:
                    continue
                if role == "deep_void_fill" and (not near_structure or (x * 19 + y * 23) % 61 != 0):
                    continue
                limit = 12 if role in {"floor_base", "deep_void_fill"} else 70
                if per_source_role[role] >= limit:
                    continue
                per_source_role[role] += 1
                for w, h in WINDOW_SIZES:
                    win = extract_window(src, x, y, w, h, role, design)
                    if not win:
                        continue
                    sid = win["signatureId"]
                    counts[sid] += 1
                    role_counts[f"{role}:{w}x{h}"] += 1
                    total += 1
                    if sid not in examples:
                        examples[sid] = win
                    elif len(examples[sid].setdefault("additionalExamples", [])) < 5:
                        examples[sid]["additionalExamples"].append({
                            "sourceMap": src["path"].name,
                            "sourceCategory": src["category"],
                            "sourceCoordinate": {"x": x, "y": y},
                        })
    windows = []
    for sid, count in counts.most_common():
        ex = examples[sid]
        ex["occurrenceCount"] = int(count)
        windows.append(ex)
    retained: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ex in windows[:4000]:
        retained.append(ex)
        seen.add(ex["signatureId"])
    per_role_size: Counter[str] = Counter()
    for ex in windows:
        key = f"{ex['roleGuess']}:{ex['size']}"
        if per_role_size[key] >= 25 or ex["signatureId"] in seen:
            continue
        retained.append(ex)
        seen.add(ex["signatureId"])
        per_role_size[key] += 1
    return {
        "generatedAt": now_iso(),
        "windowSizesScanned": [f"{w}x{h}" for w, h in WINDOW_SIZES],
        "totalWindowOccurrences": total,
        "uniqueSignatures": len(windows),
        "retainedSignatures": len(retained),
        "retentionPolicy": "Top 4000 repeated signatures plus up to 25 representative signatures per role/size; aggregate counts preserve full scan size.",
        "roleSizeCounts": dict(sorted(role_counts.items())),
        "windows": retained,
    }


def build_signatures(raw: dict[str, Any]) -> dict[str, Any]:
    signatures = []
    for w in raw["windows"]:
        signatures.append({
            "signatureId": w["signatureId"],
            "role": w["roleGuess"],
            "structuralDesign": w["structuralDesign"],
            "size": w["size"],
            "orientation": w["orientation"],
            "anchor": w["anchor"],
            "layerStack": w["cells"],
            "tileIdsByLayer": w["tileIdsByLayer"],
            "tilesheets": w["tilesheets"],
            "wallMask": w["wallMask"],
            "floorMask": w["floorMask"],
            "voidMask": w["voidMask"],
            "neighborContext": w["neighborContext"],
            "sourceEvidence": [{
                "sourceMap": w["sourceMap"],
                "sourceCategory": w["sourceCategory"],
                "sourceCoordinate": w["sourceCoordinate"],
            }] + w.get("additionalExamples", []),
            "occurrenceCount": w["occurrenceCount"],
        })
    return {"generatedAt": now_iso(), "signatures": signatures}


def family_for_role(role: str, design: str, signatures: list[dict[str, Any]]) -> dict[str, Any]:
    tile_by_layer: dict[str, set[int]] = defaultdict(set)
    examples = []
    frequency = 0
    compatible_sheets = set()
    for sig in signatures:
        if sig["role"] != role and sig["structuralDesign"] != design:
            continue
        frequency += sig["occurrenceCount"]
        compatible_sheets.update(sig.get("tilesheets", []))
        for layer, ids in sig.get("tileIdsByLayer", {}).items():
            tile_by_layer[layer].update(ids)
        for ev in sig["sourceEvidence"][:3]:
            if len(examples) < 8:
                examples.append(ev)
    all_ids = sorted({v for vals in tile_by_layer.values() for v in vals})
    required_grid = "variable"
    if role == "lower_face_3_tile_stack":
        required_grid = "1x3"
    elif "corner" in role:
        required_grid = "3x3"
    elif role in {"wall_top", "wall_body", "shadow_under_wall", "floor_to_wall_transition"}:
        required_grid = "3x1"
    elif role in {"ladder_opening", "shaft_opening"}:
        required_grid = "5x5"
    confidence = min(95, 35 + int(math.log10(max(1, frequency)) * 20))
    return {
        "familyId": f"fam_{design}_{role}",
        "familyName": role.replace("_", " ").title(),
        "structuralDesign": design,
        "sourceTilesheet": "mine-compatible local ID layout",
        "compatibleTilesheets": sorted(compatible_sheets),
        "tileIds": all_ids,
        "tileIdsByLayer": {layer: sorted(vals) for layer, vals in sorted(tile_by_layer.items())},
        "requiredOrder": "preserve relative grid/layer order from source signature",
        "requiredGrid": required_grid,
        "anchorTileId": all_ids[0] if all_ids else None,
        "neighborRequirements": "see template neighborRules; do not place family without matching complete template",
        "validRotations": ["none"] if design in {"deep_void", "floor_base", "ladder_opening", "shaft_opening"} else ["N", "E", "S", "W", "NE", "SE", "SW", "NW"],
        "invalidRotations": [],
        "layerStack": "multi-layer stack preserved in templates",
        "collisionMeaning": "blocked where Buildings non-void tiles exist; Front is decorative; Back is floor/support",
        "exampleSourceMaps": sorted({e["sourceMap"] for e in examples}),
        "exampleSourceCoordinates": [e["sourceCoordinate"] for e in examples],
        "frequency": frequency,
        "confidence": confidence,
        "notes": "Learned from repeated complete windows. Tile IDs are not approved as loose role-list placements.",
    }


def build_families(signatures_doc: dict[str, Any]) -> dict[str, Any]:
    signatures = signatures_doc["signatures"]
    keys = sorted({(s["role"], s["structuralDesign"]) for s in signatures if s["structuralDesign"] != "unknown"})
    families = [family_for_role(role, design, signatures) for role, design in keys]
    families = [f for f in families if f["frequency"] > 0 and f["tileIds"]]
    return {"generatedAt": now_iso(), "families": families}


def cluster_id(role: str, size: str, sig_id: str) -> str:
    return f"cluster_{role}_{size}_{sig_id[-8:]}"


def build_clusters(signatures_doc: dict[str, Any], families_doc: dict[str, Any]) -> dict[str, Any]:
    family_by_design_role = {(f["structuralDesign"], f["familyId"].split(f"fam_{f['structuralDesign']}_", 1)[-1]): f for f in families_doc["families"]}
    clusters = []
    for sig in signatures_doc["signatures"]:
        if sig["occurrenceCount"] < 2:
            continue
        role = sig["role"]
        design = sig["structuralDesign"]
        fam = family_by_design_role.get((design, role))
        vanilla_count = sum(1 for e in sig["sourceEvidence"] if e.get("sourceCategory") == "vanilla_mine")
        moon_count = sum(1 for e in sig["sourceEvidence"] if e.get("sourceCategory") == "moonvillage_dungeon")
        recommended = "generator_template" if sig["occurrenceCount"] >= 3 and role != "unclassified" else "manual_review"
        if sig["size"] == "1x1":
            recommended = "reject"
        clusters.append({
            "clusterId": cluster_id(role, sig["size"], sig["signatureId"]),
            "role": role,
            "tileIdFamilyId": fam["familyId"] if fam else None,
            "occurrenceCount": sig["occurrenceCount"],
            "sourceMaps": sorted({e["sourceMap"] for e in sig["sourceEvidence"]}),
            "vanillaCount": vanilla_count,
            "moonvillageCustomCount": moon_count,
            "mostCommonLayerStack": sig["layerStack"],
            "representativeWindow": sig,
            "variations": [],
            "compatibleTilesheets": sorted(sig.get("tilesheets", [])),
            "confidence": min(95, 40 + sig["occurrenceCount"]),
            "recommendedUse": recommended,
        })
    clusters.sort(key=lambda c: (-c["occurrenceCount"], c["role"], c["clusterId"]))
    return {"generatedAt": now_iso(), "clusters": clusters}


def select_template_clusters(clusters_doc: dict[str, Any]) -> list[dict[str, Any]]:
    required_roles = [
        "deep_void_fill", "floor_base", "floor_to_wall_transition", "wall_top", "wall_body",
        "lower_face_3_tile_stack", "left_wall_edge", "right_wall_edge",
        "upper_left_outer_corner", "upper_right_outer_corner", "lower_left_outer_corner", "lower_right_outer_corner",
        "upper_left_inner_corner", "upper_right_inner_corner", "lower_left_inner_corner", "lower_right_inner_corner",
        "shadow_under_wall", "ladder_opening", "shaft_opening", "blocked_boundary",
    ]
    selected = []
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in clusters_doc["clusters"]:
        by_role[c["role"]].append(c)
    for role in required_roles:
        items = by_role.get(role) or []
        if items:
            selected.append(items[0])
    # Ensure size diversity for requested windows.
    seen_sizes = {c["representativeWindow"]["size"] for c in selected}
    for size in ["1x3", "3x1", "3x3", "5x5", "1x5", "5x1"]:
        if size in seen_sizes:
            continue
        item = next((c for c in clusters_doc["clusters"] if c["representativeWindow"]["size"] == size), None)
        if item:
            selected.append(item)
            seen_sizes.add(size)
    # De-dupe.
    out = []
    seen = set()
    for c in selected:
        if c["clusterId"] not in seen:
            out.append(c)
            seen.add(c["clusterId"])
    return out


def build_template_library(clusters_doc: dict[str, Any], families_doc: dict[str, Any], compat: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    families = {f["familyId"]: f for f in families_doc["families"]}
    compat_names = [c["tilesheetName"] for c in compat if c["safeToTransferStructuralTemplateAcrossSheets"]]
    templates = []
    for c in select_template_clusters(clusters_doc):
        sig = c["representativeWindow"]
        fam = families.get(c.get("tileIdFamilyId") or "")
        production_status = "generator_ready" if c["recommendedUse"] == "generator_template" and c["occurrenceCount"] >= 3 else "review_needed"
        if c["role"] == "shaft_opening" and c["occurrenceCount"] < 3:
            production_status = "review_needed"
        templates.append({
            "templateId": f"fresh_{c['role']}_{sig['size']}_{c['clusterId'][-8:]}",
            "templateName": c["role"].replace("_", " ").title(),
            "sourceClusterId": c["clusterId"],
            "tileIdFamilyId": c.get("tileIdFamilyId"),
            "role": c["role"],
            "structuralDesign": sig["structuralDesign"],
            "size": sig["size"],
            "profile": "mine/dungeon",
            "anchor": sig["anchor"],
            "layerStack": sig["layerStack"],
            "tilesByLayer": sig["tileIdsByLayer"],
            "tileIdsByLayer": sig["tileIdsByLayer"],
            "requiredOrder": "exact relative cell/layer order from source signature",
            "emptyMask": [not cell["stack"] for cell in sig["layerStack"]],
            "floorMask": sig["floorMask"],
            "wallMask": sig["wallMask"],
            "voidMask": sig["voidMask"],
            "allowedRotations": fam["validRotations"] if fam else ["none"],
            "allowedTilesheets": compat_names,
            "tilesheetCompatibility": "local IDs align only for mine-compatible sheets listed in allowedTilesheets",
            "collisionMeaning": fam["collisionMeaning"] if fam else "unknown",
            "placementRules": "place the complete template only; no single structural cell may be emitted outside this layer stack",
            "neighborRules": sig["neighborContext"],
            "fallbackTemplateId": "marker_only_fallback",
            "productionStatus": production_status,
            "confidence": c["confidence"],
            "sourceEvidence": sig["sourceEvidence"],
            "previewPath": "",
            "notes": "Fresh relearned template. Requires manual visual review before production use unless explicitly promoted later.",
        })
    schema = {
        "schemaVersion": 1,
        "requiredTemplateFields": [
            "templateId", "sourceClusterId", "tileIdFamilyId", "role", "structuralDesign", "size",
            "anchor", "layerStack", "tileIdsByLayer", "sourceEvidence", "productionStatus",
        ],
        "productionStatuses": ["prototype_only", "review_needed", "generator_ready", "blocked"],
        "rule": "Structural tiles must be placed as complete templates/families, never loose tile IDs.",
    }
    return schema, {"generatedAt": now_iso(), "templates": templates}


def render_template(template: dict[str, Any], out: Path, scale: int = 2) -> None:
    w, h = (int(v) for v in template["size"].split("x"))
    cell = 16
    canvas = Image.new("RGBA", (w * cell, h * cell), (12, 12, 16, 255))
    draw = ImageDraw.Draw(canvas)
    ax, ay = template["anchor"]["x"], template["anchor"]["y"]
    colors = {"Back": (86, 62, 36, 255), "Buildings": (142, 102, 54, 255), "Front": (30, 30, 36, 190), "AlwaysFront": (180, 210, 250, 190), "Paths": (40, 120, 200, 190)}
    for layer in LAYERS:
        for c in template["layerStack"]:
            if layer not in c["stack"]:
                continue
            x = (c["dx"] + ax) * cell
            y = (c["dy"] + ay) * cell
            tid = c["stack"][layer]["localTileId"]
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=colors[layer])
            draw.text((x + 1, y + 2), str(tid), fill=(255, 255, 255, 230))
    draw.rectangle((ax * cell, ay * cell, (ax + 1) * cell - 1, (ay + 1) * cell - 1), outline=(255, 230, 70, 255), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.resize((canvas.width * scale, canvas.height * scale), Image.Resampling.NEAREST).save(out)


def render_atlas(library: dict[str, Any]) -> Path:
    templates = library["templates"]
    preview_records = []
    for t in templates:
        p = PREVIEW_DIR / f"{t['templateId']}.png"
        render_template(t, p)
        t["previewPath"] = str(p.resolve())
        preview_records.append((t, Image.open(p).convert("RGBA")))
    cell_w, cell_h = 260, 180
    cols = 3
    rows = max(1, math.ceil(len(preview_records) / cols))
    atlas = Image.new("RGBA", (cell_w * cols, cell_h * rows), (20, 20, 24, 255))
    draw = ImageDraw.Draw(atlas)
    for i, (t, img) in enumerate(preview_records):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        atlas.alpha_composite(img, (x + 8, y + 8))
        ev = t["sourceEvidence"][0] if t["sourceEvidence"] else {}
        lines = [
            t["role"][:32],
            f"{t['structuralDesign']} | {t['size']} | {t['productionStatus']}",
            f"{ev.get('sourceMap', '?')} @ {ev.get('sourceCoordinate', {})}",
            f"family {t.get('tileIdFamilyId')}",
            "ids " + ",".join(str(v) for vals in t["tileIdsByLayer"].values() for v in vals[:8])[:42],
        ]
        for j, text in enumerate(lines):
            draw.text((x + 8, y + 98 + j * 14), text, fill=(238, 238, 232, 235))
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(255, 255, 255, 55))
    out = PREVIEW_DIR / "mine_dungeon_fresh_template_atlas.png"
    atlas.save(out)
    return out


def write_reports(inventory, compat, raw, families, clusters, library, atlas) -> None:
    inv_lines = [
        "# Mine/Dungeon Fresh Source Inventory", "",
        f"- Sources inventoried: {len(inventory)}",
        f"- Parsed: {sum(1 for i in inventory if i.get('canBeParsed'))}",
        f"- Safe to learn: {sum(1 for i in inventory if i.get('safeToLearnFrom'))}",
        "",
        "| Map | Category | Type | Size | Layers | Tilesheets | Parsed | Safe | Risks |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]
    for item in inventory:
        size = item.get("mapSize", {})
        sheets = ", ".join(ts.get("tilesheetName", "") for ts in item.get("tilesheetsUsed", [])[:4])
        inv_lines.append(f"| `{item['mapName']}` | {item['sourceCategory']} | {item['fileType']} | {size.get('width','?')}x{size.get('height','?')} | {', '.join(item.get('layersPresent', []))} | {sheets} | {item.get('canBeParsed')} | {item.get('safeToLearnFrom')} | {', '.join(item.get('riskFlags', []))} |")
    (REPORTS / "mine_dungeon_fresh_source_inventory.md").write_text("\n".join(inv_lines) + "\n", encoding="utf-8")

    comp_lines = [
        "# Mine Tilesheet ID Compatibility", "",
        "| Tilesheet | Columns | Rows | Tile Count | Aligns With Vanilla | Palette Differs | Safe Transfer | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for c in compat:
        comp_lines.append(f"| `{c['tilesheetName']}` | {c.get('columns')} | {c.get('rows')} | {c.get('tileCount')} | {c['sameLayoutAsVanillaMine']} | {c['visualPaletteDiffers']} | {c['safeToTransferStructuralTemplateAcrossSheets']} | {c['notes']} |")
    (REPORTS / "mine_tilesheet_id_compatibility.md").write_text("\n".join(comp_lines) + "\n", encoding="utf-8")

    fam_lines = ["# Mine/Dungeon Tile-ID Family Summary", "", f"- Families: {len(families['families'])}", ""]
    for f in families["families"]:
        fam_lines += [
            f"## {f['familyName']}",
            f"- Family ID: `{f['familyId']}`",
            f"- Structural design: `{f['structuralDesign']}`",
            f"- Required grid: `{f['requiredGrid']}`",
            f"- Frequency: {f['frequency']}; confidence: {f['confidence']}",
            f"- Tile IDs by layer: `{json.dumps(f['tileIdsByLayer'])}`",
            f"- Never use alone: YES. Place only through complete templates.",
            "",
        ]
    (REPORTS / "mine_dungeon_tile_id_family_summary.md").write_text("\n".join(fam_lines), encoding="utf-8")

    clu_lines = ["# Mine/Dungeon Pattern Cluster Summary", "", f"- Clusters: {len(clusters['clusters'])}", ""]
    for c in clusters["clusters"][:80]:
        clu_lines.append(f"- `{c['clusterId']}`: {c['role']} {c['representativeWindow']['size']}; occurrences {c['occurrenceCount']}; use `{c['recommendedUse']}`; sources {', '.join(c['sourceMaps'][:4])}")
    (REPORTS / "mine_dungeon_pattern_cluster_summary.md").write_text("\n".join(clu_lines) + "\n", encoding="utf-8")

    atlas_lines = ["# Mine/Dungeon Fresh Template Atlas", "", f"- Atlas: `{atlas}`", f"- Templates: {len(library['templates'])}", ""]
    for t in library["templates"]:
        ev = t["sourceEvidence"][0] if t["sourceEvidence"] else {}
        atlas_lines.append(f"- `{t['templateId']}`: {t['role']} / {t['structuralDesign']} / {t['size']} / {t['productionStatus']} from `{ev.get('sourceMap')}` at `{ev.get('sourceCoordinate')}`.")
    (REPORTS / "mine_dungeon_fresh_template_atlas.md").write_text("\n".join(atlas_lines) + "\n", encoding="utf-8")

    old_files = [
        ROOT / "pattern_learning" / "tile_grammar_templates" / "golden_vanilla_mine_templates" / "golden_mine_templates.json",
        ROOT / "pattern_learning" / "repeated_structure_patterns" / "templates" / "custom_07_edge_wrapper_pattern_registry.json",
    ]
    old_existing = [p for p in old_files if p.exists()]
    comparison = {
        "generatedAt": now_iso(),
        "oldDatabasesFound": [str(p.resolve()) for p in old_existing],
        "freshFamilies": len(families["families"]),
        "freshTemplates": len(library["templates"]),
        "oldTemplatesMissingSourceEvidence": [],
        "oldSingleTileRoleListsFlagged": ["build_smart_edge_wrapper.py legacy TOP_WALLS/BODY_WALLS/LOWER_FACES lists", "custom_07 registry tileIds are now superseded by complete fresh family templates"],
        "freshTemplatesNeedingManualApproval": [t["templateId"] for t in library["templates"] if t["productionStatus"] != "generator_ready"],
        "freshTemplatesReplacingOld": [t["templateId"] for t in library["templates"] if t["productionStatus"] == "generator_ready"],
        "blockedTemplates": [],
    }
    (OUT_ROOT / "old_vs_fresh_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    cmp_lines = ["# Mine/Dungeon Template Old vs Fresh Comparison", "", f"- Old databases found: {len(old_existing)}", f"- Fresh families: {len(families['families'])}", f"- Fresh templates: {len(library['templates'])}", "", "## Flags"]
    cmp_lines += [f"- {x}" for x in comparison["oldSingleTileRoleListsFlagged"]]
    cmp_lines += ["", "## Fresh generator-ready templates"] + [f"- `{x}`" for x in comparison["freshTemplatesReplacingOld"]]
    cmp_lines += ["", "## Fresh templates needing manual approval"] + [f"- `{x}`" for x in comparison["freshTemplatesNeedingManualApproval"]]
    (REPORTS / "mine_dungeon_template_old_vs_fresh_comparison.md").write_text("\n".join(cmp_lines) + "\n", encoding="utf-8")

    summary = [
        "# Fresh Mine/Dungeon Template Relearn Summary", "",
        f"- Maps inventoried: {len(inventory)}",
        f"- Unique repeated signatures: {raw['uniqueSignatures']}",
        f"- Window occurrences scanned: {raw['totalWindowOccurrences']}",
        f"- Tile-ID families created: {len(families['families'])}",
        f"- Pattern clusters created: {len(clusters['clusters'])}",
        f"- Fresh templates created: {len(library['templates'])}",
        "- Production maps generated: NO",
        "- Source maps modified: NO",
        "",
        "The fresh library preserves complete grids and layer stacks. Structural tile IDs remain forbidden as loose role-list placements.",
    ]
    (REPORTS / "fresh_mine_dungeon_template_relearn_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (REPORTS / "fresh_mine_dungeon_template_generator_update.md").write_text(
        "# Fresh Mine/Dungeon Template Generator Update\n\n`build_smart_edge_wrapper_v2.py` consumes `mine_dungeon_fresh_template_library.json` and logs template/family placements for custom_08.\n",
        encoding="utf-8",
    )
    (REPORTS / "fresh_mine_dungeon_template_safety_status.md").write_text(
        "# Fresh Mine/Dungeon Template Safety Status\n\n- No production maps generated.\n- Original Moonvillage maps untouched.\n- mission_assets untouched.\n- unpacked_basegame untouched.\n- Approved DB unchanged.\n- Fresh templates are prototype/review unless explicitly marked generator_ready.\n",
        encoding="utf-8",
    )
    (REPORTS / "fresh_mine_dungeon_next_manual_review_targets.md").write_text(
        "# Fresh Mine/Dungeon Next Manual Review Targets\n\n- Review all `review_needed` templates in the atlas.\n- Promote only visually approved 3x3 corner and 5x5 opening templates.\n- Verify angled wall families against side-by-side Moonvillage dungeon maps before production use.\n",
        encoding="utf-8",
    )


def main() -> int:
    ensure_dirs()
    sources = [parse_source(p) for p in source_files()]
    parsed = [s for s in sources if s.get("parsed")]
    inventory = build_inventory(sources)
    compat = compatibility_report(parsed)
    raw = extract_windows(parsed)
    signatures = build_signatures(raw)
    families = build_families(signatures)
    clusters = build_clusters(signatures, families)
    schema, library = build_template_library(clusters, families, compat)
    atlas = render_atlas(library)
    # Update preview paths after atlas render.
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "source_inventory.json").write_text(json.dumps({"generatedAt": now_iso(), "sources": inventory}, indent=2), encoding="utf-8")
    (OUT_ROOT / "mine_tilesheet_id_compatibility.json").write_text(json.dumps({"generatedAt": now_iso(), "tilesheets": compat}, indent=2), encoding="utf-8")
    (RAW_DIR / "mine_dungeon_raw_windows.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    (RAW_DIR / "mine_dungeon_pattern_signatures.json").write_text(json.dumps(signatures, indent=2), encoding="utf-8")
    (CLUSTER_DIR / "mine_dungeon_tile_id_families.json").write_text(json.dumps(families, indent=2), encoding="utf-8")
    (CLUSTER_DIR / "mine_dungeon_pattern_clusters.json").write_text(json.dumps(clusters, indent=2), encoding="utf-8")
    (TEMPLATE_DIR / "mine_dungeon_fresh_template_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    (TEMPLATE_DIR / "mine_dungeon_fresh_template_library.json").write_text(json.dumps(library, indent=2), encoding="utf-8")
    write_reports(inventory, compat, raw, families, clusters, library, atlas)
    print(json.dumps({
        "status": "PASS",
        "sources": len(inventory),
        "parsed": len(parsed),
        "uniqueSignatures": raw["uniqueSignatures"],
        "families": len(families["families"]),
        "clusters": len(clusters["clusters"]),
        "templates": len(library["templates"]),
        "atlas": str(atlas.resolve()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
