#!/usr/bin/env python3
"""Build source tilesheet crops for the New_vanillaeditedmaps exception-review UI."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


TOOL_ROOT = Path(__file__).resolve().parent
ACTIONABLE_PACK_DIR = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "actionable_review" / "review_packs"
EXCEPTION_ROOT = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "exception_review"
CROP_ROOT = EXCEPTION_ROOT / "tile_crops"
METADATA_PATH = EXCEPTION_ROOT / "tile_preview_metadata.json"
CROP_INDEX_PATH = CROP_ROOT / "tile_crop_index.json"
TILESET_CATALOG_PATH = TOOL_ROOT / "database" / "tileset_catalog.json"
APPROVED_DB_PATH = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
NEW_MAP_INVENTORY_PATH = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "new_vanillaeditedmaps_inventory.json"
UNPACKED_BASEGAME = TOOL_ROOT / "mission_assets" / "unpacked_basegame"
STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def base_key(value: Any) -> str:
    name = Path(str(value or "").replace("\\", "/")).name.lower()
    for suffix in [".png", ".tsx", ".tbin", ".json"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return re.sub(r"[^a-z0-9]+", "", name)


def display_sheet_name(value: Any) -> str:
    text = str(value or "")
    if ":" in text:
        return text.rsplit(":", 1)[0]
    return Path(text.replace("\\", "/")).name


def to_web_path(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(TOOL_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def parse_tile_id(tile_value: Any) -> tuple[str, int] | None:
    text = str(tile_value or "").strip()
    if ":" not in text:
        return None
    sheet, local = text.rsplit(":", 1)
    try:
        return sheet, int(local)
    except ValueError:
        return None


def add_image_candidate(index: dict[str, list[dict[str, Any]]], path: Path, source: str, priority: int, extra: dict[str, Any] | None = None) -> None:
    if not path.exists() or path.suffix.lower() != ".png":
        return
    key = base_key(path.name)
    index[key].append(
        {
            "path": path.resolve(),
            "source": source,
            "priority": priority,
            **(extra or {}),
        }
    )


def build_image_index() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)

    inventory = load_json(NEW_MAP_INVENTORY_PATH, {"files": []})
    for item in inventory.get("files", []):
        if str(item.get("extension", "")).lower() == ".png":
            add_image_candidate(index, Path(item.get("fullPath", "")), "new_vanillaeditedmaps_inventory", 10, {"inventoryRelativePath": item.get("relativePath")})

    if UNPACKED_BASEGAME.exists():
        for path in UNPACKED_BASEGAME.glob("*.png"):
            add_image_candidate(index, path, "unpacked_basegame", 20)

    catalog = load_json(TILESET_CATALOG_PATH, [])
    for item in catalog if isinstance(catalog, list) else []:
        path = Path(item.get("imagePath") or item.get("copiedPath") or "")
        priority = {"moonvillage": 30, "stardew_mods": 40, "reference_mods": 50}.get(item.get("sourceCategory"), 60)
        add_image_candidate(index, path, "tileset_catalog", priority, {"tilesetCatalog": item})

    for key in index:
        index[key].sort(key=lambda item: (item["priority"], str(item["path"]).lower()))
    return index


def build_approved_lookup() -> dict[tuple[str, int], dict[str, Any]]:
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    data = load_json(APPROVED_DB_PATH, [])
    for entry in data if isinstance(data, list) else []:
        local = entry.get("localTileId")
        try:
            local_id = int(local)
        except (TypeError, ValueError):
            continue
        keys = {
            base_key(entry.get("tilesetName")),
            base_key(entry.get("imageName")),
            base_key(entry.get("copiedImagePath")),
        }
        profile = {
            "candidateId": entry.get("candidateId"),
            "approved": bool(entry.get("approved")),
            "approvedClass": entry.get("finalClass"),
            "approvedPurpose": entry.get("finalPurpose"),
            "collision": entry.get("collision"),
            "allowedLayers": entry.get("allowedLayers") or [],
            "approvalSource": entry.get("approvalSource"),
            "approvalConfidence": entry.get("approvalConfidence"),
        }
        for key in keys:
            if key and (key, local_id) not in lookup:
                lookup[(key, local_id)] = profile
    return lookup


def resolve_image(sheet: str, image_index: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, list[str]]:
    key = base_key(sheet)
    attempts = [key]
    candidates = list(image_index.get(key, []))
    if not candidates:
        for image_key, values in image_index.items():
            if key and (key in image_key or image_key in key):
                candidates.extend(values)
                attempts.append(image_key)
    candidates.sort(key=lambda item: (item["priority"], str(item["path"]).lower()))
    return (candidates[0] if candidates else None), attempts


def crop_fixed_context(image: Image.Image, tile_x: int, tile_y: int, tile_w: int, tile_h: int, radius: int) -> Image.Image:
    count = radius * 2 + 1
    canvas = Image.new("RGBA", (count * tile_w, count * tile_h), (0, 0, 0, 0))
    for cy in range(tile_y - radius, tile_y + radius + 1):
        for cx in range(tile_x - radius, tile_x + radius + 1):
            src = (cx * tile_w, cy * tile_h, (cx + 1) * tile_w, (cy + 1) * tile_h)
            dst = ((cx - tile_x + radius) * tile_w, (cy - tile_y + radius) * tile_h)
            if src[0] < 0 or src[1] < 0 or src[2] > image.width or src[3] > image.height:
                continue
            canvas.alpha_composite(image.crop(src), dst)
    return canvas


def crop_single(image: Image.Image, tile_x: int, tile_y: int, tile_w: int, tile_h: int) -> Image.Image:
    return image.crop((tile_x * tile_w, tile_y * tile_h, (tile_x + 1) * tile_w, (tile_y + 1) * tile_h))


def crop_paths(sheet_key: str, local_tile_id: int) -> dict[str, Path]:
    safe_sheet = re.sub(r"[^a-z0-9_\\-]+", "_", sheet_key.lower())
    base = CROP_ROOT / safe_sheet / f"tile_{local_tile_id:04d}"
    return {
        "single": base.with_name(base.name + "_single.png"),
        "context3x3": base.with_name(base.name + "_context3x3.png"),
        "context5x5": base.with_name(base.name + "_context5x5.png"),
    }


def make_tile_preview(
    sheet: str,
    local_tile_id: int,
    image_index: dict[str, list[dict[str, Any]]],
    approved_lookup: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    sheet_key = base_key(sheet)
    resolved, attempts = resolve_image(sheet, image_index)
    base = {
        "sourceTilesheet": sheet,
        "sourceTilesheetKey": sheet_key,
        "localTileId": local_tile_id,
        "resolved": False,
        "attemptedKeys": attempts,
        "warnings": [],
    }
    approved = approved_lookup.get((sheet_key, local_tile_id), {})
    base.update(
        {
            "candidateId": approved.get("candidateId"),
            "approved": bool(approved.get("approved")),
            "approvedClass": approved.get("approvedClass"),
            "approvedPurpose": approved.get("approvedPurpose"),
            "collision": approved.get("collision"),
            "allowedLayers": approved.get("allowedLayers") or [],
            "approvalSource": approved.get("approvalSource"),
            "approvalConfidence": approved.get("approvalConfidence"),
        }
    )
    if not resolved:
        base["warnings"].append("source tilesheet image could not be resolved")
        return base

    source_path = Path(resolved["path"])
    try:
        image = Image.open(source_path).convert("RGBA")
    except Exception as exc:
        base["warnings"].append(f"source tilesheet image could not be opened: {exc}")
        base["sourceImagePath"] = str(source_path)
        base["sourceImageWebPath"] = to_web_path(source_path)
        return base

    catalog = resolved.get("tilesetCatalog") or {}
    tile_w = int(catalog.get("tileWidth") or 16)
    tile_h = int(catalog.get("tileHeight") or 16)
    columns = int(catalog.get("columns") or max(1, image.width // tile_w))
    tile_count = int(catalog.get("tileCount") or (columns * max(1, image.height // tile_h)))
    tile_x = local_tile_id % columns
    tile_y = local_tile_id // columns

    base.update(
        {
            "resolved": True,
            "sourceResolver": resolved.get("source"),
            "sourceImagePath": str(source_path),
            "sourceImageWebPath": to_web_path(source_path),
            "imageWidth": image.width,
            "imageHeight": image.height,
            "tileWidth": tile_w,
            "tileHeight": tile_h,
            "columns": columns,
            "tileCount": tile_count,
            "tileX": tile_x,
            "tileY": tile_y,
        }
    )
    if local_tile_id < 0 or local_tile_id >= tile_count:
        base["warnings"].append("localTileId is outside resolved tilesheet tile count")
        return base
    if (tile_x + 1) * tile_w > image.width or (tile_y + 1) * tile_h > image.height:
        base["warnings"].append("localTileId resolves outside image bounds")
        return base

    paths = crop_paths(sheet_key, local_tile_id)
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    crop_single(image, tile_x, tile_y, tile_w, tile_h).save(paths["single"])
    crop_fixed_context(image, tile_x, tile_y, tile_w, tile_h, 1).save(paths["context3x3"])
    crop_fixed_context(image, tile_x, tile_y, tile_w, tile_h, 2).save(paths["context5x5"])
    base.update(
        {
            "singleTileCropPath": to_web_path(paths["single"]),
            "context3x3Path": to_web_path(paths["context3x3"]),
            "context5x5Path": to_web_path(paths["context5x5"]),
        }
    )
    return base


def load_review_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(ACTIONABLE_PACK_DIR.glob("*.json")):
        data = load_json(path, {})
        for entry in data.get("entries", []):
            entries.append({**entry, "_reviewPackId": data.get("reviewPackId"), "_reviewPackPath": path})
    return entries


def main() -> int:
    CROP_ROOT.mkdir(parents=True, exist_ok=True)
    image_index = build_image_index()
    approved_lookup = build_approved_lookup()
    entries = load_review_entries()
    unique_tiles = sorted(
        {
            parse_tile_id(tile)
            for entry in entries
            for tile in (entry.get("tileIdsByLayer") or {}).values()
            if parse_tile_id(tile)
        },
        key=lambda item: (base_key(item[0]), item[1]),
    )
    tile_preview_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for sheet, local_id in unique_tiles:
        tile_preview_by_key[(base_key(sheet), local_id)] = make_tile_preview(sheet, local_id, image_index, approved_lookup)

    case_records = []
    missing_cases = []
    layer_count = 0
    missing_layer_count = 0
    tile_946_records = []
    for entry in entries:
        layers = []
        tile_ids_by_layer = entry.get("tileIdsByLayer") or {}
        for layer_name in STANDARD_LAYERS:
            parsed = parse_tile_id(tile_ids_by_layer.get(layer_name))
            if not parsed:
                layers.append({"layerName": layer_name, "empty": True})
                continue
            sheet, local_id = parsed
            preview = dict(tile_preview_by_key.get((base_key(sheet), local_id), {}))
            layer_count += 1
            if not preview.get("resolved") or not preview.get("singleTileCropPath"):
                missing_layer_count += 1
            if local_id == 946:
                tile_946_records.append({"caseId": entry.get("caseId"), "mapName": entry.get("mapName"), "layerName": layer_name, "sourceTilesheet": sheet, "localTileId": local_id})
            layers.append(
                {
                    "layerName": layer_name,
                    "empty": False,
                    "mapName": entry.get("mapName"),
                    "x": entry.get("x"),
                    "y": entry.get("y"),
                    **preview,
                }
            )
        record = {
            "caseId": entry.get("caseId"),
            "reviewPackId": entry.get("_reviewPackId"),
            "mapName": entry.get("mapName"),
            "x": entry.get("x"),
            "y": entry.get("y"),
            "layerStack": entry.get("layerStack"),
            "layers": layers,
        }
        if any((not layer.get("empty")) and (not layer.get("resolved") or not layer.get("singleTileCropPath")) for layer in layers):
            missing_cases.append(record["caseId"])
        case_records.append(record)

    metadata = {
        "generatedAt": now_iso(),
        "source": "build_exception_review_tile_crops.py",
        "caseCount": len(case_records),
        "reviewLayerTileCount": layer_count,
        "missingLayerTileCount": missing_layer_count,
        "missingCaseCount": len(set(missing_cases)),
        "tile946Records": tile_946_records,
        "cases": case_records,
    }
    crop_index = {
        "generatedAt": now_iso(),
        "uniqueTileCount": len(unique_tiles),
        "resolvedTileCount": sum(1 for item in tile_preview_by_key.values() if item.get("resolved") and item.get("singleTileCropPath")),
        "missingTileCount": sum(1 for item in tile_preview_by_key.values() if not item.get("resolved") or not item.get("singleTileCropPath")),
        "sourceResolverCounts": Counter(str(item.get("sourceResolver") or "missing") for item in tile_preview_by_key.values()),
        "tiles": list(tile_preview_by_key.values()),
    }
    crop_index["sourceResolverCounts"] = dict(crop_index["sourceResolverCounts"])
    write_json(METADATA_PATH, metadata)
    write_json(CROP_INDEX_PATH, crop_index)
    print(f"Cases: {len(case_records)}")
    print(f"Layer tiles: {layer_count}")
    print(f"Unique source tiles: {len(unique_tiles)}")
    print(f"Missing layer tiles: {missing_layer_count}")
    print(f"Wrote {METADATA_PATH}")
    print(f"Wrote {CROP_INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
