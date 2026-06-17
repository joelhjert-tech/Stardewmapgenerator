#!/usr/bin/env python3
"""Rasterize planned semantic rooms into floor masks and markers."""
from __future__ import annotations

import random

from dungeon_graph import DungeonGraph
from dungeon_layout_planner import PlannedRoom
from dungeon_spec import DungeonSpec


def _add_ellipse(mask: set[tuple[int, int]], cx: int, cy: int, rx: int, ry: int, width: int, height: int) -> None:
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if 0 <= x < width and 0 <= y < height:
                dx = (x - cx) / max(1, rx)
                dy = (y - cy) / max(1, ry)
                if dx * dx + dy * dy <= 1.0:
                    mask.add((x, y))


def _add_disc(mask: set[tuple[int, int]], cx: int, cy: int, radius: int, width: int, height: int) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if 0 <= x < width and 0 <= y < height:
                mask.add((x, y))


def _carve_corridor(
    mask: set[tuple[int, int]],
    start: tuple[int, int],
    end: tuple[int, int],
    corridor_width: int,
    width: int,
    height: int,
) -> None:
    sx, sy = start
    ex, ey = end
    steps = max(abs(ex - sx), abs(ey - sy), 1)
    radius = max(1, corridor_width)
    for i in range(steps + 1):
        t = i / steps
        x = round(sx + (ex - sx) * t)
        y = round(sy + (ey - sy) * t)
        _add_disc(mask, x, y, radius, width, height)


def rasterize_layout(
    graph: DungeonGraph,
    rooms: dict[str, PlannedRoom],
    spec: DungeonSpec,
    rng: random.Random,
) -> tuple[set[tuple[int, int]], dict[str, list[tuple[int, int]]], tuple[int, int], tuple[int, int]]:
    floor_mask: set[tuple[int, int]] = set()
    for room in rooms.values():
        _add_ellipse(floor_mask, room.x, room.y, room.rx, room.ry, spec.width, spec.height)

    for edge in graph.edges:
        a = rooms[edge.a]
        b = rooms[edge.b]
        _carve_corridor(floor_mask, (a.x, a.y), (b.x, b.y), spec.corridor_width, spec.width, spec.height)

    entrance_room = rooms["main_00"]
    exit_room = rooms[f"main_{spec.main_path_rooms - 1:02d}"]
    entrance = (entrance_room.x, entrance_room.y)
    exit = (exit_room.x, exit_room.y)
    floor_mask.add(entrance)
    floor_mask.add(exit)

    candidates = sorted(
        (point for point in floor_mask if point not in {entrance, exit}),
        key=lambda p: (p[1], p[0]),
    )
    torch_count = min(spec.torch_count, len(candidates))
    torches = sorted(rng.sample(candidates, torch_count), key=lambda p: (p[1], p[0])) if torch_count else []
    special_markers = {"torches": torches, "ore": [], "chests": []}
    return floor_mask, special_markers, entrance, exit
