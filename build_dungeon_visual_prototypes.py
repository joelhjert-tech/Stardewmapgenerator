#!/usr/bin/env python3
"""Build isolated visual mine/dungeon prototype maps for review.

This intentionally writes only under tools/tiled-map-assistant/prototype_visual_maps
and reports/. It reads the unpacked vanilla mine tilesheet and vanilla reference
maps as evidence, but it does not modify mission_assets or production data.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
BASEGAME = ROOT / "mission_assets" / "unpacked_basegame"
OUT_ROOT = ROOT / "prototype_visual_maps" / "dungeon_review"
REPORTS = ROOT / "reports"
MINE_MAP_DIR = BASEGAME / "Mine"
TILESET_SRC = BASEGAME / "mine.png"
if not TILESET_SRC.exists():
    TILESET_SRC = MINE_MAP_DIR / "mine.png"
TILE_SIZE = 16
MAP_W = 48
MAP_H = 48
FIRSTGID = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def gid(local_tile_id: Optional[int]) -> int:
    if local_tile_id is None:
        return 0
    return local_tile_id + FIRSTGID


def local_id(gid_value: int) -> Optional[int]:
    if gid_value <= 0:
        return None
    return gid_value - FIRSTGID


def hpick(options: Sequence[int], x: int, y: int, seed: int, bias_first: int = 0) -> int:
    """Deterministic coordinate picker with optional strong bias toward first tile."""
    if not options:
        raise ValueError("empty tile option list")
    n = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    n &= 0xFFFFFFFF
    if bias_first and n % bias_first:
        return options[0]
    return options[n % len(options)]


def relpath(path: Path, start: Path) -> str:
    return path.resolve().relative_to(start.resolve()).as_posix()


@dataclass
class TileRole:
    local_id: int
    role: str
    layer: str
    collision: str
    reason: str
    confidence: int = 80


@dataclass
class PrototypeMap:
    map_id: str
    title: str
    kind: str
    source_map: Optional[str]
    source_origin: str
    source_reason: str
    width: int = MAP_W
    height: int = MAP_H
    seed: int = 0
    floor_style: str = "earth"
    layers: Dict[str, List[int]] = field(default_factory=dict)
    walkable: Set[Tuple[int, int]] = field(default_factory=set)
    blocked: Set[Tuple[int, int]] = field(default_factory=set)
    floor_mask: Set[Tuple[int, int]] = field(default_factory=set)
    wall_mask: Set[Tuple[int, int]] = field(default_factory=set)
    entrance: Tuple[int, int] = (0, 0)
    exit: Tuple[int, int] = (0, 0)
    ladder_cells: Set[Tuple[int, int]] = field(default_factory=set)
    special_markers: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)
    provisional_roles: List[TileRole] = field(default_factory=list)

    def init_layers(self) -> None:
        self.layers = {
            "Back": [gid(77)] * (self.width * self.height),
            "Buildings": [0] * (self.width * self.height),
            "Front": [0] * (self.width * self.height),
            "AlwaysFront": [0] * (self.width * self.height),
            "Paths": [0] * (self.width * self.height),
        }

    def idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def set_tile(self, layer: str, x: int, y: int, tile_id: Optional[int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.layers[layer][self.idx(x, y)] = gid(tile_id)

    def get_tile(self, layer: str, x: int, y: int) -> Optional[int]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        return local_id(self.layers[layer][self.idx(x, y)])


TILE_ROLES: Dict[int, TileRole] = {
    77: TileRole(77, "black_void_fill", "Back", "blocked_outside_floor", "Frequent vanilla mine void/black fill tile."),
    138: TileRole(138, "cave_floor_base", "Back", "walkable", "Most common Back floor tile in vanilla 1.tbin/10.tbin."),
    137: TileRole(137, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    139: TileRole(139, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    140: TileRole(140, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    153: TileRole(153, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    154: TileRole(154, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    155: TileRole(155, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    169: TileRole(169, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    170: TileRole(170, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    171: TileRole(171, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    185: TileRole(185, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    186: TileRole(186, "cave_under_wall_shadow_floor", "Back", "walkable", "Vanilla Back under-wall/shadow floor; do not use as random broad floor."),
    187: TileRole(187, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    188: TileRole(188, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    201: TileRole(201, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    202: TileRole(202, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    203: TileRole(203, "cave_floor_variation", "Back", "walkable", "Repeated vanilla Back floor variation."),
    217: TileRole(217, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    218: TileRole(218, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    219: TileRole(219, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    220: TileRole(220, "cave_front_wall_side_overlay", "Front", "decorative_front", "Vanilla mine Front wall/side overlay; invalid as random Back floor."),
    233: TileRole(233, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    234: TileRole(234, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    235: TileRole(235, "cave_floor_detail", "Back", "walkable", "Common vanilla Back floor detail."),
    1: TileRole(1, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    2: TileRole(2, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    3: TileRole(3, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    17: TileRole(17, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    18: TileRole(18, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    19: TileRole(19, "mine_plank_or_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    33: TileRole(33, "mine_cobbled_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    34: TileRole(34, "mine_cobbled_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    35: TileRole(35, "mine_cobbled_floor_base", "Back", "walkable", "Used on Back in vanilla 10.tbin as compact mine-room flooring."),
    69: TileRole(69, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    70: TileRole(70, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    71: TileRole(71, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    72: TileRole(72, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    73: TileRole(73, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    74: TileRole(74, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    75: TileRole(75, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    76: TileRole(76, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock boundary candidate."),
    85: TileRole(85, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    86: TileRole(86, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    87: TileRole(87, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    88: TileRole(88, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    89: TileRole(89, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    90: TileRole(90, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    91: TileRole(91, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    92: TileRole(92, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    93: TileRole(93, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    94: TileRole(94, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    101: TileRole(101, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    102: TileRole(102, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    105: TileRole(105, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    106: TileRole(106, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    107: TileRole(107, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    108: TileRole(108, "cave_wall_body", "Buildings", "blocked", "Vanilla mine Buildings rock body candidate."),
    109: TileRole(109, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    110: TileRole(110, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    121: TileRole(121, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock lower edge candidate."),
    122: TileRole(122, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock lower edge candidate."),
    123: TileRole(123, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock lower edge candidate."),
    124: TileRole(124, "cave_wall_edge", "Buildings", "blocked", "Vanilla mine Buildings rock lower edge candidate."),
    125: TileRole(125, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    126: TileRole(126, "cave_wall_corner", "Buildings", "blocked", "Vanilla mine Buildings rock corner/cap candidate."),
    196: TileRole(196, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    197: TileRole(197, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    205: TileRole(205, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    206: TileRole(206, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    213: TileRole(213, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    214: TileRole(214, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    215: TileRole(215, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    216: TileRole(216, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    221: TileRole(221, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    232: TileRole(232, "cave_shadow_or_front_edge", "Front", "decorative_front", "Vanilla mine Front rock/shadow edge candidate."),
    67: TileRole(67, "ladder_or_exit", "Buildings", "walkable_special", "Vanilla mine ladder candidate; prototype review only."),
    83: TileRole(83, "ladder_or_exit", "Buildings", "walkable_special", "Vanilla mine ladder candidate; prototype review only."),
    99: TileRole(99, "ladder_or_exit", "Buildings", "walkable_special", "Vanilla mine ladder candidate; prototype review only."),
    115: TileRole(115, "ladder_or_exit", "Buildings", "walkable_special", "Vanilla mine ladder candidate; prototype review only."),
    48: TileRole(48, "wall_torch", "Front", "decorative_front", "Vanilla mine torch/light decoration candidate."),
    80: TileRole(80, "wall_torch", "Front", "decorative_front", "Vanilla mine torch/light decoration candidate."),
    237: TileRole(237, "fire_or_light", "Front", "decorative_front", "Vanilla mine fire/light decoration candidate."),
    238: TileRole(238, "treasure_chest", "Buildings", "blocked_or_interactive", "Vanilla mine chest/treasure candidate; prototype review only."),
    239: TileRole(239, "ore_or_crate_detail", "Buildings", "blocked", "Vanilla mine detail candidate; prototype review only."),
}

EARTH_FLOORS = [138, 138, 138, 138, 137, 139, 140, 153, 154, 155, 169, 170, 171, 185, 187, 188]
EARTH_DETAILS = [217, 218, 218, 219, 233, 234, 234, 235, 201, 202, 203]
COBBLE_FLOORS = [33, 33, 33, 18, 18, 34, 35, 1, 2, 3, 17, 19, 138]
WALL_TOPS = [69, 70, 71, 72, 73, 74, 75, 76]
WALL_BODIES = [85, 86, 87, 88, 89, 90, 91, 92, 101, 102, 105, 106, 107, 108]
WALL_LOWER = [121, 122, 123, 124]
WALL_CORNERS_L = [93, 109, 125]
WALL_CORNERS_R = [94, 110, 126]
FRONT_SHADOW_TOP = [213, 214, 215, 216]
FRONT_SHADOW_SIDE_L = [196, 197, 205]
FRONT_SHADOW_SIDE_R = [206, 221, 232]
LADDER_STACK = [67, 83, 99, 115]


def add_ellipse(mask: Set[Tuple[int, int]], cx: int, cy: int, rx: int, ry: int) -> None:
    for y in range(cy - ry - 1, cy + ry + 2):
        for x in range(cx - rx - 1, cx + rx + 2):
            if 1 <= x < MAP_W - 1 and 1 <= y < MAP_H - 1:
                dx = (x - cx) / max(1, rx)
                dy = (y - cy) / max(1, ry)
                if dx * dx + dy * dy <= 1.0:
                    mask.add((x, y))


def add_rect(mask: Set[Tuple[int, int]], x1: int, y1: int, x2: int, y2: int) -> None:
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            if 1 <= x < MAP_W - 1 and 1 <= y < MAP_H - 1:
                mask.add((x, y))


def carve_corridor(mask: Set[Tuple[int, int]], points: Sequence[Tuple[int, int]], width: int = 2) -> None:
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        x, y = ax, ay
        while (x, y) != (bx, by):
            for yy in range(y - width, y + width + 1):
                for xx in range(x - width, x + width + 1):
                    if abs(xx - x) + abs(yy - y) <= width + 1 and 1 <= xx < MAP_W - 1 and 1 <= yy < MAP_H - 1:
                        mask.add((xx, yy))
            if x < bx:
                x += 1
            elif x > bx:
                x -= 1
            elif y < by:
                y += 1
            elif y > by:
                y -= 1
        for yy in range(by - width, by + width + 1):
            for xx in range(bx - width, bx + width + 1):
                if abs(xx - bx) + abs(yy - by) <= width + 1 and 1 <= xx < MAP_W - 1 and 1 <= yy < MAP_H - 1:
                    mask.add((xx, yy))


def neighbors4(x: int, y: int) -> Iterable[Tuple[int, int]]:
    yield x, y - 1
    yield x + 1, y
    yield x, y + 1
    yield x - 1, y


def make_remake_01() -> PrototypeMap:
    p = PrototypeMap(
        map_id="remake_01",
        title="Remake 01 - Open Vanilla Mine Chamber",
        kind="remake",
        source_map="1.tbin",
        source_origin="vanilla base-game unpacked map, read-only: mission_assets/unpacked_basegame/1.tbin",
        source_reason="Small early mine chamber with one clean open floor, a top ladder, torches, and simple rocky boundary.",
        seed=31001,
        floor_style="earth",
        entrance=(24, 38),
        exit=(24, 11),
    )
    mask: Set[Tuple[int, int]] = set()
    add_ellipse(mask, 24, 25, 16, 13)
    add_ellipse(mask, 16, 31, 8, 7)
    add_ellipse(mask, 34, 24, 8, 9)
    carve_corridor(mask, [(24, 38), (24, 12)], width=2)
    add_rect(mask, 22, 10, 26, 14)
    p.floor_mask = mask
    p.special_markers = {"torches": [(15, 15), (33, 15), (11, 28), (37, 29)], "ore": [(18, 25), (28, 30), (35, 22)]}
    return p


def make_remake_02() -> PrototypeMap:
    p = PrototypeMap(
        map_id="remake_02",
        title="Remake 02 - Compact Mine Outpost Room",
        kind="remake",
        source_map="10.tbin",
        source_origin="vanilla base-game unpacked map, read-only: mission_assets/unpacked_basegame/10.tbin",
        source_reason="Compact mine room with denser Back-layer flooring, a ladder/exit, and wooden/stone structural language.",
        seed=31010,
        floor_style="cobble",
        entrance=(24, 37),
        exit=(36, 23),
    )
    mask: Set[Tuple[int, int]] = set()
    add_rect(mask, 12, 18, 36, 35)
    add_ellipse(mask, 24, 26, 15, 9)
    add_ellipse(mask, 36, 24, 6, 5)
    carve_corridor(mask, [(24, 37), (24, 30), (35, 24)], width=2)
    add_rect(mask, 34, 21, 39, 26)
    # make lower edge less rectangular
    for x in range(12, 19):
        mask.discard((x, 35))
    for x in range(30, 37):
        mask.discard((x, 35))
    p.floor_mask = mask
    p.special_markers = {"torches": [(15, 17), (31, 17), (40, 24)], "wood": [(20, 17), (21, 17), (22, 17), (23, 17)], "chests": [(31, 31)]}
    return p


def make_custom_03() -> PrototypeMap:
    p = PrototypeMap(
        map_id="custom_03",
        title="Custom 03 - Branching Moonvillage Mine Prototype",
        kind="custom",
        source_map=None,
        source_origin="original prototype generated from scratch using vanilla mine.png tile language.",
        source_reason="Tests a believable custom mine floor with a main chamber, side pockets, reachable exit, treasure, and ore interest points.",
        seed=31033,
        floor_style="earth",
        entrance=(23, 42),
        exit=(36, 10),
    )
    mask: Set[Tuple[int, int]] = set()
    add_ellipse(mask, 22, 31, 13, 9)
    add_ellipse(mask, 15, 18, 9, 7)
    add_ellipse(mask, 34, 16, 8, 8)
    add_ellipse(mask, 36, 34, 7, 6)
    carve_corridor(mask, [(23, 42), (22, 31), (15, 18), (34, 16), (36, 10)], width=2)
    carve_corridor(mask, [(22, 31), (36, 34)], width=2)
    add_rect(mask, 33, 8, 39, 12)
    p.floor_mask = mask
    p.special_markers = {
        "torches": [(12, 16), (28, 14), (38, 20), (16, 33), (37, 31)],
        "ore": [(14, 21), (20, 17), (31, 17), (39, 35), (18, 36), (28, 31)],
        "chests": [(38, 12)],
    }
    return p


def build_wall_mask(floor: Set[Tuple[int, int]], radius: int = 2) -> Set[Tuple[int, int]]:
    wall: Set[Tuple[int, int]] = set()
    for x, y in floor:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and (nx, ny) not in floor:
                    if max(abs(dx), abs(dy)) <= radius:
                        wall.add((nx, ny))
    return wall


def decorate_floor(p: PrototypeMap) -> None:
    floor_tiles = COBBLE_FLOORS if p.floor_style == "cobble" else EARTH_FLOORS
    for x, y in p.floor_mask:
        tile = hpick(floor_tiles, x, y, p.seed, bias_first=3)
        if (x * 17 + y * 31 + p.seed) % 13 == 0:
            tile = hpick(EARTH_DETAILS, x, y, p.seed + 11)
        p.set_tile("Back", x, y, tile)
        p.walkable.add((x, y))


def decorate_walls(p: PrototypeMap) -> None:
    p.wall_mask = build_wall_mask(p.floor_mask, 2)
    for x, y in p.wall_mask:
        if (x, y) in p.floor_mask:
            continue
        n_floor = (x, y - 1) in p.floor_mask
        e_floor = (x + 1, y) in p.floor_mask
        s_floor = (x, y + 1) in p.floor_mask
        w_floor = (x - 1, y) in p.floor_mask
        diagonal_floor = any((x + dx, y + dy) in p.floor_mask for dx in (-1, 1) for dy in (-1, 1))
        if s_floor and not (e_floor or w_floor):
            tile = hpick(WALL_TOPS, x, y, p.seed)
        elif n_floor:
            tile = hpick(WALL_LOWER, x, y, p.seed)
        elif e_floor:
            tile = hpick(WALL_CORNERS_L + WALL_BODIES[:3], x, y, p.seed)
        elif w_floor:
            tile = hpick(WALL_CORNERS_R + WALL_BODIES[-3:], x, y, p.seed)
        elif diagonal_floor:
            tile = hpick(WALL_CORNERS_L + WALL_CORNERS_R, x, y, p.seed)
        else:
            tile = hpick(WALL_BODIES, x, y, p.seed, bias_first=2)
        p.set_tile("Buildings", x, y, tile)
        p.blocked.add((x, y))


def decorate_front_edges(p: PrototypeMap) -> None:
    for x, y in sorted(p.floor_mask):
        north_wall = (x, y - 1) in p.wall_mask
        west_wall = (x - 1, y) in p.wall_mask
        east_wall = (x + 1, y) in p.wall_mask
        if north_wall:
            p.set_tile("Front", x, y, hpick(FRONT_SHADOW_TOP, x, y, p.seed))
        elif west_wall and not east_wall:
            p.set_tile("Front", x, y, hpick(FRONT_SHADOW_SIDE_L, x, y, p.seed))
        elif east_wall and not west_wall:
            p.set_tile("Front", x, y, hpick(FRONT_SHADOW_SIDE_R, x, y, p.seed))


def place_ladder_stack(p: PrototypeMap, x: int, y_bottom: int) -> None:
    top_y = y_bottom - len(LADDER_STACK) + 1
    for offset, tile in enumerate(LADDER_STACK):
        y = top_y + offset
        if 0 <= y < p.height:
            p.set_tile("Buildings", x, y, tile)
            p.ladder_cells.add((x, y))
            p.walkable.add((x, y))
            p.blocked.discard((x, y))
    p.set_tile("Back", x, y_bottom, hpick(EARTH_FLOORS, x, y_bottom, p.seed))


def place_specials(p: PrototypeMap) -> None:
    # Entrance: keep floor visible and unobstructed.
    ex, ey = p.entrance
    add_rect(p.floor_mask, ex - 1, ey - 1, ex + 1, ey + 1)
    p.walkable.update((x, y) for x in range(ex - 1, ex + 2) for y in range(ey - 1, ey + 2) if 0 <= x < p.width and 0 <= y < p.height)
    # Exit ladder.
    lx, ly = p.exit
    place_ladder_stack(p, lx, ly)
    # Torches and small mine details.
    for x, y in p.special_markers.get("torches", []):
        if 0 <= x < p.width and 0 <= y < p.height:
            p.set_tile("Front", x, y, 48 if (x + y) % 2 else 80)
    for x, y in p.special_markers.get("ore", []):
        if (x, y) in p.floor_mask:
            p.set_tile("Buildings", x, y, 239)
            p.blocked.add((x, y))
    for x, y in p.special_markers.get("chests", []):
        if (x, y) in p.floor_mask:
            p.set_tile("Buildings", x, y, 238)
            p.blocked.add((x, y))
    # Wooden outpost rail on remake_02.
    for x, y in p.special_markers.get("wood", []):
        if 0 <= x < p.width and 0 <= y < p.height:
            p.set_tile("Buildings", x, y, hpick([20, 21, 22, 36, 37, 38], x, y, p.seed))
            p.blocked.add((x, y))


def finalize_map(p: PrototypeMap) -> None:
    p.init_layers()
    decorate_floor(p)
    decorate_walls(p)
    decorate_front_edges(p)
    place_specials(p)
    # Re-assert protected entrance/exit floors after wall pass.
    for x, y in [p.entrance, p.exit]:
        p.set_tile("Back", x, y, hpick(EARTH_FLOORS, x, y, p.seed))
        p.walkable.add((x, y))
        p.blocked.discard((x, y))
    p.provisional_roles = []
    used: Set[Tuple[int, str]] = set()
    for layer, data in p.layers.items():
        for g in data:
            tid = local_id(g)
            if tid is None:
                continue
            role = TILE_ROLES.get(tid)
            if role and (tid, role.layer) not in used:
                p.provisional_roles.append(role)
                used.add((tid, role.layer))


def csv_data(values: Sequence[int], width: int) -> str:
    rows = []
    for y in range(len(values) // width):
        rows.append(",".join(str(v) for v in values[y * width:(y + 1) * width]))
    return "\n" + ",\n".join(rows) + "\n"


def write_tmx(p: PrototypeMap, out_dir: Path, tilesheet_rel: str) -> Path:
    tmx = out_dir / f"{p.map_id}.tmx"
    layer_chunks = []
    for idx, layer_name in enumerate(["Back", "Buildings", "Front", "AlwaysFront", "Paths"], start=1):
        layer_chunks.append(
            f'  <layer id="{idx}" name="{layer_name}" width="{p.width}" height="{p.height}">\n'
            f'   <data encoding="csv">{csv_data(p.layers[layer_name], p.width)}   </data>\n'
            f"  </layer>"
        )
    props = f"""  <properties>
   <property name="prototype" value="true"/>
   <property name="profile" value="dungeon"/>
   <property name="sourceMap" value="{p.source_map or 'custom'}"/>
   <property name="entrance" value="{p.entrance[0]} {p.entrance[1]}"/>
   <property name="exit" value="{p.exit[0]} {p.exit[1]}"/>
   <property name="tileUsageStatus" value="prototype_only_provisional"/>
  </properties>"""
    text = f"""<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.10.2" orientation="orthogonal" renderorder="right-down" width="{p.width}" height="{p.height}" tilewidth="16" tileheight="16" infinite="0" nextlayerid="10" nextobjectid="1">
{props}
  <tileset firstgid="1" name="mine" tilewidth="16" tileheight="16" tilecount="288" columns="16">
   <image source="{tilesheet_rel}" width="256" height="288"/>
  </tileset>
{chr(10).join(layer_chunks)}
</map>
"""
    tmx.write_text(text, encoding="utf-8")
    return tmx


def write_tmj(p: PrototypeMap, out_dir: Path, tilesheet_rel: str) -> Path:
    tmj = out_dir / f"{p.map_id}.tmj"
    layers = []
    for i, layer_name in enumerate(["Back", "Buildings", "Front", "AlwaysFront", "Paths"], start=1):
        layers.append({
            "id": i,
            "name": layer_name,
            "type": "tilelayer",
            "visible": True,
            "opacity": 1,
            "width": p.width,
            "height": p.height,
            "x": 0,
            "y": 0,
            "data": p.layers[layer_name],
        })
    obj_layer = {
        "id": 6,
        "name": "ReviewMarkers",
        "type": "objectgroup",
        "visible": True,
        "opacity": 1,
        "objects": [
            {"id": 1, "name": "Entrance", "type": "prototype_entrance", "x": p.entrance[0] * 16, "y": p.entrance[1] * 16, "width": 16, "height": 16},
            {"id": 2, "name": "Exit", "type": "prototype_exit_ladder", "x": p.exit[0] * 16, "y": p.exit[1] * 16, "width": 16, "height": 16},
        ],
    }
    layers.append(obj_layer)
    doc = {
        "type": "map",
        "version": "1.10",
        "tiledversion": "1.10.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "width": p.width,
        "height": p.height,
        "tilewidth": 16,
        "tileheight": 16,
        "infinite": False,
        "properties": [
            {"name": "prototype", "type": "bool", "value": True},
            {"name": "profile", "type": "string", "value": "dungeon"},
            {"name": "sourceMap", "type": "string", "value": p.source_map or "custom"},
            {"name": "tileUsageStatus", "type": "string", "value": "prototype_only_provisional"},
        ],
        "tilesets": [{
            "firstgid": 1,
            "name": "mine",
            "tilewidth": 16,
            "tileheight": 16,
            "tilecount": 288,
            "columns": 16,
            "image": tilesheet_rel,
            "imagewidth": 256,
            "imageheight": 288,
        }],
        "layers": layers,
    }
    tmj.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return tmj


def render_map(
    p: PrototypeMap,
    tilesheet: Image.Image,
    out_dir: Path,
    clean_name: str = "preview_clean.png",
    labeled_name: str = "preview_labeled.png",
) -> Tuple[Path, Path]:
    def draw_layers(label: bool) -> Image.Image:
        canvas = Image.new("RGBA", (p.width * TILE_SIZE, p.height * TILE_SIZE), (0, 0, 0, 255))
        cols = tilesheet.width // TILE_SIZE
        for layer_name in ["Back", "Buildings", "Front", "AlwaysFront"]:
            data = p.layers[layer_name]
            for y in range(p.height):
                for x in range(p.width):
                    tid = local_id(data[p.idx(x, y)])
                    if tid is None:
                        continue
                    sx = (tid % cols) * TILE_SIZE
                    sy = (tid // cols) * TILE_SIZE
                    tile = tilesheet.crop((sx, sy, sx + TILE_SIZE, sy + TILE_SIZE))
                    canvas.alpha_composite(tile, (x * TILE_SIZE, y * TILE_SIZE))
        if label:
            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(overlay)
            for x in range(0, p.width + 1, 4):
                color = (255, 255, 255, 26 if x % 8 else 55)
                d.line((x * 16, 0, x * 16, p.height * 16), fill=color)
            for y in range(0, p.height + 1, 4):
                color = (255, 255, 255, 26 if y % 8 else 55)
                d.line((0, y * 16, p.width * 16, y * 16), fill=color)
            for name, pos, color in [
                ("ENTRANCE", p.entrance, (60, 220, 110, 210)),
                ("EXIT/LADDER", p.exit, (255, 220, 55, 220)),
            ]:
                x, y = pos
                d.rectangle((x * 16 - 2, y * 16 - 2, x * 16 + 18, y * 16 + 18), outline=color, width=3)
                d.text((x * 16 + 20, max(0, y * 16 - 2)), name, fill=color)
            d.rectangle((6, 6, 340, 58), fill=(0, 0, 0, 170), outline=(255, 255, 255, 100))
            d.text((12, 12), p.title, fill=(255, 255, 255, 230))
            d.text((12, 30), f"{p.width}x{p.height} | source: {p.source_map or 'custom'} | prototype-only tiles", fill=(235, 235, 235, 220))
            return Image.alpha_composite(canvas, overlay)
        return canvas

    clean = draw_layers(False)
    labeled = draw_layers(True)
    clean_path = out_dir / clean_name
    labeled_path = out_dir / labeled_name
    clean.save(clean_path)
    labeled.save(labeled_path)
    return clean_path, labeled_path


def render_source_reference(source_name: Optional[str], out_dir: Path) -> Optional[Path]:
    if not source_name:
        return None
    sys.path.insert(0, str(ROOT))
    import tbin_reader  # local import keeps script usable if references are unavailable

    p = BASEGAME / source_name
    if not p.exists():
        p = MINE_MAP_DIR / source_name
    if not p.exists():
        return None
    mp = tbin_reader.parse(p.read_bytes())
    w, h = mp["layers"][0]["layerSize"]
    sheets = {}
    for ts in mp["tilesheets"]:
        src = ts["imageSource"]
        cand = BASEGAME / (src if src.lower().endswith(".png") else src + ".png")
        if cand.exists():
            sheets[ts["id"]] = Image.open(cand).convert("RGBA")
    canvas = Image.new("RGBA", (w * 16, h * 16), (0, 0, 0, 255))
    for layer_name in ["Back", "Buildings", "Front", "AlwaysFront"]:
        layer = next((l for l in mp["layers"] if l["id"] == layer_name), None)
        if not layer:
            continue
        for (x, y), (sid, idx) in layer["tiles"].items():
            sheet = sheets.get(sid)
            if not sheet:
                continue
            cols = sheet.width // 16
            sx, sy = (idx % cols) * 16, (idx // cols) * 16
            canvas.alpha_composite(sheet.crop((sx, sy, sx + 16, sy + 16)), (x * 16, y * 16))
    scale = 2
    canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.Resampling.NEAREST)
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, canvas.width - 1, canvas.height - 1), outline=(255, 255, 255, 160))
    d.text((4, 4), f"Source {source_name}", fill=(255, 255, 255, 230))
    out = out_dir / "source_reference_preview.png"
    canvas.save(out)
    return out


def write_metadata(
    p: PrototypeMap,
    out_dir: Path,
    paths: Dict[str, str],
    validation: Dict,
    file_name: str = "metadata.json",
) -> Path:
    usage = Counter()
    by_layer = {}
    for layer, data in p.layers.items():
        c = Counter(local_id(g) for g in data if local_id(g) is not None)
        by_layer[layer] = {str(k): v for k, v in sorted(c.items())}
        usage.update(c)
    doc = {
        "generatedAt": now_iso(),
        "mapId": p.map_id,
        "title": p.title,
        "profile": "dungeon",
        "kind": p.kind,
        "sourceMap": p.source_map,
        "sourceOrigin": p.source_origin,
        "sourceReason": p.source_reason,
        "size": {"width": p.width, "height": p.height, "tileWidth": 16, "tileHeight": 16},
        "tilesheet": {
            "name": "mine.png",
            "sourcePath": str(TILESET_SRC.resolve()),
            "copiedPath": str((OUT_ROOT / "tilesheets" / "mine.png").resolve()),
            "columns": 16,
            "rows": 18,
            "tileCount": 288,
            "sourceStatus": "vanilla_basegame_tilesheet_read_only_source",
        },
        "entrance": {"x": p.entrance[0], "y": p.entrance[1]},
        "exit": {"x": p.exit[0], "y": p.exit[1]},
        "layerNames": list(p.layers.keys()),
        "tileUsageByLayer": by_layer,
        "tileUsageTotal": {str(k): v for k, v in sorted(usage.items())},
        "prototypeOnly": True,
        "provisionalUsage": [
            {
                "localTileId": r.local_id,
                "role": r.role,
                "layer": r.layer,
                "collision": r.collision,
                "confidence": r.confidence,
                "reason": r.reason,
            }
            for r in sorted(p.provisional_roles, key=lambda r: (r.layer, r.local_id))
        ],
        "paths": paths,
        "validation": validation,
        "tile946Status": "not_used",
    }
    out = out_dir / file_name
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def validate_prototype(p: PrototypeMap, tmx: Path, tmj: Path, tilesheet_rel: str) -> Dict:
    issues = []
    warnings = []
    # Parse output formats.
    try:
        ET.parse(tmx)
    except Exception as exc:
        issues.append(f"TMX parse failed: {exc}")
    try:
        json.loads(tmj.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"TMJ parse failed: {exc}")
    if not (tmx.parent / tilesheet_rel).resolve().exists():
        issues.append(f"Referenced tilesheet does not resolve: {tilesheet_rel}")
    # Tile 946 quarantine.
    for layer, data in p.layers.items():
        if any(local_id(g) == 946 for g in data):
            issues.append(f"Tile 946 found on {layer}; mine prototypes must not use tile 946.")
    # Boundary seal.
    edge_walkable = [(x, y) for x, y in p.walkable if x in (0, p.width - 1) or y in (0, p.height - 1)]
    if edge_walkable:
        issues.append(f"Walkable cells touch map edge: {edge_walkable[:10]}")
    # Reachability.
    reachable = set()
    q = deque([p.entrance])
    while q:
        cell = q.popleft()
        if cell in reachable:
            continue
        reachable.add(cell)
        for n in neighbors4(*cell):
            if n in p.walkable and n not in p.blocked and n not in reachable:
                q.append(n)
    if p.exit not in reachable:
        issues.append(f"Exit {p.exit} is not reachable from entrance {p.entrance}.")
    # Layer sanity.
    for y in range(p.height):
        for x in range(p.width):
            back = p.get_tile("Back", x, y)
            bld = p.get_tile("Buildings", x, y)
            front = p.get_tile("Front", x, y)
            af = p.get_tile("AlwaysFront", x, y)
            if bld is not None and back is None:
                issues.append(f"Buildings tile without Back support at {x},{y}")
            if af is not None:
                warnings.append(f"AlwaysFront used at {x},{y}; expected empty for mine prototypes.")
            if front is not None and back is None:
                warnings.append(f"Front tile without Back support at {x},{y}")
    result = {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "warnings": warnings[:100],
        "warningCount": len(warnings),
        "checks": {
            "tmxParsed": not any(i.startswith("TMX") for i in issues),
            "tmjParsed": not any(i.startswith("TMJ") for i in issues),
            "tilesheetResolved": not any("tilesheet" in i for i in issues),
            "entranceExitReachable": p.exit in reachable,
            "boundarySealed": not edge_walkable,
            "tile946Absent": not any(local_id(g) == 946 for data in p.layers.values() for g in data),
            "alwaysFrontEmpty": all(local_id(g) is None for g in p.layers["AlwaysFront"]),
        },
        "reachableTileCount": len(reachable),
        "walkableTileCount": len(p.walkable - p.blocked),
    }
    return result


def write_validation_report(
    p: PrototypeMap,
    out_dir: Path,
    validation: Dict,
    file_name: str = "validation_report.md",
) -> Path:
    lines = [
        f"# {p.title} Validation Report",
        "",
        f"- Status: {validation['status']}",
        f"- Entrance: `{p.entrance[0]},{p.entrance[1]}`",
        f"- Exit/ladder: `{p.exit[0]},{p.exit[1]}`",
        f"- Reachable tiles: {validation['reachableTileCount']}",
        f"- Walkable non-blocked tiles: {validation['walkableTileCount']}",
        f"- Tile 946 used: NO",
        f"- Production DB modified: NO",
        f"- mission_assets modified: NO",
        "",
        "## Checks",
    ]
    for key, value in validation["checks"].items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    if validation["issues"]:
        lines += ["", "## Issues"]
        lines += [f"- {issue}" for issue in validation["issues"]]
    if validation["warnings"]:
        lines += ["", "## Warnings"]
        lines += [f"- {warning}" for warning in validation["warnings"][:40]]
        if validation["warningCount"] > 40:
            lines.append(f"- ... {validation['warningCount'] - 40} additional warnings omitted from this report.")
    else:
        lines += ["", "## Warnings", "- None."]
    out = out_dir / file_name
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def side_by_side(
    source: Optional[Path],
    remake_preview: Path,
    out_dir: Path,
    file_name: str = "source_vs_remake_preview.png",
) -> Optional[Path]:
    if not source or not source.exists():
        return None
    a = Image.open(source).convert("RGBA")
    b = Image.open(remake_preview).convert("RGBA")
    # Scale source/remake down to comparable widths for contact.
    max_h = max(a.height, b.height)
    sheet = Image.new("RGBA", (a.width + b.width + 24, max_h), (18, 18, 22, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (a.width + 24, 0))
    d = ImageDraw.Draw(sheet)
    d.text((8, max(8, a.height - 24)), "source reference", fill=(255, 255, 255, 230))
    d.text((a.width + 32, max(8, b.height - 24)), "48x48 visual prototype", fill=(255, 255, 255, 230))
    out = out_dir / file_name
    sheet.save(out)
    return out


def write_reports(maps: List[PrototypeMap], outputs: Dict[str, Dict[str, str]], validations: Dict[str, Dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)

    source_lines = [
        "# Dungeon Visual Prototype Source Selection",
        "",
        "Two remake targets were selected from the unpacked vanilla base-game mine maps. These files were read only; no base-game or mission asset file was modified.",
        "",
    ]
    for p in maps:
        if p.kind == "remake":
            source_lines += [
                f"## {p.map_id}: {p.source_map}",
                f"- Source origin: {p.source_origin}",
                f"- Why chosen: {p.source_reason}",
                "- Safety: vanilla/base-game source map and vanilla `mine.png` tilesheet; remake output is isolated under `prototype_visual_maps/dungeon_review/`.",
                "",
            ]
    (REPORTS / "dungeon_visual_prototype_source_selection.md").write_text("\n".join(source_lines), encoding="utf-8")

    provisional = [
        "# Dungeon Visual Prototype Provisional Usage",
        "",
        "These tile roles were used for review prototypes only. They are not merged into `tile_database_v1_human_approved.json` and should become safe patterns or approved roles only after review.",
        "",
        "- Tilesheet source: `tools/tiled-map-assistant/mission_assets/unpacked_basegame/mine.png` read-only.",
        "- Copied review dependency: `tools/tiled-map-assistant/prototype_visual_maps/dungeon_review/tilesheets/mine.png`.",
        "- Tile 946: not used.",
        "",
    ]
    seen = set()
    for p in maps:
        provisional.append(f"## {p.map_id}")
        for r in sorted(p.provisional_roles, key=lambda r: (r.layer, r.local_id)):
            key = (p.map_id, r.local_id, r.layer)
            if key in seen:
                continue
            seen.add(key)
            provisional.append(f"- `{r.local_id}` on `{r.layer}`: {r.role}; collision `{r.collision}`; confidence {r.confidence}. {r.reason}")
        provisional.append("")
    (REPORTS / "dungeon_visual_prototype_provisional_usage.md").write_text("\n".join(provisional), encoding="utf-8")

    validation_lines = [
        "# Dungeon Visual Prototype Validation Summary",
        "",
        "| Map | Status | Reachable | Boundary sealed | Tile 946 absent | TMX/TMJ parse |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in maps:
        v = validations[p.map_id]
        validation_lines.append(
            f"| {p.map_id} | {v['status']} | {'PASS' if v['checks']['entranceExitReachable'] else 'FAIL'} | "
            f"{'PASS' if v['checks']['boundarySealed'] else 'FAIL'} | {'PASS' if v['checks']['tile946Absent'] else 'FAIL'} | "
            f"{'PASS' if v['checks']['tmxParsed'] and v['checks']['tmjParsed'] else 'FAIL'} |"
        )
    validation_lines += [
        "",
        "All validation here is prototype-specific visual-map validation: output parsing, tilesheet resolution, sealed bounds, entrance/exit reachability, layer sanity, and tile 946 quarantine.",
    ]
    (REPORTS / "dungeon_visual_prototype_validation_summary.md").write_text("\n".join(validation_lines) + "\n", encoding="utf-8")

    summary = [
        "# Dungeon Visual Prototype Review Summary",
        "",
        "Three visual mine/dungeon prototype maps were created for review using the vanilla base-game `mine.png` tilesheet. These are finished visual review artifacts, not marker-only maps, but the structural tile choices remain prototype-only until reviewed.",
        "",
        "## Maps Created",
        "",
    ]
    for p in maps:
        out = outputs[p.map_id]
        summary += [
            f"### {p.map_id}: {p.title}",
            f"- Type: {p.kind}",
            f"- Source/remake reference: {p.source_map or 'original custom layout'}",
            f"- TMX: `{out['tmx']}`",
            f"- TMJ: `{out['tmj']}`",
            f"- Clean preview: `{out['preview_clean']}`",
            f"- Labeled preview: `{out['preview_labeled']}`",
            f"- Validation: {validations[p.map_id]['status']}",
            "",
        ]
    summary += [
        "## Tilesheets Used",
        "",
        "- `mine.png`, copied from the read-only unpacked vanilla base-game source into the prototype review folder.",
        "",
        "## Approved vs Provisional",
        "",
        "- Production approval database was not modified.",
        "- Structural wall, edge, shadow, ladder, torch, chest, and ore/detail roles are documented as provisional prototype usage.",
        "- Tile 946 is not used in any prototype map.",
        "",
        "## What Looks Finished",
        "",
        "- All three maps render with real Stardew mine tiles, visible floors, cave walls, front shadows, ladders/exits, and review previews.",
        "- Entrance and exit/ladder positions are reachable in each semantic walkability check.",
        "",
        "## Still Needs Improvement",
        "",
        "- Cave wall/corner autotiling is good enough for visual review but still needs safe-pattern approval before production generation.",
        "- Ladder, torch, chest, ore, and shadow roles should be converted into reviewed safe patterns if these visuals are accepted.",
        "",
        "## Recommended Next Approval Targets",
        "",
        "- `cave_wall_body`, `cave_wall_edge`, `cave_wall_corner`, `cave_shadow`, `cave_floor_variation`, `ladder`, and small mine decoration/ore patterns.",
    ]
    (REPORTS / "dungeon_visual_prototype_review_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def make_contact_sheet(outputs: Dict[str, Dict[str, str]]) -> Path:
    imgs = []
    labels = []
    for map_id in ["remake_01", "remake_02", "custom_03"]:
        p = Path(outputs[map_id]["preview_labeled"])
        img = Image.open(p).convert("RGBA")
        # Half scale for compact sheet.
        img = img.resize((img.width // 2, img.height // 2), Image.Resampling.NEAREST)
        imgs.append(img)
        labels.append(map_id)
    pad = 16
    w = sum(i.width for i in imgs) + pad * (len(imgs) + 1)
    h = max(i.height for i in imgs) + 56
    sheet = Image.new("RGBA", (w, h), (18, 18, 22, 255))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 12), "Dungeon visual prototype review contact sheet", fill=(255, 255, 255, 240))
    x = pad
    for label, img in zip(labels, imgs):
        y = 42
        sheet.alpha_composite(img, (x, y))
        d.text((x, y + img.height + 4), label, fill=(255, 255, 255, 220))
        x += img.width + pad
    out = OUT_ROOT / "dungeon_review_contact_sheet.png"
    sheet.save(out)
    return out


def main() -> int:
    if os.environ.get("ALLOW_UNSAFE_MINE_WALL_GENERATOR") != "1":
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "mine_visual_generation_freeze.md").write_text(
            "\n".join([
                "# Mine Visual Generation Freeze",
                "",
                "`build_dungeon_visual_prototypes.py` is frozen by default because it uses legacy single-tile mine wall role lists.",
                "",
                "- Default behavior: fail closed without generating new visual maps.",
                "- To inspect the historical output path only, set `ALLOW_UNSAFE_MINE_WALL_GENERATOR=1` explicitly.",
                "- Current safe visual mine/dungeon output should use `build_golden_mine_template_prototypes.py` or `generate_visual_map_v2.py`, which route wall structures through golden vanilla templates.",
                "- Marker-only fallback remains available.",
                "- Production maps are not generated by this script.",
            ]) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "FROZEN",
            "reason": "Legacy mine wall generation uses individual role-list tiles. Use golden template resolver instead.",
            "overrideForHistoricalInspection": "set ALLOW_UNSAFE_MINE_WALL_GENERATOR=1",
        }, indent=2))
        return 0
    if not TILESET_SRC.exists():
        raise SystemExit(f"Missing vanilla mine tilesheet: {TILESET_SRC}")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "tilesheets").mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    copied_tilesheet = OUT_ROOT / "tilesheets" / "mine.png"
    shutil.copy2(TILESET_SRC, copied_tilesheet)
    tilesheet = Image.open(copied_tilesheet).convert("RGBA")

    prototypes = [make_remake_01(), make_remake_02(), make_custom_03()]
    outputs: Dict[str, Dict[str, str]] = {}
    validations: Dict[str, Dict] = {}
    for p in prototypes:
        finalize_map(p)
        out_dir = OUT_ROOT / p.map_id
        out_dir.mkdir(parents=True, exist_ok=True)
        tilesheet_rel = "../tilesheets/mine.png"
        tmx = write_tmx(p, out_dir, tilesheet_rel)
        tmj = write_tmj(p, out_dir, tilesheet_rel)
        clean, labeled = render_map(p, tilesheet, out_dir)
        source_preview = render_source_reference(p.source_map, out_dir)
        side = side_by_side(source_preview, clean, out_dir)
        validation = validate_prototype(p, tmx, tmj, tilesheet_rel)
        validations[p.map_id] = validation
        validation_report = write_validation_report(p, out_dir, validation)
        paths = {
            "tmx": str(tmx.resolve()),
            "tmj": str(tmj.resolve()),
            "preview_clean": str(clean.resolve()),
            "preview_labeled": str(labeled.resolve()),
            "source_reference_preview": str(source_preview.resolve()) if source_preview else "",
            "source_vs_remake_preview": str(side.resolve()) if side else "",
            "validation_report": str(validation_report.resolve()),
        }
        metadata = write_metadata(p, out_dir, paths, validation)
        paths["metadata"] = str(metadata.resolve())
        outputs[p.map_id] = paths

    contact = make_contact_sheet(outputs)
    outputs["contact_sheet"] = {"path": str(contact.resolve())}
    (OUT_ROOT / "dungeon_visual_prototype_outputs.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    write_reports(prototypes, outputs, validations)

    failed = [map_id for map_id, v in validations.items() if v["status"] != "PASS"]
    print(json.dumps({
        "status": "PASS" if not failed else "FAIL",
        "outputRoot": str(OUT_ROOT.resolve()),
        "contactSheet": str(contact.resolve()),
        "failedMaps": failed,
    }, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
