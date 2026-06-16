#!/usr/bin/env python3
"""Build clean and labeled preview images for manual safe patterns."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

import approval_validation_utils as approval_utils
from validate_manual_safe_patterns import PATTERN_PATH, pattern_list


TOOL_ROOT = Path(__file__).resolve().parent
PATTERN_ROOT = TOOL_ROOT / "pattern_learning" / "manual_safe_patterns"
PREVIEW_ROOT = PATTERN_ROOT / "previews"
REPORT_PATH = TOOL_ROOT / "reports" / "manual_safe_pattern_preview_report.md"
TILE_SIZE = 16
DISPLAY_TILE = 48


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def safe_name(value: Any) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value or "pattern"))
    return text.strip("_") or "pattern"


def image_path_for(tile: dict[str, Any], candidate: dict[str, Any] | None) -> Path | None:
    for key in ("copiedImagePath", "imagePath"):
        if tile.get(key):
            path = Path(str(tile[key]))
            if path.exists():
                return path
    if candidate:
        for key in ("copiedImagePath", "imagePath"):
            if candidate.get(key):
                path = Path(str(candidate[key]))
                if path.exists():
                    return path
    return None


def local_id_for(tile: dict[str, Any], candidate: dict[str, Any] | None) -> int | None:
    value = tile.get("localTileId")
    if value is None and candidate:
        value = candidate.get("localTileId")
    try:
        return int(value)
    except Exception:
        return None


def tile_crop(tile: dict[str, Any], candidate: dict[str, Any] | None) -> Image.Image:
    path = image_path_for(tile, candidate)
    local_id = local_id_for(tile, candidate)
    if not path or local_id is None:
        img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (32, 36, 42, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, TILE_SIZE - 1, TILE_SIZE - 1), outline=(255, 107, 107, 255))
        return img
    try:
        source = Image.open(path).convert("RGBA")
        columns = max(1, source.width // TILE_SIZE)
        tile_x = int(tile.get("tileX") if tile.get("tileX") is not None else candidate.get("tileX") if candidate else local_id % columns)
        tile_y = int(tile.get("tileY") if tile.get("tileY") is not None else candidate.get("tileY") if candidate else local_id // columns)
        box = (tile_x * TILE_SIZE, tile_y * TILE_SIZE, tile_x * TILE_SIZE + TILE_SIZE, tile_y * TILE_SIZE + TILE_SIZE)
        return source.crop(box)
    except Exception:
        img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (32, 36, 42, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, TILE_SIZE - 1, TILE_SIZE - 1), outline=(255, 195, 106, 255))
        return img


def layout_cells(pattern: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    tiles = pattern.get("tiles") or []
    if pattern.get("patternType") in {"grid", "neighbor_mask"}:
        cells = []
        for index, tile in enumerate(tiles):
            x = tile.get("gridX")
            y = tile.get("gridY")
            cells.append((int(x) if x is not None else index, int(y) if y is not None else 0, tile))
        return cells
    if pattern.get("patternType") == "layer_stack":
        layer_order = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
        layer_rank = {layer: i for i, layer in enumerate(layer_order)}
        return [(0, layer_rank.get(tile.get("layer"), index), tile) for index, tile in enumerate(tiles)]
    return [(index, 0, tile) for index, tile in enumerate(tiles)]


def render_pattern(pattern: dict[str, Any], candidates: dict[str, dict[str, Any]], labeled: bool) -> Image.Image:
    cells = layout_cells(pattern)
    if not cells:
        return Image.new("RGBA", (DISPLAY_TILE, DISPLAY_TILE), (16, 19, 23, 255))
    min_x = min(x for x, _, _ in cells)
    min_y = min(y for _, y, _ in cells)
    max_x = max(x for x, _, _ in cells)
    max_y = max(y for _, y, _ in cells)
    width = (max_x - min_x + 1) * DISPLAY_TILE
    height = (max_y - min_y + 1) * DISPLAY_TILE
    canvas = Image.new("RGBA", (width, height), (16, 19, 23, 255))
    draw = ImageDraw.Draw(canvas)
    for x, y, tile in cells:
        candidate = candidates.get(str(tile.get("candidateId") or ""))
        crop = tile_crop(tile, candidate).resize((DISPLAY_TILE, DISPLAY_TILE), Image.Resampling.NEAREST)
        px = (x - min_x) * DISPLAY_TILE
        py = (y - min_y) * DISPLAY_TILE
        canvas.alpha_composite(crop, (px, py))
        draw.rectangle((px, py, px + DISPLAY_TILE - 1, py + DISPLAY_TILE - 1), outline=(56, 65, 74, 255))
        if labeled:
            label = f"{tile.get('role') or '?'}\n{tile.get('layer') or '?'}\n{tile.get('candidateId') or ''}"
            draw.rectangle((px, py, px + DISPLAY_TILE - 1, min(py + 30, py + DISPLAY_TILE - 1)), fill=(238, 242, 245, 210))
            draw.text((px + 2, py + 2), label[:48], fill=(16, 19, 23, 255))
    return canvas


def main() -> int:
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    patterns = pattern_list(load_json(PATTERN_PATH, {"patterns": []}))
    candidates = approval_utils.candidate_lookup()
    written = []
    for pattern in patterns:
        pattern_id = safe_name(pattern.get("patternId") or pattern.get("patternName"))
        clean = render_pattern(pattern, candidates, labeled=False)
        labeled = render_pattern(pattern, candidates, labeled=True)
        clean_path = PREVIEW_ROOT / f"{pattern_id}_clean.png"
        labeled_path = PREVIEW_ROOT / f"{pattern_id}_labeled.png"
        clean.save(clean_path)
        labeled.save(labeled_path)
        written.append((pattern_id, clean_path, labeled_path))
    lines = [
        "# Manual Safe Pattern Preview Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Patterns rendered: {len(written)}",
        "",
    ]
    for pattern_id, clean_path, labeled_path in written:
        lines.append(f"- `{pattern_id}`: `{clean_path}`, `{labeled_path}`")
    if not written:
        lines.append("- No manual safe patterns found.")
    write_text(REPORT_PATH, "\n".join(lines))
    print(f"Safe pattern previews generated: {len(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
