#!/usr/bin/env python3
"""Strict golden-template resolver for mine/dungeon prototype maps.

This resolver intentionally refuses the old single-tile wall-picking behavior.
Mine wall/corner/opening visual tiles may only enter the output as cells from a
source-stamped vanilla template placement.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "pattern_learning" / "tile_grammar_templates" / "golden_vanilla_mine_templates"
STARTER_SET = GOLDEN_DIR / "golden_mine_starter_set.json"
FIRSTGID = 1

TilePoint = Tuple[int, int]

WALL_IDS = {
    68, 69, 70, 71, 72, 73, 74, 75, 76,
    84, 85, 86, 87, 88, 89, 90, 91, 92,
    93, 94, 100, 101, 102, 103, 104, 105, 106,
    107, 108, 109, 110, 116, 117, 118, 119, 120,
    121, 122, 123, 124, 125, 126, 132, 133, 134,
    141, 142, 148, 157, 158, 159, 191, 196, 207,
}
FRONT_WALL_OR_SHADOW_IDS = {196, 197, 205, 206, 213, 214, 215, 216, 220, 221, 232}
UNDER_WALL_BACK_IDS = {186}
LADDER_IDS = {67, 83, 99, 115}
MINE_WALL_RESTRICTED_IDS = WALL_IDS | FRONT_WALL_OR_SHADOW_IDS | UNDER_WALL_BACK_IDS | LADDER_IDS
CRITICAL_ROLES = {
    "floor_base",
    "straight_horizontal_wall",
    "wall_body",
    "left_edge",
    "right_edge",
    "shadow_under_wall",
    "ladder_opening",
    "blocked_boundary",
}


def gid(local_tile_id: Optional[int]) -> int:
    return 0 if local_tile_id is None else int(local_tile_id) + FIRSTGID


def local_id(gid_value: int) -> Optional[int]:
    return None if gid_value <= 0 else int(gid_value) - FIRSTGID


def hpick(options: Sequence[str], x: int, y: int, seed: int) -> str:
    if not options:
        raise ValueError("empty options")
    n = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    return options[n & 0xFFFFFFFF % len(options)]


def neighbors4(x: int, y: int) -> Iterable[TilePoint]:
    yield x, y - 1
    yield x + 1, y
    yield x, y + 1
    yield x - 1, y


class GoldenMineTemplateResolver:
    """Stamp-only resolver for mine wall structures."""

    def __init__(self, starter_set_path: Path = STARTER_SET):
        self.starter_set_path = starter_set_path
        self.templates_by_role: Dict[str, List[dict]] = {}
        self.templates_by_id: Dict[str, dict] = {}
        self.load_errors: List[str] = []
        self._load()

    def _load(self) -> None:
        if not self.starter_set_path.exists():
            self.load_errors.append(f"Missing starter set: {self.starter_set_path}")
            return
        try:
            doc = json.loads(self.starter_set_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.load_errors.append(f"Could not parse starter set: {exc}")
            return
        for template in doc.get("templates", []):
            role = template.get("role")
            tid = template.get("templateId")
            if not role or not tid:
                continue
            if 946 in {int(v) for v in template.get("localTileIdsUsed", [])}:
                self.load_errors.append(f"{tid} contains tile 946, forbidden for mine templates.")
                continue
            self.templates_by_role.setdefault(role, []).append(template)
            self.templates_by_id[tid] = template

    def missing_required_roles(self) -> List[str]:
        return sorted(role for role in CRITICAL_ROLES if not self.templates_by_role.get(role))

    def can_generate_visual_walls(self) -> bool:
        return not self.load_errors and not self.missing_required_roles()

    def _build_wall_mask(self, floor: Set[TilePoint], width: int, height: int) -> Set[TilePoint]:
        wall: Set[TilePoint] = set()
        for x, y in floor:
            for nx, ny in neighbors4(x, y):
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in floor:
                    wall.add((nx, ny))
        return wall

    def _nearest_floor_vector(self, x: int, y: int, floor: Set[TilePoint], max_radius: int = 2) -> Optional[Tuple[int, int, int]]:
        best = None
        best_score = 999
        for fy in range(y - max_radius, y + max_radius + 1):
            for fx in range(x - max_radius, x + max_radius + 1):
                if (fx, fy) not in floor:
                    continue
                dist = abs(fx - x) + abs(fy - y)
                if dist <= 0 or dist > max_radius:
                    continue
                bias = 0 if fy > y else (2 if fx != x else 4)
                score = dist * 10 + bias
                if score < best_score:
                    best = (fx - x, fy - y, dist)
                    best_score = score
        return best

    def _role_for_wall_cell(self, x: int, y: int, floor: Set[TilePoint]) -> str:
        n = (x, y - 1) in floor
        e = (x + 1, y) in floor
        s = (x, y + 1) in floor
        w = (x - 1, y) in floor
        ne = (x + 1, y - 1) in floor
        nw = (x - 1, y - 1) in floor
        se = (x + 1, y + 1) in floor
        sw = (x - 1, y + 1) in floor
        if s and not n:
            return "straight_horizontal_wall"
        if e and not w:
            return "left_edge"
        if w and not e:
            return "right_edge"
        if se:
            return "upper_left_corner"
        if sw:
            return "upper_right_corner"
        if ne:
            return "lower_left_corner"
        if nw:
            return "lower_right_corner"
        if n:
            return "wall_body"
        return "blocked_boundary"

    def _choose_template(self, role: str, x: int, y: int, seed: int) -> Optional[dict]:
        candidates = self.templates_by_role.get(role) or []
        if not candidates and role in {"upper_left_corner", "upper_right_corner", "lower_left_corner", "lower_right_corner"}:
            candidates = self.templates_by_role.get("inner_corner") or self.templates_by_role.get("straight_horizontal_wall") or []
        if not candidates and role == "blocked_boundary":
            candidates = self.templates_by_role.get("wall_body") or []
        if not candidates:
            return None
        index = ((x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)) & 0xFFFFFFFF
        return candidates[index % len(candidates)]

    def _stamp_template(self, p, template: dict, anchor_x: int, anchor_y: int, reason: str, priority: int) -> bool:
        placement_cells: List[dict] = []
        # Reject hard conflicts on non-Back layers. Back may be overwritten by
        # golden source context because source windows include floor/shadow.
        for cell in template.get("cells", []):
            layer = cell["layer"]
            x = anchor_x + int(cell["dx"])
            y = anchor_y + int(cell["dy"])
            if not (0 <= x < p.width and 0 <= y < p.height):
                return False
            new_gid = gid(cell["localTileId"])
            old_gid = p.layers[layer][p.idx(x, y)]
            if layer != "Back" and old_gid not in (0, new_gid):
                return False
            placement_cells.append({
                "x": x,
                "y": y,
                "layer": layer,
                "localTileId": int(cell["localTileId"]),
                "sourceDx": int(cell["dx"]),
                "sourceDy": int(cell["dy"]),
            })
        for out in placement_cells:
            p.set_tile(out["layer"], out["x"], out["y"], out["localTileId"])
            tid = out["localTileId"]
            if out["layer"] == "Buildings" and tid in WALL_IDS:
                p.blocked.add((out["x"], out["y"]))
                p.walkable.discard((out["x"], out["y"]))
            if out["layer"] == "Buildings" and tid in LADDER_IDS:
                p.blocked.discard((out["x"], out["y"]))
                p.walkable.add((out["x"], out["y"]))
        p.golden_template_placements.append({
            "templateId": template["templateId"],
            "role": template["role"],
            "anchor": {"x": anchor_x, "y": anchor_y},
            "sourceMapName": template.get("sourceMapName"),
            "sourceCoordinate": template.get("sourceCoordinate"),
            "reason": reason,
            "priority": priority,
            "cells": placement_cells,
        })
        return True

    def _fill_floors(self, p) -> None:
        base = self._choose_template("floor_base", 0, 0, p.seed)
        variation = self._choose_template("floor_variation", 1, 1, p.seed)
        if not base:
            return
        for x, y in sorted(p.floor_mask):
            template = variation if variation and (x * 17 + y * 31 + p.seed) % 11 == 0 else base
            self._stamp_template(p, template, x, y, "floor fill from golden vanilla floor template", 90)
            p.walkable.add((x, y))
            p.blocked.discard((x, y))

    def apply(self, p) -> dict:
        p.golden_template_placements = []
        p.golden_template_missing = []
        p.golden_template_mode = "golden_vanilla_templates_only"
        if not self.can_generate_visual_walls():
            p.golden_template_missing = self.load_errors + self.missing_required_roles()
            p.golden_template_mode = "marker_only_required_missing_golden_template"
            return {"status": "FALLBACK_REQUIRED", "missing": p.golden_template_missing}
        for layer_name in ("Buildings", "Front", "AlwaysFront"):
            for y in range(p.height):
                for x in range(p.width):
                    p.set_tile(layer_name, x, y, None)
        p.blocked.clear()
        p.walkable.clear()
        self._fill_floors(p)
        p.wall_mask = self._build_wall_mask(p.floor_mask, p.width, p.height)
        # Openings first, as requested.
        for x, y in [p.exit]:
            template = self._choose_template("ladder_opening", x, y, p.seed)
            if template:
                self._stamp_template(p, template, x, y, "exit/ladder opening golden placement", 10)
                for ay in range(y, min(p.height, y + 3)):
                    for ax in range(x - 1, x + 2):
                        if 0 <= ax < p.width and 0 <= ay < p.height:
                            p.floor_mask.add((ax, ay))
                            p.walkable.add((ax, ay))
                            p.blocked.discard((ax, ay))
        # Corners/edges/body are all complete source-window stamps.
        ordered_wall = sorted(p.wall_mask, key=lambda pt: (pt[1], pt[0]))
        for x, y in ordered_wall:
            role = self._role_for_wall_cell(x, y, p.floor_mask)
            template = self._choose_template(role, x, y, p.seed)
            if template:
                self._stamp_template(p, template, x, y, f"{role} wall boundary golden placement", 30)
            else:
                p.golden_template_missing.append(role)
        # Shadow pass is still stamped as a template, never as a single ID.
        for x, y in sorted(p.floor_mask):
            if (x, y - 1) in p.wall_mask:
                template = self._choose_template("shadow_under_wall", x, y, p.seed)
                if template:
                    self._stamp_template(p, template, x, y, "under-wall shadow golden placement", 60)
                else:
                    p.golden_template_missing.append("shadow_under_wall")
        self._clear_semantic_floor_blockers(p)
        for cell in [p.entrance, p.exit]:
            p.walkable.add(cell)
            p.blocked.discard(cell)
        return {
            "status": "PASS" if not p.golden_template_missing else "PASS_WITH_MISSING_MARKERS",
            "missing": sorted(set(p.golden_template_missing)),
            "placements": len(p.golden_template_placements),
        }

    def _clear_semantic_floor_blockers(self, p) -> None:
        """Keep generated semantic floor walkable after large source-window stamps.

        This removes wall spillover from floor cells; it never places a wall tile.
        Ladder cells are kept as walkable special cells.
        """
        for x, y in sorted(p.floor_mask):
            b = p.get_tile("Buildings", x, y)
            if b in LADDER_IDS:
                p.walkable.add((x, y))
                p.blocked.discard((x, y))
                continue
            if b in WALL_IDS:
                p.set_tile("Buildings", x, y, None)
            p.walkable.add((x, y))
            p.blocked.discard((x, y))
        # Entrance must stay visibly open and readable.
        ex, ey = p.entrance
        floor_template = self._choose_template("floor_base", ex, ey, p.seed)
        for y in range(ey - 1, ey + 2):
            for x in range(ex - 1, ex + 2):
                if 0 <= x < p.width and 0 <= y < p.height:
                    p.set_tile("Buildings", x, y, None)
                    p.set_tile("Front", x, y, None)
                    if floor_template:
                        self._stamp_template(p, floor_template, x, y, "protected entrance floor reset", 95)
                    p.walkable.add((x, y))
                    p.blocked.discard((x, y))


__all__ = [
    "GoldenMineTemplateResolver",
    "MINE_WALL_RESTRICTED_IDS",
    "WALL_IDS",
    "FRONT_WALL_OR_SHADOW_IDS",
    "UNDER_WALL_BACK_IDS",
    "LADDER_IDS",
]
