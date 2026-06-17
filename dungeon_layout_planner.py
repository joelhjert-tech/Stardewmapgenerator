#!/usr/bin/env python3
"""Place graph nodes into map-space rooms."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from dungeon_graph import DungeonGraph
from dungeon_spec import DungeonSpec


@dataclass(frozen=True)
class PlannedRoom:
    node_id: str
    x: int
    y: int
    rx: int
    ry: int
    kind: str


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def plan_layout(graph: DungeonGraph, spec: DungeonSpec, rng: random.Random) -> dict[str, PlannedRoom]:
    if spec.width <= spec.margin * 2 or spec.height <= spec.margin * 2:
        raise ValueError("width and height must be larger than twice the margin")
    rooms: dict[str, PlannedRoom] = {}
    min_x = spec.margin
    max_x = spec.width - spec.margin - 1
    min_y = spec.margin
    max_y = spec.height - spec.margin - 1

    for i in range(spec.main_path_rooms):
        node_id = f"main_{i:02d}"
        t = i / max(1, spec.main_path_rooms - 1)
        base_x = round(min_x + t * (max_x - min_x))
        base_y = round(max_y - t * (max_y - min_y))
        jitter_x = rng.randint(-3, 3)
        jitter_y = rng.randint(-3, 3)
        rx = rng.randint(spec.min_room_radius, spec.max_room_radius)
        ry = rng.randint(spec.min_room_radius, spec.max_room_radius)
        x = _clamp(base_x + jitter_x, rx + 1, spec.width - rx - 2)
        y = _clamp(base_y + jitter_y, ry + 1, spec.height - ry - 2)
        rooms[node_id] = PlannedRoom(node_id=node_id, x=x, y=y, rx=rx, ry=ry, kind="main")

    branch_edges = [edge for edge in graph.edges if edge.kind == "branch"]
    for i, edge in enumerate(branch_edges):
        branch_id = edge.a if edge.a.startswith("branch_") else edge.b
        parent_id = edge.b if branch_id == edge.a else edge.a
        parent = rooms[parent_id]
        angle = (i * 2.399963229728653 + rng.uniform(-0.35, 0.35)) % (math.pi * 2)
        distance = rng.randint(spec.max_room_radius * 2 + 3, spec.max_room_radius * 3 + 8)
        rx = rng.randint(spec.min_room_radius, spec.max_room_radius - 1)
        ry = rng.randint(spec.min_room_radius, spec.max_room_radius - 1)
        x = _clamp(round(parent.x + math.cos(angle) * distance), rx + 1, spec.width - rx - 2)
        y = _clamp(round(parent.y + math.sin(angle) * distance), ry + 1, spec.height - ry - 2)
        rooms[branch_id] = PlannedRoom(node_id=branch_id, x=x, y=y, rx=rx, ry=ry, kind="branch")

    return rooms
