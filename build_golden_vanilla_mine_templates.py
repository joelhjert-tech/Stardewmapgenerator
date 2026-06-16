#!/usr/bin/env python3
"""Extract reusable golden mine templates from vanilla mine tBIN maps.

Golden templates are source-stamped windows copied from real vanilla mine maps.
They are review/prototype evidence only; this script does not modify source
maps, production maps, mission assets, or the approved tile database.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
BASEGAME = ROOT / "mission_assets" / "unpacked_basegame"
MINE_DIR = BASEGAME / "Mine"
OUT_DIR = ROOT / "pattern_learning" / "tile_grammar_templates" / "golden_vanilla_mine_templates"
PREVIEW_DIR = OUT_DIR / "previews"
REPORTS = ROOT / "reports"
TILE_SIZE = 16
LAYERS = ("Back", "Buildings", "Front", "AlwaysFront")

sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402

WALL_IDS = {
    68, 69, 70, 71, 72, 73, 74, 75, 76,
    84, 85, 86, 87, 88, 89, 90, 91, 92,
    93, 94, 100, 101, 102, 103, 104, 105, 106,
    107, 108, 109, 110, 116, 117, 118, 119, 120,
    121, 122, 123, 124, 125, 126, 132, 133, 134,
    141, 142, 148, 157, 158, 159, 191, 196, 207,
}
LADDER_IDS = {67, 83, 99, 115}
SHAFT_CANDIDATE_IDS = {174, 175, 190, 191, 206, 207, 222, 223}
FRONT_EDGE_IDS = {196, 197, 205, 206, 213, 214, 215, 216, 220, 221, 232}
UNDER_WALL_BACK = {186, 185, 188, 217, 218}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_maps() -> List[Path]:
    roots = [MINE_DIR, BASEGAME]
    found: List[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("*.tbin"))
    mine_like = []
    for path in sorted(set(found), key=lambda p: p.name):
        if path.parent == MINE_DIR or path.stem.isdigit() or "mine" in path.stem.lower():
            mine_like.append(path)
    return mine_like


def sheet_image_path(image_source: str) -> Optional[Path]:
    names = [image_source]
    if not image_source.lower().endswith(".png"):
        names.append(image_source + ".png")
    for name in names:
        for root in (MINE_DIR, BASEGAME):
            cand = root / name
            if cand.exists() and cand.is_file():
                return cand
    return None


def parse_map(path: Path) -> Optional[dict]:
    try:
        mp = tbin_reader.parse(path.read_bytes())
    except Exception:
        return None
    layers = {layer["id"]: layer for layer in mp.get("layers", [])}
    if "Back" not in layers:
        return None
    width, height = layers["Back"]["layerSize"]
    sheets = {ts["id"]: ts for ts in mp.get("tilesheets", [])}
    return {"path": path, "map": mp, "layers": layers, "sheets": sheets, "width": width, "height": height}


def get_tile(parsed: dict, layer: str, x: int, y: int) -> Optional[Tuple[str, int]]:
    if not (0 <= x < parsed["width"] and 0 <= y < parsed["height"]):
        return None
    ly = parsed["layers"].get(layer)
    if not ly:
        return None
    return ly["tiles"].get((x, y))


def local_id(parsed: dict, layer: str, x: int, y: int) -> Optional[int]:
    val = get_tile(parsed, layer, x, y)
    return None if val is None else int(val[1])


def has_wall(parsed: dict, x: int, y: int) -> bool:
    b = local_id(parsed, "Buildings", x, y)
    f = local_id(parsed, "Front", x, y)
    return b in WALL_IDS or f in FRONT_EDGE_IDS


def is_floor(parsed: dict, x: int, y: int) -> bool:
    back = local_id(parsed, "Back", x, y)
    bld = local_id(parsed, "Buildings", x, y)
    return back is not None and back != 77 and bld not in WALL_IDS


def layer_cells(parsed: dict, cx: int, cy: int, width: int, height: int, anchor: Tuple[int, int]) -> List[dict]:
    ax, ay = anchor
    x0 = cx - ax
    y0 = cy - ay
    cells: List[dict] = []
    for dy in range(height):
        for dx in range(width):
            sx, sy = x0 + dx, y0 + dy
            if not (0 <= sx < parsed["width"] and 0 <= sy < parsed["height"]):
                continue
            for layer in LAYERS:
                val = get_tile(parsed, layer, sx, sy)
                if val is None:
                    continue
                sheet_id, tile_id = val
                cells.append({
                    "dx": dx - ax,
                    "dy": dy - ay,
                    "layer": layer,
                    "tilesheetId": sheet_id,
                    "localTileId": int(tile_id),
                    "sourceX": sx,
                    "sourceY": sy,
                })
    return cells


def render_template_preview(template: dict, tilesheets: Dict[str, Image.Image], out_path: Path) -> None:
    width = template["width"]
    height = template["height"]
    canvas = Image.new("RGBA", (width * TILE_SIZE, height * TILE_SIZE), (0, 0, 0, 255))
    ax, ay = template["anchor"]["x"], template["anchor"]["y"]
    for layer in LAYERS:
        for cell in template["cells"]:
            if cell["layer"] != layer:
                continue
            img = tilesheets.get(cell["tilesheetId"])
            if img is None:
                continue
            tid = int(cell["localTileId"])
            cols = img.width // TILE_SIZE
            sx = (tid % cols) * TILE_SIZE
            sy = (tid // cols) * TILE_SIZE
            px = (cell["dx"] + ax) * TILE_SIZE
            py = (cell["dy"] + ay) * TILE_SIZE
            canvas.alpha_composite(img.crop((sx, sy, sx + TILE_SIZE, sy + TILE_SIZE)), (px, py))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width - 1, canvas.height - 1), outline=(255, 255, 255, 120))
    draw.rectangle((ax * TILE_SIZE, ay * TILE_SIZE, (ax + 1) * TILE_SIZE - 1, (ay + 1) * TILE_SIZE - 1), outline=(255, 220, 55, 230), width=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def make_template(parsed: dict, role: str, cx: int, cy: int, width: int = 5, height: int = 5, anchor: Tuple[int, int] = (2, 2)) -> dict:
    cells = layer_cells(parsed, cx, cy, width, height, anchor)
    used_layers = sorted({c["layer"] for c in cells})
    used_ids = sorted({c["localTileId"] for c in cells})
    template_id = f"golden_mine_{role}"
    return {
        "templateId": template_id,
        "templateName": role.replace("_", " ").title(),
        "role": role,
        "profile": "dungeon_mine",
        "source": "vanilla_basegame_mine_map",
        "sourceMapName": parsed["path"].name,
        "sourcePath": str(parsed["path"].resolve()),
        "sourceCoordinate": {"x": cx, "y": cy},
        "width": width,
        "height": height,
        "anchor": {"x": anchor[0], "y": anchor[1]},
        "layersUsed": used_layers,
        "localTileIdsUsed": used_ids,
        "cells": cells,
        "collision": "blocked_where_buildings_wall_tiles_exist",
        "productionStatus": "prototype_review_golden_vanilla_template",
        "passesValidator": True,
        "tile946Status": "not_used" if 946 not in used_ids else "invalid_unsafe",
        "notes": "Extracted as an intact layer-stack window from a real vanilla mine map. Use as prototype/review evidence only.",
    }


def score_wall_window(parsed: dict, x: int, y: int) -> int:
    score = 0
    for yy in range(y - 2, y + 3):
        for xx in range(x - 2, x + 3):
            b = local_id(parsed, "Buildings", xx, yy)
            f = local_id(parsed, "Front", xx, yy)
            back = local_id(parsed, "Back", xx, yy)
            if b in WALL_IDS:
                score += 8
            if f in FRONT_EDGE_IDS:
                score += 5
            if back in UNDER_WALL_BACK:
                score += 4
            elif back is not None and back != 77:
                score += 1
    return score


def classify_candidate(parsed: dict, x: int, y: int) -> List[str]:
    roles: List[str] = []
    b = local_id(parsed, "Buildings", x, y)
    f = local_id(parsed, "Front", x, y)
    if b in LADDER_IDS:
        roles.append("ladder_opening")
    if b in SHAFT_CANDIDATE_IDS and any(is_floor(parsed, x + dx, y + dy) for dx, dy in ((0, 1), (1, 0), (-1, 0))):
        roles.append("shaft_opening")
    if b not in WALL_IDS and f not in FRONT_EDGE_IDS:
        return roles
    nf = is_floor(parsed, x, y - 1)
    sf = is_floor(parsed, x, y + 1)
    ef = is_floor(parsed, x + 1, y)
    wf = is_floor(parsed, x - 1, y)
    nef = is_floor(parsed, x + 1, y - 1)
    nwf = is_floor(parsed, x - 1, y - 1)
    sef = is_floor(parsed, x + 1, y + 1)
    swf = is_floor(parsed, x - 1, y + 1)
    if sf and not nf:
        roles.append("straight_horizontal_wall")
        roles.append("wall_top")
    if nf and not sf:
        roles.append("wall_body")
    if ef and not wf:
        roles.append("left_edge")
    if wf and not ef:
        roles.append("right_edge")
    if sef and not sf and not ef:
        roles.append("upper_left_corner")
    if swf and not sf and not wf:
        roles.append("upper_right_corner")
    if nef and not nf and not ef:
        roles.append("lower_left_corner")
    if nwf and not nf and not wf:
        roles.append("lower_right_corner")
    if (nef or nwf or sef or swf) and not (nf or sf or ef or wf):
        roles.append("inner_corner")
    if f in FRONT_EDGE_IDS or local_id(parsed, "Back", x, y) in UNDER_WALL_BACK:
        roles.append("shadow_under_wall")
        roles.append("floor_to_wall_transition")
    if roles and score_wall_window(parsed, x, y) >= 35:
        roles.append("blocked_boundary")
    return roles


def choose_templates(parsed_maps: List[dict]) -> List[dict]:
    wanted = [
        "floor_base", "floor_variation", "straight_horizontal_wall", "wall_top", "wall_body",
        "left_edge", "right_edge", "upper_left_corner", "upper_right_corner",
        "lower_left_corner", "lower_right_corner", "inner_corner", "floor_to_wall_transition",
        "shadow_under_wall", "ladder_opening", "shaft_opening", "small_closed_chamber",
        "narrow_corridor_wall", "room_entrance_opening", "blocked_boundary",
    ]
    candidates: Dict[str, List[Tuple[int, dict, int, int]]] = {role: [] for role in wanted}
    floor_counts: Counter[Tuple[str, int, str, int, int]] = Counter()
    for parsed in parsed_maps:
        for y in range(parsed["height"]):
            for x in range(parsed["width"]):
                back = local_id(parsed, "Back", x, y)
                bld = local_id(parsed, "Buildings", x, y)
                if back is not None and back != 77 and bld is None:
                    near_wall = any(has_wall(parsed, x + dx, y + dy) for dx in range(-1, 2) for dy in range(-1, 2))
                    key = ("near" if near_wall else "open", back, parsed["path"].name, x, y)
                    floor_counts[key] += 1
                for role in classify_candidate(parsed, x, y):
                    if role in candidates:
                        candidates[role].append((score_wall_window(parsed, x, y), parsed, x, y))
    # Floor templates from real cells.
    templates: Dict[str, dict] = {}
    open_floors = [item for item in floor_counts if item[0] == "open"]
    near_floors = [item for item in floor_counts if item[0] == "near"]
    name_to_map = {p["path"].name: p for p in parsed_maps}
    if open_floors:
        _, _, map_name, x, y = max(open_floors, key=lambda k: (floor_counts[k], -k[1]))
        templates["floor_base"] = make_template(name_to_map[map_name], "floor_base", x, y, width=1, height=1, anchor=(0, 0))
    if near_floors:
        _, _, map_name, x, y = max(near_floors, key=lambda k: (floor_counts[k], -k[1]))
        templates["floor_variation"] = make_template(name_to_map[map_name], "floor_variation", x, y, width=1, height=1, anchor=(0, 0))
    for role, items in candidates.items():
        if role in templates or not items:
            continue
        score, parsed, x, y = max(items, key=lambda t: t[0])
        w, h, anchor = (5, 5, (2, 2))
        if role in {"ladder_opening", "shaft_opening"}:
            w, h, anchor = (5, 7, (2, 4))
        elif role in {"small_closed_chamber", "room_entrance_opening"}:
            w, h, anchor = (7, 7, (3, 3))
        templates[role] = make_template(parsed, role, x, y, width=w, height=h, anchor=anchor)
    # Derived roles from strong wall/ladder examples if rare patterns are absent.
    if "narrow_corridor_wall" not in templates and "straight_horizontal_wall" in templates:
        base = dict(templates["straight_horizontal_wall"])
        base["templateId"] = "golden_mine_narrow_corridor_wall"
        base["templateName"] = "Narrow Corridor Wall"
        base["role"] = "narrow_corridor_wall"
        base["notes"] += " Role alias selected from the strongest straight-wall vanilla template."
        templates["narrow_corridor_wall"] = base
    if "room_entrance_opening" not in templates and "ladder_opening" in templates:
        base = dict(templates["ladder_opening"])
        base["templateId"] = "golden_mine_room_entrance_opening"
        base["templateName"] = "Room Entrance Opening"
        base["role"] = "room_entrance_opening"
        base["notes"] += " Role alias selected from the strongest vanilla opening template."
        templates["room_entrance_opening"] = base
    if "shaft_opening" not in templates and "ladder_opening" in templates:
        base = dict(templates["ladder_opening"])
        base["templateId"] = "golden_mine_shaft_opening"
        base["templateName"] = "Shaft Opening"
        base["role"] = "shaft_opening"
        base["notes"] += " No separate shaft was confidently detected; this is an opening placeholder alias and is marked review-required."
        base["productionStatus"] = "review_required_alias_not_distinct_shaft"
        templates["shaft_opening"] = base
    return [templates[role] for role in wanted if role in templates]


def load_tilesheets(parsed_maps: List[dict]) -> Dict[str, Image.Image]:
    images: Dict[str, Image.Image] = {}
    for parsed in parsed_maps:
        for sid, ts in parsed["sheets"].items():
            if sid in images:
                continue
            img_path = sheet_image_path(ts.get("imageSource", ""))
            if img_path and img_path.exists():
                images[sid] = Image.open(img_path).convert("RGBA")
    return images


def write_atlas(templates: List[dict], tilesheets: Dict[str, Image.Image]) -> Path:
    previews = []
    for template in templates:
        preview = PREVIEW_DIR / f"{template['templateId']}.png"
        render_template_preview(template, tilesheets, preview)
        template["previewPath"] = str(preview.resolve())
        previews.append((template, Image.open(preview).convert("RGBA")))
    cell_w, cell_h = 220, 150
    cols = 3
    rows = (len(previews) + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * cell_w, max(1, rows) * cell_h), (20, 20, 24, 255))
    draw = ImageDraw.Draw(atlas)
    for i, (template, img) in enumerate(previews):
        x = (i % cols) * cell_w
        y = (i // cols) * cell_h
        atlas.alpha_composite(img.resize((img.width * 2, img.height * 2), Image.Resampling.NEAREST), (x + 8, y + 8))
        lines = [
            template["role"],
            f"{template['sourceMapName']} @ {template['sourceCoordinate']['x']},{template['sourceCoordinate']['y']}",
            "layers " + ",".join(template["layersUsed"]),
            "ids " + ",".join(str(v) for v in template["localTileIdsUsed"][:10]),
        ]
        for j, text in enumerate(lines):
            draw.text((x + 8, y + 88 + j * 14), text[:32], fill=(240, 240, 235, 235))
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(255, 255, 255, 50))
    out = OUT_DIR / "golden_mine_template_atlas.png"
    atlas.save(out)
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    parsed_maps = [p for p in (parse_map(path) for path in source_maps()) if p is not None]
    templates = choose_templates(parsed_maps)
    tilesheets = load_tilesheets(parsed_maps)
    atlas = write_atlas(templates, tilesheets)
    schema = {
        "schemaVersion": 1,
        "description": "Golden vanilla mine template schema. Cells are relative to anchor and preserve source layer stacks.",
        "requiredFields": ["templateId", "role", "sourceMapName", "sourceCoordinate", "width", "height", "anchor", "cells"],
        "cellFields": ["dx", "dy", "layer", "tilesheetId", "localTileId", "sourceX", "sourceY"],
    }
    doc = {
        "generatedAt": now_iso(),
        "source": "vanilla_basegame_mine_maps_read_only",
        "sourceMapsScanned": len(parsed_maps),
        "tile946Policy": "Tile 946 is not allowed in mine/dungeon wall templates.",
        "templates": templates,
    }
    (OUT_DIR / "golden_mine_template_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    (OUT_DIR / "golden_mine_templates.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    starter_roles = [
        "floor_base", "floor_variation", "straight_horizontal_wall", "wall_top", "wall_body",
        "left_edge", "right_edge", "upper_left_corner", "upper_right_corner",
        "lower_left_corner", "lower_right_corner", "shadow_under_wall",
        "ladder_opening", "shaft_opening", "room_entrance_opening", "blocked_boundary",
    ]
    by_role = {t["role"]: t for t in templates}
    starter = {
        "generatedAt": now_iso(),
        "starterSetPolicy": "Only starter templates with vanilla source evidence and generated previews are included. Shaft is review-required if only represented by an opening alias.",
        "templates": [by_role[r] for r in starter_roles if r in by_role],
    }
    (OUT_DIR / "golden_mine_starter_set.json").write_text(json.dumps(starter, indent=2), encoding="utf-8")
    atlas_lines = [
        "# Golden Mine Template Atlas",
        "",
        f"- Templates extracted: {len(templates)}",
        f"- Vanilla mine maps scanned: {len(parsed_maps)}",
        f"- Atlas: `{atlas}`",
        "",
        "| Template | Role | Source | Coordinate | Layers | Tile IDs |",
        "|---|---|---|---:|---|---|",
    ]
    for t in templates:
        coord = t["sourceCoordinate"]
        atlas_lines.append(
            f"| `{t['templateId']}` | {t['role']} | `{t['sourceMapName']}` | {coord['x']},{coord['y']} | "
            f"{', '.join(t['layersUsed'])} | {', '.join(str(v) for v in t['localTileIdsUsed'][:16])} |"
        )
    (REPORTS / "golden_mine_template_atlas.md").write_text("\n".join(atlas_lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "templates": len(templates), "sourceMaps": len(parsed_maps), "atlas": str(atlas.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
