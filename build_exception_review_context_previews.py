#!/usr/bin/env python3
"""Build larger map-context previews for New_vanillaeditedmaps exception review cases."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


TOOL_ROOT = Path(__file__).resolve().parent
NVE_ROOT = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps"
ACTION_PACK_ROOT = NVE_ROOT / "actionable_review" / "review_packs"
EXCEPTION_ROOT = NVE_ROOT / "exception_review"
CONTEXT_ROOT = EXCEPTION_ROOT / "context_previews"
CONTEXT_INDEX_PATH = CONTEXT_ROOT / "context_preview_index.json"
STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
CONTEXT_SIZES = [3, 5, 9, 15]

sys.path.insert(0, str(TOOL_ROOT))
sys.path.insert(0, str(NVE_ROOT))
from analyze_new_vanillaeditedmaps import SOURCE_ROOT, base_key, load_approved_lookup, load_vanilla_index, parse_maps, stack_for


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(TOOL_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def safe_name(value: Any) -> str:
    text = str(value or "unknown").lower()
    return re.sub(r"[^a-z0-9_\-]+", "_", text).strip("_") or "unknown"


def load_review_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(ACTION_PACK_ROOT.glob("*.json")):
        data = load_json(path, {})
        for entry in data.get("entries", []):
            entries.append({**entry, "reviewPackId": data.get("reviewPackId"), "reviewGroup": data.get("group")})
    return entries


def image_lookup() -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    for path in SOURCE_ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            keys = {
                path.name.lower(),
                path.stem.lower(),
                base_key(path.name),
                base_key(path.stem),
            }
            for key in keys:
                lookup.setdefault(key, path)
    return lookup


def resolve_sheet_images(parsed: dict[str, Any], images: dict[str, Path]) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    map_parent = Path(parsed["path"]).parent
    for ts in parsed.get("tilesheets", []):
        sheet_base = base_key(ts.get("imageSource") or ts.get("id"))
        candidates = [
            map_parent / str(ts.get("imageSource") or ""),
            SOURCE_ROOT / str(ts.get("imageSource") or ""),
            images.get(str(ts.get("imageSource") or "").lower()),
            images.get(base_key(ts.get("imageSource"))),
            images.get(base_key(ts.get("id"))),
        ]
        source_path = next((Path(path) for path in candidates if path and Path(path).exists()), None)
        if not source_path:
            continue
        try:
            image = Image.open(source_path).convert("RGBA")
        except Exception:
            continue
        sheet_size = ts.get("sheetSize") or [max(1, image.width // 16), max(1, image.height // 16)]
        tile_size = ts.get("tileSize") or [16, 16]
        resolved[sheet_base] = {
            "path": source_path,
            "image": image,
            "columns": int(sheet_size[0] or max(1, image.width // 16)),
            "tileWidth": int(tile_size[0] or 16),
            "tileHeight": int(tile_size[1] or 16),
        }
    return resolved


def crop_tile(sheet_info: dict[str, Any], local_id: int) -> Image.Image | None:
    image: Image.Image = sheet_info["image"]
    columns = max(1, int(sheet_info["columns"]))
    tile_w = int(sheet_info["tileWidth"])
    tile_h = int(sheet_info["tileHeight"])
    tile_x = local_id % columns
    tile_y = local_id // columns
    box = (tile_x * tile_w, tile_y * tile_h, (tile_x + 1) * tile_w, (tile_y + 1) * tile_h)
    if box[2] > image.width or box[3] > image.height:
        return None
    return image.crop(box)


def draw_grid_and_center(image: Image.Image, size: int, tile_w: int, tile_h: int) -> None:
    draw = ImageDraw.Draw(image)
    grid_color = (255, 255, 255, 42)
    for x in range(0, image.width + 1, tile_w):
        draw.line([(x, 0), (x, image.height)], fill=grid_color)
    for y in range(0, image.height + 1, tile_h):
        draw.line([(0, y), (image.width, y)], fill=grid_color)
    radius = size // 2
    x0 = radius * tile_w
    y0 = radius * tile_h
    draw.rectangle([x0, y0, x0 + tile_w - 1, y0 + tile_h - 1], outline=(255, 48, 48, 255), width=2)


def render_context(
    parsed: dict[str, Any],
    sheet_images: dict[str, dict[str, Any]],
    center_x: int,
    center_y: int,
    size: int,
    layer_mode: str,
) -> Image.Image:
    tile_w = int(parsed.get("tileWidth") or 16)
    tile_h = int(parsed.get("tileHeight") or 16)
    radius = size // 2
    canvas = Image.new("RGBA", (size * tile_w, size * tile_h), (20, 20, 24, 255))
    layers = STANDARD_LAYERS if layer_mode == "combined" else [layer_mode]
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            map_x = center_x + dx
            map_y = center_y + dy
            if map_x < 0 or map_y < 0 or map_x >= parsed["width"] or map_y >= parsed["height"]:
                continue
            _, stack = stack_for(parsed, map_x, map_y)
            dest = ((dx + radius) * tile_w, (dy + radius) * tile_h)
            for layer in layers:
                tile = stack.get(layer)
                if not tile:
                    continue
                info = sheet_images.get(base_key(tile.get("sheet")))
                if not info:
                    continue
                crop = crop_tile(info, int(tile.get("tileIndex")))
                if crop:
                    canvas.alpha_composite(crop, dest)
    draw_grid_and_center(canvas, size, tile_w, tile_h)
    return canvas


def build_context_previews() -> dict[str, Any]:
    vanilla_index = load_vanilla_index()
    approved_lookup = load_approved_lookup()
    _, _, parsed_maps = parse_maps(vanilla_index, approved_lookup)
    parsed_by_name = {item["mapName"]: item for item in parsed_maps}
    images = image_lookup()
    entries = load_review_entries()
    records = []
    missing_maps = 0
    missing_images = 0
    rendered_images = 0
    source_counts = Counter()
    sheet_image_cache: dict[str, dict[str, dict[str, Any]]] = {}

    for entry in entries:
        parsed = parsed_by_name.get(entry.get("mapName"))
        if not parsed:
            missing_maps += 1
            records.append(
                {
                    "caseId": entry.get("caseId"),
                    "mapName": entry.get("mapName"),
                    "x": entry.get("x"),
                    "y": entry.get("y"),
                    "reviewPackId": entry.get("reviewPackId"),
                    "available": False,
                    "missingReason": "map_not_parsed",
                }
            )
            continue

        map_name = safe_name(entry.get("mapName"))
        case_id = safe_name(entry.get("caseId"))
        if map_name not in sheet_image_cache:
            sheet_image_cache[map_name] = resolve_sheet_images(parsed, images)
        sheet_images = sheet_image_cache[map_name]
        if not sheet_images:
            missing_images += 1

        combined: dict[str, str] = {}
        layers_9: dict[str, str] = {}
        for size in CONTEXT_SIZES:
            out_path = CONTEXT_ROOT / map_name / f"{case_id}_{size}x{size}_combined.png"
            if not out_path.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
                render_context(parsed, sheet_images, int(entry["x"]), int(entry["y"]), size, "combined").save(out_path)
            combined[f"{size}x{size}"] = rel(out_path)
            rendered_images += 1
        for layer in STANDARD_LAYERS:
            out_path = CONTEXT_ROOT / map_name / f"{case_id}_9x9_{layer.lower()}.png"
            if not out_path.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
                render_context(parsed, sheet_images, int(entry["x"]), int(entry["y"]), 9, layer).save(out_path)
            layers_9[layer] = rel(out_path)
            rendered_images += 1

        _, center_stack = stack_for(parsed, int(entry["x"]), int(entry["y"]))
        source_counts.update(tile.get("sheet") for tile in center_stack.values())
        records.append(
            {
                "caseId": entry.get("caseId"),
                "mapName": entry.get("mapName"),
                "x": entry.get("x"),
                "y": entry.get("y"),
                "reviewPackId": entry.get("reviewPackId"),
                "available": True,
                "defaultSize": "9x9",
                "defaultLayerMode": "combined",
                "combined": combined,
                "layers9x9": layers_9,
                "sourceTilesheetsAtCenter": sorted({tile.get("sheet") for tile in center_stack.values()}),
            }
        )

    return {
        "generatedAt": now_iso(),
        "source": "build_exception_review_context_previews.py",
        "caseCount": len(records),
        "availableCaseCount": sum(1 for item in records if item.get("available")),
        "missingMapCount": missing_maps,
        "missingSheetImageMapCount": missing_images,
        "renderedImageReferences": rendered_images,
        "contextSizes": [f"{size}x{size}" for size in CONTEXT_SIZES],
        "layerModes": ["combined", *STANDARD_LAYERS],
        "sourceTileSheetCounts": dict(source_counts.most_common()),
        "cases": records,
    }


def main() -> int:
    index = build_context_previews()
    write_json(CONTEXT_INDEX_PATH, index)
    print(
        json.dumps(
            {
                "cases": index["caseCount"],
                "available": index["availableCaseCount"],
                "missingMaps": index["missingMapCount"],
                "path": str(CONTEXT_INDEX_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
