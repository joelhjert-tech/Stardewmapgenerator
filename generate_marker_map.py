#!/usr/bin/env python3
"""Generate a marker-only semantic test map."""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw

from validate_out_of_bounds import check_out_of_bounds, errors_and_warnings
from validate_stylepacks import validate_all


TOOL_ROOT = Path(__file__).resolve().parent
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"
OUT_DIR = TOOL_ROOT / "generated_maps" / "marker_tests"
REPORT_DIR = TOOL_ROOT / "reports"
WIDTH = 48
HEIGHT = 48
TILE_SIZE = 16
MARKER_TILE_COLUMNS = 5
FULL_LAYOUT_STEM = "complete_test_map_48x48"
GENERATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
DEFAULT_SEED = int(os.environ.get("TMA_MARKER_SEED", "24061477"))


@dataclass(frozen=True)
class LayoutProfile:
    profile_id: str
    layout_family: str
    description: str
    entrance: tuple[int, int]
    exit: tuple[int, int]
    edge_exits_allowed: bool
    output_subdir: str
    full_layout_stem: str


LAYOUT_PROFILES = {
    "outdoor": LayoutProfile(
        profile_id="outdoor",
        layout_family="outdoor",
        description="Outdoor forest/maze marker layout with irregular borders and protected near-border entrance/exit capsules.",
        entrance=(24, 46),
        exit=(24, 1),
        edge_exits_allowed=False,
        output_subdir="outdoor",
        full_layout_stem="complete_test_map_48x48_outdoor",
    ),
    "indoor": LayoutProfile(
        profile_id="indoor",
        layout_family="indoor",
        description="Indoor marker layout with sealed exterior walls, connected rooms, corridors, and interior door markers.",
        entrance=(24, 45),
        exit=(24, 3),
        edge_exits_allowed=False,
        output_subdir="indoor",
        full_layout_stem="complete_test_map_48x48_indoor",
    ),
    "dungeon": LayoutProfile(
        profile_id="dungeon",
        layout_family="dungeon",
        description="Dungeon/mine marker layout with sealed cave boundary, irregular cave rooms, connected tunnels, ladder, treasure, and spawn markers.",
        entrance=(24, 44),
        exit=(24, 3),
        edge_exits_allowed=False,
        output_subdir="dungeon",
        full_layout_stem="complete_test_map_48x48_dungeon",
    ),
}
LAYOUT_ALIASES = {"mine": "dungeon"}

CHARS = {
    "marker_ground": ".",
    "marker_cave_floor": ",",
    "marker_wall": "#",
    "marker_rock_wall": "r",
    "marker_cave_wall": "R",
    "marker_path": "+",
    "marker_entrance": "E",
    "marker_exit": "X",
    "marker_ladder": "L",
    "marker_treasure": "$",
    "marker_monster_spawn": "M",
    "marker_ore_spawn": "*",
    "marker_forage_spawn": "f",
    "marker_decoration_zone": "d",
    "marker_protected": "p",
    "marker_water": "~",
    "marker_blocked": "B",
    "marker_wall_body": "b",
    "marker_wall_top": "t",
    "marker_corner": "c",
    "marker_edge": "e",
    "marker_transition": "=",
    "marker_overlay": "o",
}
PASSABLE = {
    "marker_ground",
    "marker_cave_floor",
    "marker_path",
    "marker_entrance",
    "marker_exit",
    "marker_ladder",
    "marker_treasure",
    "marker_monster_spawn",
    "marker_ore_spawn",
    "marker_forage_spawn",
    "marker_decoration_zone",
    "marker_protected",
}
EDGE_EXIT_ROLES = {"marker_entrance", "marker_exit"}
STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
STRUCTURAL_MARKER_ROLES = {"marker_wall", "marker_rock_wall", "marker_cave_wall", "marker_wall_body", "marker_corner", "marker_edge", "marker_blocked"}
TECHNICAL_PATH_MARKER_ROLES = {"marker_path", "marker_entrance", "marker_exit", "marker_ladder", "marker_treasure", "marker_monster_spawn", "marker_ore_spawn", "marker_forage_spawn"}
MARKER_COLORS = {
    "marker_ground": (88, 148, 83, 255),
    "marker_cave_floor": (91, 82, 70, 255),
    "marker_wall": (61, 64, 71, 255),
    "marker_rock_wall": (54, 55, 62, 255),
    "marker_cave_wall": (73, 71, 76, 255),
    "marker_wall_top": (109, 105, 116, 255),
    "marker_wall_body": (78, 77, 86, 255),
    "marker_corner": (128, 92, 78, 255),
    "marker_edge": (94, 112, 92, 255),
    "marker_transition": (190, 157, 79, 255),
    "marker_path": (181, 141, 81, 255),
    "marker_entrance": (73, 139, 190, 255),
    "marker_exit": (192, 88, 82, 255),
    "marker_ladder": (219, 186, 78, 255),
    "marker_treasure": (232, 185, 67, 255),
    "marker_monster_spawn": (186, 65, 87, 255),
    "marker_ore_spawn": (117, 150, 189, 255),
    "marker_forage_spawn": (126, 169, 95, 255),
    "marker_decoration_zone": (186, 89, 160, 255),
    "marker_blocked": (31, 35, 42, 255),
    "marker_protected": (83, 177, 164, 255),
    "marker_water": (57, 122, 191, 255),
    "marker_overlay": (122, 79, 165, 255),
}
MARKER_ROLE_DESCRIPTIONS = {
    "marker_ground": "walkable base ground marker",
    "marker_cave_floor": "walkable cave floor marker",
    "marker_wall": "generic blocking wall marker",
    "marker_rock_wall": "blocking rock wall marker",
    "marker_cave_wall": "blocking cave wall marker",
    "marker_wall_top": "front/top wall marker",
    "marker_wall_body": "blocking wall body marker",
    "marker_corner": "wall corner marker",
    "marker_edge": "wall edge or cap marker",
    "marker_transition": "terrain transition marker",
    "marker_path": "walkable path marker",
    "marker_entrance": "walkable entrance marker",
    "marker_exit": "walkable exit marker",
    "marker_ladder": "reachable ladder or floor transition marker",
    "marker_treasure": "reachable treasure/chest marker",
    "marker_monster_spawn": "reachable monster spawn marker",
    "marker_ore_spawn": "reachable ore spawn marker",
    "marker_forage_spawn": "reachable forage/resource spawn marker",
    "marker_decoration_zone": "decoration placement zone marker",
    "marker_blocked": "blocked cell marker",
    "marker_protected": "protected walkable zone marker",
    "marker_water": "water marker",
    "marker_overlay": "AlwaysFront overlay marker",
}


