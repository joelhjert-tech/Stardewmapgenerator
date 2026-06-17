#!/usr/bin/env python3
"""Generate graph-first semantic dungeon layout JSON."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from dungeon_graph import DungeonEdge, DungeonGraph
from dungeon_layout_planner import plan_layout
from dungeon_rasterizer import rasterize_layout
from dungeon_spec import DungeonSpec
from dungeon_topology_generator import generate_topology
from semantic_layout import SCHEMA


def write_semantic_layout_json(data: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True)
    out_path.write_text(text + "\n", encoding="utf-8")


def _sorted_edges(edges: list[DungeonEdge]) -> list[dict[str, str]]:
    return [
        {"a": e.a, "b": e.b, "kind": e.kind}
        for e in sorted(edges, key=lambda e: (e.kind, min(e.a, e.b), max(e.a, e.b)))
    ]


def build_semantic_layout_data(spec: DungeonSpec, allow_partial_loops: bool = False) -> dict[str, Any]:
    rng = random.Random(spec.seed)
    graph = generate_topology(spec, rng, allow_partial_loops=allow_partial_loops)
    rooms = plan_layout(graph, spec, rng)
    floor_mask, special_markers, entrance, exit = rasterize_layout(graph, rooms, spec, rng)
    return {
        "schema": SCHEMA,
        "mapId": f"generated_seed_{spec.seed}",
        "title": f"Generated Dungeon Seed {spec.seed}",
        "width": spec.width,
        "height": spec.height,
        "seed": spec.seed,
        "entrance": [entrance[0], entrance[1]],
        "exit": [exit[0], exit[1]],
        "floorMask": [[x, y] for x, y in sorted(floor_mask, key=lambda p: (p[1], p[0]))],
        "specialMarkers": {
            name: [[x, y] for x, y in sorted(points, key=lambda p: (p[1], p[0]))]
            for name, points in sorted(special_markers.items())
        },
        "graphDebug": _graph_debug(graph, rooms, spec, floor_mask),
    }


def _graph_debug(
    graph: DungeonGraph,
    rooms: dict,
    spec: DungeonSpec,
    floor_mask: set[tuple[int, int]],
) -> dict[str, Any]:
    loop_edges = sorted(
        (item for item in graph.loop_debug if "a" in item),
        key=lambda item: (item["a"], item["b"], item["hopsBeforeAdded"]),
    )
    warnings = sorted(item["warning"] for item in graph.loop_debug if "warning" in item)
    debug = {
        "mainPathRooms": spec.main_path_rooms,
        "sideBranches": spec.side_branches,
        "requestedLoops": spec.loops,
        "actualLoops": len([edge for edge in graph.edges if edge.kind == "loop"]),
        "minLoopHops": spec.min_loop_hops,
        "loopEdges": loop_edges,
        "nodeCount": len(graph.nodes),
        "edgeCount": len(graph.edges),
        "floorCells": len(floor_mask),
        "nodes": [
            {
                "id": node_id,
                "kind": room.kind,
                "x": room.x,
                "y": room.y,
                "rx": room.rx,
                "ry": room.ry,
            }
            for node_id, room in sorted(rooms.items())
        ],
        "edges": _sorted_edges(graph.edges),
    }
    if warnings:
        debug["warnings"] = warnings
    return debug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate semantic dungeon layout JSON.")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--width", type=int, default=96)
    parser.add_argument("--height", type=int, default=96)
    parser.add_argument("--main-path-rooms", type=int, default=12)
    parser.add_argument("--side-branches", type=int, default=4)
    parser.add_argument("--loops", type=int, default=2)
    parser.add_argument("--min-loop-hops", type=int, default=3)
    parser.add_argument("--min-room-radius", type=int, default=4)
    parser.add_argument("--max-room-radius", type=int, default=9)
    parser.add_argument("--corridor-width", type=int, default=2)
    parser.add_argument("--margin", type=int, default=8)
    parser.add_argument("--torch-count", type=int, default=8)
    parser.add_argument("--allow-partial-loops", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def spec_from_args(args: argparse.Namespace) -> DungeonSpec:
    return DungeonSpec(
        seed=args.seed,
        width=args.width,
        height=args.height,
        main_path_rooms=args.main_path_rooms,
        side_branches=args.side_branches,
        loops=args.loops,
        min_loop_hops=args.min_loop_hops,
        min_room_radius=args.min_room_radius,
        max_room_radius=args.max_room_radius,
        corridor_width=args.corridor_width,
        margin=args.margin,
        torch_count=args.torch_count,
    )


def main() -> int:
    args = parse_args()
    spec = spec_from_args(args)
    try:
        data = build_semantic_layout_data(spec, allow_partial_loops=args.allow_partial_loops)
    except ValueError as exc:
        print(json.dumps({
            "status": "FAIL",
            "issue": str(exc),
            "requestedLoops": spec.loops,
            "minLoopHops": spec.min_loop_hops,
        }, indent=2, sort_keys=True))
        return 1
    write_semantic_layout_json(data, args.out)
    graph_debug = data["graphDebug"]
    print(json.dumps({
        "status": "PASS",
        "out": str(args.out.resolve()),
        "roomCount": graph_debug["nodeCount"],
        "edgeCount": graph_debug["edgeCount"],
        "branchCount": spec.side_branches,
        "requestedLoops": graph_debug["requestedLoops"],
        "actualLoops": graph_debug["actualLoops"],
        "minLoopHops": graph_debug["minLoopHops"],
        "loopEdgeHopDistances": [edge["hopsBeforeAdded"] for edge in graph_debug["loopEdges"]],
        "floorCellCount": len(data["floorMask"]),
        "entrance": data["entrance"],
        "exit": data["exit"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
