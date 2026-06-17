#!/usr/bin/env python3
"""Semantic dungeon layout loading for Smart Edge-Wrapper renderers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import build_dungeon_visual_prototypes as base

SCHEMA = "semantic_dungeon_layout_v1"


@dataclass
class SemanticLayout:
    map_id: str
    title: str
    width: int
    height: int
    seed: int
    entrance: tuple[int, int]
    exit: tuple[int, int]
    floor_mask: set[tuple[int, int]]
    special_markers: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    graph_debug: dict = field(default_factory=dict)


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"missing required field: {key}")
    return data[key]


def _parse_point(value: Any, field_name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field_name} must be a two-item [x, y] list")
    x, y = value
    if not isinstance(x, int) or not isinstance(y, int):
        raise ValueError(f"{field_name} coordinates must be integers")
    return (x, y)


def _parse_point_list(value: Any, field_name: str) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of [x, y] points")
    return [_parse_point(point, f"{field_name}[{i}]") for i, point in enumerate(value)]


def load_semantic_layout_json(path: str | Path) -> SemanticLayout:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("layout JSON root must be an object")
    schema = _require(data, "schema")
    if schema != SCHEMA:
        raise ValueError(f"unsupported schema {schema!r}; expected {SCHEMA!r}")

    map_id = _require(data, "mapId")
    title = _require(data, "title")
    width = _require(data, "width")
    height = _require(data, "height")
    seed = _require(data, "seed")
    if not isinstance(map_id, str) or not map_id:
        raise ValueError("mapId must be a non-empty string")
    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    if not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer")
    if not isinstance(height, int) or height <= 0:
        raise ValueError("height must be a positive integer")
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")

    floor_mask = set(_parse_point_list(_require(data, "floorMask"), "floorMask"))
    special_marker_data = data.get("specialMarkers", {})
    if not isinstance(special_marker_data, dict):
        raise ValueError("specialMarkers must be an object mapping marker names to point lists")
    special_markers = {
        str(name): _parse_point_list(points, f"specialMarkers.{name}")
        for name, points in special_marker_data.items()
    }
    graph_debug = data.get("graphDebug", {})
    if not isinstance(graph_debug, dict):
        raise ValueError("graphDebug must be an object")

    return SemanticLayout(
        map_id=map_id,
        title=title,
        width=width,
        height=height,
        seed=seed,
        entrance=_parse_point(_require(data, "entrance"), "entrance"),
        exit=_parse_point(_require(data, "exit"), "exit"),
        floor_mask=floor_mask,
        special_markers=special_markers,
        graph_debug=graph_debug,
    )


def prototype_from_semantic_layout(layout: SemanticLayout) -> base.PrototypeMap:
    p = base.PrototypeMap(
        map_id=layout.map_id,
        title=layout.title,
        kind="generated",
        source_map=None,
        source_origin="semantic dungeon layout generated from graph-first pipeline",
        source_reason="Generated floor mask rendered by Smart Edge-Wrapper v2.",
        width=layout.width,
        height=layout.height,
        seed=layout.seed,
        floor_style="earth",
        entrance=layout.entrance,
        exit=layout.exit,
    )
    p.floor_mask = set(layout.floor_mask)
    p.special_markers = {name: list(points) for name, points in layout.special_markers.items()}
    return p


def prototype_from_layout_json(path: str | Path) -> base.PrototypeMap:
    return prototype_from_semantic_layout(load_semantic_layout_json(path))