def in_bounds(x: int, y: int) -> bool:
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


def neighbors4(x: int, y: int):
    for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny):
            yield nx, ny


def is_edge(x: int, y: int, width: int = WIDTH, height: int = HEIGHT) -> bool:
    return x == 0 or y == 0 or x == width - 1 or y == height - 1


def protected_tiles() -> set[tuple[int, int]]:
    result = set()
    for cx, cy in [(24, 46), (24, 1)]:
        for y in range(cy - 3, cy + 4):
            for x in range(cx - 3, cx + 4):
                if in_bounds(x, y) and abs(x - cx) + abs(y - cy) <= 4:
                    result.add((x, y))
    return result


def protected_tiles_for_points(points: list[tuple[int, int]], radius: int = 4) -> set[tuple[int, int]]:
    result = set()
    for cx, cy in points:
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if in_bounds(x, y) and abs(x - cx) + abs(y - cy) <= radius:
                    result.add((x, y))
    return result


def output_dir_for_profile(profile: LayoutProfile) -> Path:
    return OUT_DIR / profile.output_subdir


def connected_between(grid: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> bool:
    width = len(grid[0])
    height = len(grid)
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return True
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in seen or grid[ny][nx] not in PASSABLE:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return False


def connected(grid: list[list[str]]) -> bool:
    return connected_between(grid, (24, 46), (24, 1))


def wall_like(grid: list[list[str]], x: int, y: int) -> bool:
    if not in_bounds(x, y):
        return False
    return grid[y][x] in STRUCTURAL_MARKER_ROLES


def marker_wall_shape(grid: list[list[str]], x: int, y: int) -> str:
    role = grid[y][x]
    if role == "marker_blocked":
        return "marker_blocked"
    if role in {"marker_rock_wall", "marker_cave_wall"}:
        return role
    if role in {"marker_wall_body", "marker_corner", "marker_edge"}:
        return role
    cardinal = {
        "N": wall_like(grid, x, y - 1),
        "E": wall_like(grid, x + 1, y),
        "S": wall_like(grid, x, y + 1),
        "W": wall_like(grid, x - 1, y),
    }
    count = sum(1 for value in cardinal.values() if value)
    if count == 4:
        return "marker_wall_body"
    if count == 2 and not ((cardinal["N"] and cardinal["S"]) or (cardinal["E"] and cardinal["W"])):
        return "marker_corner"
    return "marker_edge"


def is_front_exposed_wall(grid: list[list[str]], x: int, y: int) -> bool:
    return wall_like(grid, x, y) and in_bounds(x, y + 1) and grid[y + 1][x] in PASSABLE


def build_full_layout_layers(grid: list[list[str]], marker_tiles: dict[str, int]) -> dict[str, list[int]]:
    layers = {layer: [0] * (WIDTH * HEIGHT) for layer in STANDARD_LAYERS}
    ground_gid = marker_tiles["marker_ground"]
    wall_gid = marker_tiles["marker_wall"]
    wall_top_gid = marker_tiles["marker_wall_top"]
    overlay_gid = marker_tiles["marker_overlay"]

    for y, row in enumerate(grid):
        for x, role in enumerate(row):
            index = y * WIDTH + x
            if role in STRUCTURAL_MARKER_ROLES:
                wall_role = marker_wall_shape(grid, x, y)
                layers["Back"][index] = ground_gid
                layers["Buildings"][index] = marker_tiles.get(wall_role, wall_gid)
                if is_front_exposed_wall(grid, x, y):
                    layers["Front"][index] = wall_top_gid
                if y < 6 and role != "marker_blocked":
                    layers["AlwaysFront"][index] = overlay_gid
                continue

            if role == "marker_decoration_zone":
                layers["Back"][index] = ground_gid
                layers["Front"][index] = marker_tiles["marker_decoration_zone"]
                continue

            if role in TECHNICAL_PATH_MARKER_ROLES:
                layers["Back"][index] = marker_tiles.get("marker_cave_floor" if role in {"marker_ladder", "marker_monster_spawn", "marker_ore_spawn", "marker_treasure", "marker_forage_spawn"} else role, ground_gid)
            else:
                layers["Back"][index] = marker_tiles.get(role, ground_gid)
            if role in TECHNICAL_PATH_MARKER_ROLES:
                layers["Paths"][index] = marker_tiles.get(role, marker_tiles["marker_path"])
    return layers


def expanded_marker_tiles(base_marker_tiles: dict[str, int], grid: list[list[str]]) -> dict[str, int]:
    marker_tiles = {key: int(value) for key, value in base_marker_tiles.items()}
    roles_in_grid = sorted({role for row in grid for role in row if str(role).startswith("marker_")})
    next_gid = max(marker_tiles.values(), default=3000) + 1
    for role in roles_in_grid:
        if role not in marker_tiles:
            marker_tiles[role] = next_gid
            next_gid += 1
    return marker_tiles


def marker_tilesheet_geometry(marker_tiles: dict[str, int]) -> tuple[int, int, int, int]:
    firstgid = min(int(gid) for gid in marker_tiles.values())
    tilecount = max(int(gid) for gid in marker_tiles.values()) - firstgid + 1
    columns = min(MARKER_TILE_COLUMNS, tilecount)
    rows = (tilecount + columns - 1) // columns
    return firstgid, tilecount, columns, rows


def write_marker_tilesheet(marker_tiles: dict[str, int], out_dir: Path) -> Path:
    firstgid, tilecount, columns, rows = marker_tilesheet_geometry(marker_tiles)
    image_path = out_dir / "semantic_marker_tiles.png"
    image = Image.new("RGBA", (columns * TILE_SIZE, rows * TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for role, gid in marker_tiles.items():
        local = int(gid) - firstgid
        x = (local % columns) * TILE_SIZE
        y = (local // columns) * TILE_SIZE
        color = MARKER_COLORS.get(role, (255, 0, 255, 255))
        draw.rectangle([x, y, x + TILE_SIZE - 1, y + TILE_SIZE - 1], fill=color)
        draw.rectangle([x, y, x + TILE_SIZE - 1, y + TILE_SIZE - 1], outline=(24, 26, 31, 255))
    image.save(image_path)
    return image_path


def write_full_layout_preview(grid: list[list[str]], out_dir: Path, full_layout_stem: str) -> Path:
    preview_path = out_dir / f"{full_layout_stem}_preview.png"
    image = Image.new("RGBA", (WIDTH * TILE_SIZE, HEIGHT * TILE_SIZE), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, role in enumerate(row):
            color = MARKER_COLORS.get(role, (255, 0, 255, 255))
            left = x * TILE_SIZE
            top = y * TILE_SIZE
            draw.rectangle([left, top, left + TILE_SIZE - 1, top + TILE_SIZE - 1], fill=color)
    for x in range(WIDTH + 1):
        draw.line([(x * TILE_SIZE, 0), (x * TILE_SIZE, HEIGHT * TILE_SIZE)], fill=(0, 0, 0, 55))
    for y in range(HEIGHT + 1):
        draw.line([(0, y * TILE_SIZE), (WIDTH * TILE_SIZE, y * TILE_SIZE)], fill=(0, 0, 0, 55))
    image.save(preview_path)
    return preview_path


def write_full_layout_tmj(stylepack: dict, grid: list[list[str]], profile: LayoutProfile, out_dir: Path) -> dict:
    marker_tiles = expanded_marker_tiles(stylepack.get("markerTiles") or {}, grid)
    required = {
        "marker_ground",
        "marker_wall",
        "marker_wall_top",
        "marker_wall_body",
        "marker_corner",
        "marker_edge",
        "marker_path",
        "marker_entrance",
        "marker_exit",
        "marker_decoration_zone",
        "marker_blocked",
        "marker_protected",
        "marker_water",
        "marker_overlay",
    }
    missing = sorted(required - set(marker_tiles))
    if missing:
        raise ValueError(f"Stylepack markerTiles missing required marker roles: {', '.join(missing)}")

    tilesheet_path = write_marker_tilesheet(marker_tiles, out_dir)
    preview_path = write_full_layout_preview(grid, out_dir, profile.full_layout_stem)
    firstgid, tilecount, columns, rows = marker_tilesheet_geometry(marker_tiles)
    layers = build_full_layout_layers(grid, marker_tiles)
    tmj_layers = []
    for layer_id, layer_name in enumerate(STANDARD_LAYERS, start=1):
        tmj_layers.append(
            {
                "id": layer_id,
                "name": layer_name,
                "type": "tilelayer",
                "width": WIDTH,
                "height": HEIGHT,
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": True,
                "data": layers[layer_name],
            }
        )
    tmj = {
        "type": "map",
        "version": "1.10",
        "tiledversion": "1.10.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "compressionlevel": -1,
        "infinite": False,
        "width": WIDTH,
        "height": HEIGHT,
        "tilewidth": TILE_SIZE,
        "tileheight": TILE_SIZE,
        "nextlayerid": len(tmj_layers) + 1,
        "nextobjectid": 1,
        "properties": [
            {"name": "generationMode", "type": "string", "value": "marker_only_full_layout"},
            {"name": "layoutProfile", "type": "string", "value": profile.profile_id},
            {"name": "layoutFamily", "type": "string", "value": profile.layout_family},
            {"name": "productionMap", "type": "bool", "value": False},
            {"name": "usesFinalVisualTileIds", "type": "bool", "value": False},
            {"name": "tile946BlockingRolesUsed", "type": "bool", "value": False},
            {"name": "stylePackId", "type": "string", "value": stylepack["stylePackId"]},
        ],
        "tilesets": [
            {
                "firstgid": firstgid,
                "name": "semantic_marker_tiles",
                "image": tilesheet_path.name,
                "imagewidth": columns * TILE_SIZE,
                "imageheight": rows * TILE_SIZE,
                "margin": 0,
                "spacing": 0,
                "tilewidth": TILE_SIZE,
                "tileheight": TILE_SIZE,
                "tilecount": tilecount,
                "columns": columns,
            }
        ],
        "layers": tmj_layers,
    }
    tmj_path = out_dir / f"{profile.full_layout_stem}.tmj"
    tmj_path.write_text(json.dumps(tmj, indent=2) + "\n", encoding="utf-8")
    tmx_path = write_full_layout_tmx(stylepack, layers, marker_tiles, tilesheet_path, profile, out_dir)

    non_empty_by_layer = {layer: sum(1 for gid in data if gid) for layer, data in layers.items()}
    return {
        "tmjPath": str(tmj_path.resolve()),
        "tmxPath": str(tmx_path.resolve()),
        "markerTilesheetPath": str(tilesheet_path.resolve()),
        "previewPath": str(preview_path.resolve()),
        "tilesetFirstGid": firstgid,
        "tilesetTileCount": tilecount,
        "nonEmptyByLayer": non_empty_by_layer,
    }


def csv_layer_data(data: list[int]) -> str:
    rows = []
    for y in range(HEIGHT):
        start = y * WIDTH
        rows.append(",".join(str(value) for value in data[start : start + WIDTH]))
    return ",\n".join(rows)


def tmx_property(name: str, value: object, prop_type: str | None = None) -> str:
    type_attr = f' type="{prop_type}"' if prop_type else ""
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)
    return f'  <property name="{escape(name)}"{type_attr} value="{escape(rendered)}"/>'


def write_full_layout_tmx(
    stylepack: dict,
    layers: dict[str, list[int]],
    marker_tiles: dict[str, int],
    tilesheet_path: Path,
    profile: LayoutProfile,
    out_dir: Path,
) -> Path:
    firstgid, tilecount, columns, rows = marker_tilesheet_geometry(marker_tiles)
    tmx_path = out_dir / f"{profile.full_layout_stem}.tmx"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<map version="1.10" tiledversion="1.10.2" orientation="orthogonal" renderorder="right-down" width="{WIDTH}" height="{HEIGHT}" tilewidth="{TILE_SIZE}" tileheight="{TILE_SIZE}" infinite="0" nextlayerid="{len(STANDARD_LAYERS) + 1}" nextobjectid="1">',
        " <properties>",
        tmx_property("generationMode", "marker_only_full_layout"),
        tmx_property("layoutProfile", profile.profile_id),
        tmx_property("layoutFamily", profile.layout_family),
        tmx_property("productionMap", False, "bool"),
        tmx_property("usesFinalVisualTileIds", False, "bool"),
        tmx_property("tile946BlockingRolesUsed", False, "bool"),
        tmx_property("stylePackId", stylepack["stylePackId"]),
        " </properties>",
        f' <tileset firstgid="{firstgid}" name="semantic_marker_tiles" tilewidth="{TILE_SIZE}" tileheight="{TILE_SIZE}" tilecount="{tilecount}" columns="{columns}">',
        f'  <image source="{escape(tilesheet_path.name)}" width="{columns * TILE_SIZE}" height="{rows * TILE_SIZE}"/>',
    ]
    for role, gid in sorted(marker_tiles.items(), key=lambda item: int(item[1])):
        local_id = int(gid) - firstgid
        lines.extend(
            [
                f'  <tile id="{local_id}" type="{escape(role)}">',
                "   <properties>",
                tmx_property("markerRole", role),
                tmx_property("description", MARKER_ROLE_DESCRIPTIONS.get(role, role)),
                tmx_property("productionTile", False, "bool"),
                "   </properties>",
                "  </tile>",
            ]
        )
    lines.append(" </tileset>")
    for layer_id, layer_name in enumerate(STANDARD_LAYERS, start=1):
        lines.extend(
            [
                f' <layer id="{layer_id}" name="{layer_name}" width="{WIDTH}" height="{HEIGHT}">',
                '  <data encoding="csv">',
                csv_layer_data(layers[layer_name]),
                "  </data>",
                " </layer>",
            ]
        )
    lines.append("</map>")
    tmx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmx_path


def edge_passable_tiles(grid: list[list[str]]) -> list[dict]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    result = []
    for y, row in enumerate(grid):
        for x, role in enumerate(row):
            if is_edge(x, y, width, height) and role in PASSABLE:
                result.append({"x": x, "y": y, "role": role})
    return result


def seal_map_edges_except_intended_exits(
    grid: list[list[str]],
    intended_exit_tiles: set[tuple[int, int]],
) -> dict:
    """Seal passable edge leakage while preserving explicit edge exit markers only."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    sealed = []
    preserved = []
    for y, row in enumerate(grid):
        for x, role in enumerate(row):
            if not is_edge(x, y, width, height):
                continue
            if (x, y) in intended_exit_tiles and role in EDGE_EXIT_ROLES:
                preserved.append({"x": x, "y": y, "role": role})
                continue
            if role in PASSABLE:
                sealed.append({"x": x, "y": y, "oldRole": role, "newRole": "marker_wall"})
                grid[y][x] = "marker_wall"
    return {
        "edgeSealingApplied": True,
        "intendedExitTiles": [{"x": x, "y": y} for x, y in sorted(intended_exit_tiles)],
        "preservedEdgeExitTiles": preserved,
        "sealedEdgeTiles": sealed,
        "passableEdgeTilesRemaining": edge_passable_tiles(grid),
    }


def build_outdoor_grid(seed: int, profile: LayoutProfile = LAYOUT_PROFILES["outdoor"]) -> tuple[list[list[str]], dict, dict]:
    rng = random.Random(seed)
    grid = [["marker_ground" for _ in range(WIDTH)] for _ in range(HEIGHT)]
    protected = protected_tiles()

    left_depth = right_depth = 3
    for y in range(HEIGHT):
        if rng.random() < 0.55:
            left_depth += rng.choice([-1, 0, 1])
        if rng.random() < 0.55:
            right_depth += rng.choice([-1, 0, 1])
        left_depth = max(2, min(5, left_depth))
        right_depth = max(2, min(5, right_depth))
        for x in range(left_depth):
            grid[y][x] = "marker_wall"
        for x in range(WIDTH - right_depth, WIDTH):
            grid[y][x] = "marker_wall"

    top_depth = bottom_depth = 3
    for x in range(WIDTH):
        if rng.random() < 0.55:
            top_depth += rng.choice([-1, 0, 1])
        if rng.random() < 0.55:
            bottom_depth += rng.choice([-1, 0, 1])
        top_depth = max(2, min(5, top_depth))
        bottom_depth = max(2, min(5, bottom_depth))
        for y in range(top_depth):
            if not (21 <= x <= 27 and y <= 4):
                grid[y][x] = "marker_wall"
        for y in range(HEIGHT - bottom_depth, HEIGHT):
            if not (21 <= x <= 27 and y >= HEIGHT - 5):
                grid[y][x] = "marker_wall"

    route = set()
    x = 24
    for y in range(46, 0, -1):
        if y % 4 == 0:
            x += rng.choice([-1, 0, 0, 1])
            x = max(8, min(40, x))
        if y < 8:
            x += -1 if x > 24 else 1 if x < 24 else 0
        for dx in [-1, 0, 1]:
            for dy in [0, 1]:
                px, py = x + dx, y + dy
                if in_bounds(px, py):
                    grid[py][px] = "marker_path"
                    route.add((px, py))

    accepted_segments = 0
    for _ in range(80):
        snapshot = [row[:] for row in grid]
        vertical = rng.random() < 0.5
        length = rng.randint(4, 12)
        if vertical:
            sx = rng.randrange(7, WIDTH - 7)
            sy = rng.randrange(7, HEIGHT - 8)
            coords = [(sx, y) for y in range(sy, min(HEIGHT - 5, sy + length))]
        else:
            sy = rng.randrange(7, HEIGHT - 7)
            sx = rng.randrange(7, WIDTH - 8)
            coords = [(x, sy) for x in range(sx, min(WIDTH - 5, sx + length))]
        for cx, cy in coords:
            if (cx, cy) in protected or (cx, cy) in route:
                continue
            grid[cy][cx] = "marker_wall"
        if connected(grid):
            accepted_segments += 1
        else:
            grid = snapshot
        if accepted_segments >= 28:
            break

    for x, y in protected:
        if grid[y][x] != "marker_path":
            grid[y][x] = "marker_protected"
    entrance_x, entrance_y = profile.entrance
    exit_x, exit_y = profile.exit
    grid[entrance_y][entrance_x] = "marker_entrance"
    grid[exit_y][exit_x] = "marker_exit"
    intended_exit_tiles = {profile.entrance, profile.exit} if profile.edge_exits_allowed else set()
    edge_sealing = seal_map_edges_except_intended_exits(grid, intended_exit_tiles)

    for y in range(2, HEIGHT - 2):
        for x in range(2, WIDTH - 2):
            if grid[y][x] == "marker_ground" and any(grid[ny][nx] == "marker_wall" for nx, ny in neighbors4(x, y)):
                if rng.random() < 0.08:
                    grid[y][x] = "marker_decoration_zone"

    stats = {
        "layoutProfile": profile.profile_id,
        "layoutFamily": profile.layout_family,
        "protectedTileCount": len(protected),
        "routeTileCount": len(route),
        "acceptedWallSegments": accepted_segments,
        "wallCount": sum(cell == "marker_wall" for row in grid for cell in row),
        "decorationZoneCount": sum(cell == "marker_decoration_zone" for row in grid for cell in row),
        "sealedEdgeTileCount": len(edge_sealing["sealedEdgeTiles"]),
        "passableEdgeTilesRemaining": len(edge_sealing["passableEdgeTilesRemaining"]),
    }
    return grid, stats, edge_sealing


def carve_room(grid: list[list[str]], x1: int, y1: int, x2: int, y2: int, floor_role: str = "marker_ground") -> None:
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            if in_bounds(x, y):
                grid[y][x] = floor_role


def carve_corridor(grid: list[list[str]], start: tuple[int, int], end: tuple[int, int], role: str = "marker_path") -> set[tuple[int, int]]:
    sx, sy = start
    ex, ey = end
    carved = set()
    x_step = 1 if ex >= sx else -1
    for x in range(sx, ex + x_step, x_step):
        if in_bounds(x, sy):
            grid[sy][x] = role
            carved.add((x, sy))
    y_step = 1 if ey >= sy else -1
    for y in range(sy, ey + y_step, y_step):
        if in_bounds(ex, y):
            grid[y][ex] = role
            carved.add((ex, y))
    return carved


def build_indoor_grid(seed: int, profile: LayoutProfile = LAYOUT_PROFILES["indoor"]) -> tuple[list[list[str]], dict, dict]:
    rng = random.Random(seed + 101)
    grid = [["marker_wall" for _ in range(WIDTH)] for _ in range(HEIGHT)]
    room_rects = [
        (4, 4, 17, 16),
        (20, 4, 43, 16),
        (4, 19, 20, 32),
        (23, 19, 43, 32),
        (9, 35, 38, 44),
    ]
    room_centers = []
    for x1, y1, x2, y2 in room_rects:
        carve_room(grid, x1, y1, x2, y2)
        room_centers.append(((x1 + x2) // 2, (y1 + y2) // 2))

    corridor_tiles = set()
    for start, end in zip(room_centers, room_centers[1:]):
        corridor_tiles.update(carve_corridor(grid, start, end))
    corridor_tiles.update(carve_corridor(grid, profile.entrance, room_centers[-1]))
    corridor_tiles.update(carve_corridor(grid, room_centers[1], profile.exit))

    protected = protected_tiles_for_points([profile.entrance, profile.exit], radius=3)
    for x, y in protected:
        if not is_edge(x, y):
            grid[y][x] = "marker_protected"
    entrance_x, entrance_y = profile.entrance
    exit_x, exit_y = profile.exit
    grid[entrance_y][entrance_x] = "marker_entrance"
    grid[exit_y][exit_x] = "marker_exit"

    accepted_partitions = 0
    for _ in range(55):
        snapshot = [row[:] for row in grid]
        room = rng.choice(room_rects)
        x1, y1, x2, y2 = room
        vertical = rng.random() < 0.5
        if vertical and x2 - x1 > 7:
            x = rng.randrange(x1 + 3, x2 - 2)
            door_y = rng.randrange(y1 + 2, y2 - 1)
            for y in range(y1 + 1, y2):
                if y != door_y and (x, y) not in protected:
                    grid[y][x] = "marker_wall"
        elif not vertical and y2 - y1 > 7:
            y = rng.randrange(y1 + 3, y2 - 2)
            door_x = rng.randrange(x1 + 2, x2 - 1)
            for x in range(x1 + 1, x2):
                if x != door_x and (x, y) not in protected:
                    grid[y][x] = "marker_wall"
        if connected_between(grid, profile.entrance, profile.exit):
            accepted_partitions += 1
        else:
            grid = snapshot
        if accepted_partitions >= 12:
            break

    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            if grid[y][x] == "marker_ground" and any(grid[ny][nx] == "marker_wall" for nx, ny in neighbors4(x, y)):
                if rng.random() < 0.05:
                    grid[y][x] = "marker_decoration_zone"

    edge_sealing = seal_map_edges_except_intended_exits(grid, set())
    stats = {
        "layoutProfile": profile.profile_id,
        "layoutFamily": profile.layout_family,
        "roomCount": len(room_rects),
        "protectedTileCount": len(protected),
        "corridorTileCount": len(corridor_tiles),
        "acceptedPartitionSegments": accepted_partitions,
        "wallCount": sum(cell == "marker_wall" for row in grid for cell in row),
        "decorationZoneCount": sum(cell == "marker_decoration_zone" for row in grid for cell in row),
        "sealedEdgeTileCount": len(edge_sealing["sealedEdgeTiles"]),
        "passableEdgeTilesRemaining": len(edge_sealing["passableEdgeTilesRemaining"]),
    }
    return grid, stats, edge_sealing


def carve_cave_blob(grid: list[list[str]], center: tuple[int, int], rx: int, ry: int, rng: random.Random) -> set[tuple[int, int]]:
    cx, cy = center
    carved = set()
    for y in range(max(1, cy - ry - 2), min(HEIGHT - 1, cy + ry + 3)):
        for x in range(max(1, cx - rx - 2), min(WIDTH - 1, cx + rx + 3)):
            nx = (x - cx) / max(1, rx)
            ny = (y - cy) / max(1, ry)
            wobble = rng.uniform(-0.18, 0.22)
            if nx * nx + ny * ny <= 1.0 + wobble:
                grid[y][x] = "marker_cave_floor"
                carved.add((x, y))
    return carved


def thicken_path(grid: list[list[str]], coords: set[tuple[int, int]], role: str = "marker_path") -> set[tuple[int, int]]:
    carved = set()
    for x, y in coords:
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1)]:
            nx, ny = x + dx, y + dy
            if 1 <= nx < WIDTH - 1 and 1 <= ny < HEIGHT - 1:
                grid[ny][nx] = role
                carved.add((nx, ny))
    return carved


def reachable_tiles(grid: list[list[str]], start: tuple[int, int]) -> set[tuple[int, int]]:
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        for nx, ny in neighbors4(x, y):
            if (nx, ny) in seen or grid[ny][nx] not in PASSABLE:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


def build_dungeon_grid(seed: int, profile: LayoutProfile = LAYOUT_PROFILES["dungeon"]) -> tuple[list[list[str]], dict, dict]:
    rng = random.Random(seed + 202)
    grid = [["marker_rock_wall" for _ in range(WIDTH)] for _ in range(HEIGHT)]
    room_specs = [
        ((10, 10), 6, 5),
        ((27, 8), 8, 4),
        ((38, 18), 6, 7),
        ((28, 29), 8, 6),
        ((12, 34), 7, 6),
        ((20, 21), 6, 5),
    ]
    cave_floor = set()
    centers = []
    for center, rx, ry in room_specs:
        cave_floor.update(carve_cave_blob(grid, center, rx, ry, rng))
        centers.append(center)

    tunnel_tiles = set()
    for start, end in zip(centers, centers[1:]):
        tunnel_tiles.update(thicken_path(grid, carve_corridor(grid, start, end, "marker_path")))
    tunnel_tiles.update(thicken_path(grid, carve_corridor(grid, profile.entrance, centers[-1], "marker_path")))
    tunnel_tiles.update(thicken_path(grid, carve_corridor(grid, centers[1], profile.exit, "marker_path")))

    protected = protected_tiles_for_points([profile.entrance, profile.exit], radius=3)
    for x, y in protected:
        if not is_edge(x, y):
            grid[y][x] = "marker_protected"
    entrance_x, entrance_y = profile.entrance
    exit_x, exit_y = profile.exit
    grid[entrance_y][entrance_x] = "marker_entrance"
    grid[exit_y][exit_x] = "marker_exit"
    ladder_pos = (exit_x, exit_y + 1)
    if in_bounds(*ladder_pos):
        grid[ladder_pos[1]][ladder_pos[0]] = "marker_ladder"

    reachable = sorted(reachable_tiles(grid, profile.entrance))
    reserved = {profile.entrance, profile.exit, ladder_pos} | protected
    candidate_tiles = [pos for pos in reachable if pos not in reserved and not is_edge(*pos)]
    rng.shuffle(candidate_tiles)
    special_markers = {
        "marker_treasure": [],
        "marker_monster_spawn": [],
        "marker_ore_spawn": [],
    }
    placements = [
        ("marker_treasure", 2),
        ("marker_monster_spawn", 5),
        ("marker_ore_spawn", 8),
    ]
    cursor = 0
    for role, count in placements:
        for _ in range(count):
            while cursor < len(candidate_tiles) and grid[candidate_tiles[cursor][1]][candidate_tiles[cursor][0]] not in PASSABLE:
                cursor += 1
            if cursor >= len(candidate_tiles):
                break
            x, y = candidate_tiles[cursor]
            cursor += 1
            grid[y][x] = role
            special_markers[role].append({"x": x, "y": y})

    edge_sealing = seal_map_edges_except_intended_exits(grid, set())
    stats = {
        "layoutProfile": profile.profile_id,
        "layoutFamily": profile.layout_family,
        "caveRoomCount": len(room_specs),
        "protectedTileCount": len(protected),
        "caveFloorTileCount": sum(cell == "marker_cave_floor" for row in grid for cell in row),
        "tunnelTileCount": sum(cell == "marker_path" for row in grid for cell in row),
        "rockWallCount": sum(cell == "marker_rock_wall" for row in grid for cell in row),
        "ladderCount": sum(cell == "marker_ladder" for row in grid for cell in row),
        "treasureMarkerCount": sum(cell == "marker_treasure" for row in grid for cell in row),
        "monsterSpawnMarkerCount": sum(cell == "marker_monster_spawn" for row in grid for cell in row),
        "oreSpawnMarkerCount": sum(cell == "marker_ore_spawn" for row in grid for cell in row),
        "sealedEdgeTileCount": len(edge_sealing["sealedEdgeTiles"]),
        "passableEdgeTilesRemaining": len(edge_sealing["passableEdgeTilesRemaining"]),
        "specialMarkers": special_markers,
    }
    return grid, stats, edge_sealing


def build_grid(seed: int, layout_profile: str = "outdoor") -> tuple[list[list[str]], dict, dict, LayoutProfile]:
    layout_profile = LAYOUT_ALIASES.get(layout_profile, layout_profile)
    profile = LAYOUT_PROFILES.get(layout_profile)
    if not profile:
        raise ValueError(f"Unknown layout profile: {layout_profile}")
    if profile.layout_family == "indoor":
        grid, stats, edge_sealing = build_indoor_grid(seed, profile)
    elif profile.layout_family == "dungeon":
        grid, stats, edge_sealing = build_dungeon_grid(seed, profile)
    else:
        grid, stats, edge_sealing = build_outdoor_grid(seed, profile)
    return grid, stats, edge_sealing, profile


def write_outputs(stylepack: dict, grid: list[list[str]], stats: dict, edge_sealing: dict, seed: int, profile: LayoutProfile) -> None:
    out_dir = output_dir_for_profile(profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = ["".join(CHARS.get(cell, "?") for cell in row) for row in grid]
    full_layout = write_full_layout_tmj(stylepack, grid, profile, out_dir)
    semantic_path = out_dir / f"{profile.full_layout_stem}.semantic.json"
    ascii_path = out_dir / f"{profile.full_layout_stem}.ascii.txt"
    metadata_path = out_dir / f"{profile.full_layout_stem}.generation_metadata.json"
    validation_path = out_dir / f"{profile.full_layout_stem}.validation_report.md"
    compatibility_semantic_path = out_dir / "marker_test_map.semantic.json"
    compatibility_ascii_path = out_dir / "marker_test_map.ascii.txt"
    compatibility_metadata_path = out_dir / "marker_test_map.generation_metadata.json"
    semantic = {
        "schemaVersion": 1,
        "generatedAt": GENERATED_AT,
        "mapName": profile.full_layout_stem,
        "stylePackId": stylepack["stylePackId"],
        "layoutProfile": profile.profile_id,
        "layoutFamily": profile.layout_family,
        "layoutDescription": profile.description,
        "width": WIDTH,
        "height": HEIGHT,
        "seed": seed,
        "generationMode": "marker_only",
        "usesFinalVisualTileIds": False,
        "tile946BlockingRolesUsed": False,
        "legend": CHARS,
        "rows": rows,
        "cells": grid,
        "stats": stats,
        "edgeSealing": edge_sealing,
        "fullTileLayout": full_layout,
    }
    out_of_bounds = check_out_of_bounds(semantic)
    out_of_bounds_errors, _ = errors_and_warnings(out_of_bounds)
    semantic_text = json.dumps(semantic, indent=2) + "\n"
    semantic_path.write_text(semantic_text, encoding="utf-8")
    compatibility_semantic_path.write_text(semantic_text, encoding="utf-8")
    ascii_text = "\n".join(rows) + "\n"
    ascii_path.write_text(ascii_text, encoding="utf-8")
    compatibility_ascii_path.write_text(ascii_text, encoding="utf-8")
    metadata = {
        "generatedAt": GENERATED_AT,
        "stylePackId": stylepack["stylePackId"],
        "layoutProfile": profile.profile_id,
        "layoutFamily": profile.layout_family,
        "stylepackValidationRequired": True,
        "markerOnly": True,
        "productionMap": False,
        "deepWoodsInspiredPasses": ["semantic_layout", "irregular_border_variation", "protected_exit_capsules", "path_carving", "safe_wall_segments", "decoration_zone_marking"],
        "edgeSealingApplied": edge_sealing["edgeSealingApplied"],
        "intendedExitTiles": edge_sealing["intendedExitTiles"],
        "sealedEdgeTiles": edge_sealing["sealedEdgeTiles"],
        "passableEdgeTilesRemaining": edge_sealing["passableEdgeTilesRemaining"],
        "outOfBoundsCheckPass": not out_of_bounds_errors,
        "outOfBoundsEscapeCount": len(out_of_bounds["outOfBoundsEscapes"]),
        "outOfBoundsUnreachableExitCount": len(out_of_bounds["unreachableDeclaredExits"]),
        "outOfBoundsUnreachableWalkablePocketCount": len(out_of_bounds["unreachableWalkablePockets"]),
        "outputs": {
            "semantic": str(semantic_path.resolve()),
            "ascii": str(ascii_path.resolve()),
            "validation": str(validation_path.resolve()),
            "fullTileLayoutTmj": full_layout["tmjPath"],
            "fullTileLayoutTmx": full_layout["tmxPath"],
            "fullTileLayoutPreview": full_layout["previewPath"],
            "markerTilesheet": full_layout["markerTilesheetPath"],
            "compatibilitySemantic": str(compatibility_semantic_path.resolve()),
        },
        "stats": stats,
        "fullTileLayout": full_layout,
    }
    metadata_text = json.dumps(metadata, indent=2) + "\n"
    metadata_path.write_text(metadata_text, encoding="utf-8")
    compatibility_metadata_path.write_text(metadata_text, encoding="utf-8")


def write_summary(stylepack_id: str, stats: dict, profile: LayoutProfile) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = output_dir_for_profile(profile)
    lines = [
        "# Marker Generator Summary",
        "",
        f"- Generated: {GENERATED_AT}",
        f"- Stylepack: `{stylepack_id}`",
        f"- Layout profile: `{profile.profile_id}`",
        f"- Layout family: `{profile.layout_family}`",
        "- Output mode: marker-only semantic map",
        "- Production map generated: NO",
        "- Final visual tile IDs used: NO",
        "- Tile 946 wall/body/blocking usage: NO",
        f"- Output folder: `{out_dir}`",
        "",
        "## Map Stats",
        "",
    ]
    for key, value in stats.items():
        lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "## Safety",
        "",
        "- The map uses marker role names only.",
        "- It is intended for testing semantic layout, border variation, protected exits, and validator flow.",
        "- It should not be copied into the mod as a production map.",
    ])
    (REPORT_DIR / f"marker_generator_summary_{profile.profile_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORT_DIR / "marker_generator_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_layout_split_report(profile_ids: list[str], stylepack_id: str) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Map Generation Layout Split",
        "",
        f"- Generated: {GENERATED_AT}",
        f"- Stylepack: `{stylepack_id}`",
        "- Production maps generated: NO",
        "- Output mode: marker-only",
        "",
        "## Active Layout Profiles",
        "",
    ]
    for profile_id in profile_ids:
        profile = LAYOUT_PROFILES[profile_id]
        out_dir = output_dir_for_profile(profile)
        lines.extend(
            [
                f"### {profile.profile_id}",
                "",
                f"- Layout family: `{profile.layout_family}`",
                f"- Description: {profile.description}",
                f"- Entrance: `{profile.entrance}`",
                f"- Exit: `{profile.exit}`",
                f"- Edge exits allowed: `{profile.edge_exits_allowed}`",
                f"- Output folder: `{out_dir}`",
                f"- Semantic map: `{out_dir / (profile.full_layout_stem + '.semantic.json')}`",
                f"- Full TMX marker layout: `{out_dir / (profile.full_layout_stem + '.tmx')}`",
                f"- Full TMJ marker layout: `{out_dir / (profile.full_layout_stem + '.tmj')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Split Rules",
            "",
            "- Outdoor layouts use irregular border variation, protected near-border entrance/exit capsules, sealed map edges, and outdoor path carving.",
            "- Indoor layouts use sealed exterior walls, room rectangles, corridor connections, interior entrance/exit markers, and no passable map-edge tiles.",
            "- Dungeon layouts use sealed cave boundaries, irregular cave rooms, connected tunnels, reachable ladders, treasure markers, and spawn markers.",
            "- All profiles emit marker roles only. They do not use approved production tile IDs.",
            "- Tile 946 remains unavailable for wall/body/blocking/collision output.",
            "",
            "## Next Work",
            "",
            "- Add production renderers separately for outdoor, indoor, and dungeon once structural tiles are approved.",
            "- Teach stylepacks which layout families they support before allowing visual generation.",
            "- Add indoor-specific grammar checks for doors, walls, floors, counters, and furniture once those roles are approved.",
            "- Add dungeon-specific grammar checks for cave walls, cave floors, ladders, ore, monsters, and treasure once those roles are approved.",
        ]
    )
    (REPORT_DIR / "map_generation_layout_split.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stylepack", default="moonvillage_forest_ruins")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--layout-profile", choices=[*LAYOUT_PROFILES.keys(), *LAYOUT_ALIASES.keys(), "both", "all"], default="outdoor")
    args = parser.parse_args()

    validation = validate_all()
    if not validation["pass"]:
        raise SystemExit("Stylepack validation must pass before marker generation.")

    path = STYLEPACK_DIR / f"{args.stylepack}.json"
    if not path.exists():
        raise SystemExit(f"Stylepack not found: {path}")
    stylepack = json.loads(path.read_text(encoding="utf-8"))
    profile_ids = list(LAYOUT_PROFILES) if args.layout_profile in {"both", "all"} else [LAYOUT_ALIASES.get(args.layout_profile, args.layout_profile)]
    output_dirs = []
    for profile_id in profile_ids:
        grid, stats, edge_sealing, profile = build_grid(args.seed, profile_id)
        write_outputs(stylepack, grid, stats, edge_sealing, args.seed, profile)
        write_summary(stylepack["stylePackId"], stats, profile)
        output_dirs.append(str(output_dir_for_profile(profile)))
    write_layout_split_report(profile_ids, stylepack["stylePackId"])
    print(f"Wrote marker map outputs to {', '.join(output_dirs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
