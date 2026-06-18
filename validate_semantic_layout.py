#!/usr/bin/env python3
"""Validate semantic dungeon layout JSON before rendering."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

from dungeon_graph import DungeonEdge, DungeonGraph, DungeonNode
from dungeon_locking import (
    edge_without_direction,
    is_bridge_edge,
    main_index,
    nearest_floor_tile,
    reachable_nodes,
    sorted_main_nodes,
)
from semantic_layout import SemanticLayout, load_semantic_layout_json


def _in_bounds(layout: SemanticLayout, point: tuple[int, int]) -> bool:
    x, y = point
    return 0 <= x < layout.width and 0 <= y < layout.height


def _reachable_floor(layout: SemanticLayout) -> set[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque([layout.entrance])
    while queue:
        point = queue.popleft()
        if point in seen or point not in layout.floor_mask:
            continue
        seen.add(point)
        x, y = point
        for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if neighbor not in seen and neighbor in layout.floor_mask:
                queue.append(neighbor)
    return seen


def _point_from_lock(lock: dict[str, Any], key: str, issues: list[str]) -> tuple[int, int] | None:
    value = lock.get(key)
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(n, int) for n in value):
        issues.append(f"{lock.get('lockId', '<unknown>')}: {key} must be [x, y]")
        return None
    return (value[0], value[1])


def _inside_or_adjacent_to_floor(point: tuple[int, int], floor_mask: set[tuple[int, int]]) -> bool:
    x, y = point
    for yy in range(y - 1, y + 2):
        for xx in range(x - 1, x + 2):
            if (xx, yy) in floor_mask:
                return True
    return False


def _graph_from_debug(graph_debug: dict[str, Any], issues: list[str]) -> DungeonGraph | None:
    nodes_raw = graph_debug.get("nodes")
    edges_raw = graph_debug.get("edges")
    if not isinstance(nodes_raw, list):
        issues.append("graphDebug.nodes must be a list for route-lock validation")
        return None
    if not isinstance(edges_raw, list):
        issues.append("graphDebug.edges must be a list for route-lock validation")
        return None

    nodes: dict[str, DungeonNode] = {}
    for raw in nodes_raw:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            issues.append("graphDebug.nodes entries must include string id")
            return None
        node_id = raw["id"]
        idx = main_index(node_id)
        if idx is None:
            idx = int(raw.get("index", 0)) if isinstance(raw.get("index", 0), int) else 0
        kind = str(raw.get("kind", "unknown"))
        nodes[node_id] = DungeonNode(node_id=node_id, kind=kind, index=idx)

    edges: list[DungeonEdge] = []
    for raw in edges_raw:
        if not isinstance(raw, dict):
            issues.append("graphDebug.edges entries must be objects")
            return None
        a = raw.get("a")
        b = raw.get("b")
        kind = raw.get("kind")
        if not isinstance(a, str) or not isinstance(b, str) or not isinstance(kind, str):
            issues.append("graphDebug.edges entries must include string a, b, and kind")
            return None
        edges.append(DungeonEdge(a=a, b=b, kind=kind))

    return DungeonGraph(nodes=nodes, edges=edges, loop_debug=[])


def validate_route_locks(layout: SemanticLayout) -> dict[str, Any]:
    issues: list[str] = []
    details: list[dict[str, Any]] = []
    locks = layout.route_locks
    if not locks:
        return {"status": "PASS", "lockCount": 0, "locks": []}

    graph = _graph_from_debug(layout.graph_debug, issues)
    if graph is None:
        return {"status": "FAIL", "lockCount": len(locks), "locks": [], "issues": issues}
    node_ids = set(graph.nodes)
    edge_keys = {edge_without_direction(edge.a, edge.b) for edge in graph.edges}
    main_nodes = sorted_main_nodes(graph)
    final_main = main_nodes[-1] if main_nodes else None
    full_reachable = reachable_nodes(graph, "main_00") if "main_00" in node_ids else set()

    for i, lock in enumerate(locks):
        if not isinstance(lock, dict):
            issues.append(f"routeLocks[{i}] must be an object")
            continue
        lock_id = lock.get("lockId")
        style = lock.get("style")
        gate_edge = lock.get("gateEdge")
        key_node = lock.get("keyNode")
        if not isinstance(lock_id, str) or not lock_id:
            issues.append(f"routeLocks[{i}] missing lockId")
            lock_id = f"routeLocks[{i}]"
        if style not in {"switch", "key"}:
            issues.append(f"{lock_id}: style must be switch or key")
        if not isinstance(gate_edge, list) or len(gate_edge) != 2 or not all(isinstance(n, str) for n in gate_edge):
            issues.append(f"{lock_id}: gateEdge must be two node IDs")
            continue
        if not isinstance(key_node, str):
            issues.append(f"{lock_id}: keyNode must be a node ID")
            key_node = ""
        gate_marker = _point_from_lock(lock, "gateMarker", issues)
        key_marker = _point_from_lock(lock, "keyMarker", issues)

        for marker_name, point in (("gateMarker", gate_marker), ("keyMarker", key_marker)):
            if point is None:
                continue
            if not _in_bounds(layout, point):
                issues.append(f"{lock_id}: {marker_name} {point} is out of bounds")
            if not _inside_or_adjacent_to_floor(point, layout.floor_mask):
                issues.append(f"{lock_id}: {marker_name} {point} is not inside or adjacent to floorMask")

        a, b = gate_edge
        if a not in node_ids or b not in node_ids:
            issues.append(f"{lock_id}: gateEdge refers to missing graph node(s): {gate_edge}")
            continue
        if key_node not in node_ids:
            issues.append(f"{lock_id}: keyNode {key_node!r} is missing from graphDebug.nodes")
            continue
        if edge_without_direction(a, b) not in edge_keys:
            issues.append(f"{lock_id}: gateEdge {gate_edge} does not exist in graphDebug.edges")
            continue

        a_idx = main_index(a)
        b_idx = main_index(b)
        earlier, later = (a, b)
        if a_idx is not None and b_idx is not None and b_idx < a_idx:
            earlier, later = b, a

        is_bridge, entrance_side = is_bridge_edge(graph, earlier, later, entrance_node="main_00")
        key_reachable = key_node in entrance_side
        gate_side_reachable = later in entrance_side
        exit_before = final_main in entrance_side if final_main else False
        exit_after = final_main in full_reachable if final_main else False
        detail = {
            "lockId": lock_id,
            "isBridge": is_bridge,
            "keyReachableBeforeUnlock": key_reachable,
            "gateSideReachableBeforeUnlock": gate_side_reachable,
            "exitReachableBeforeUnlock": exit_before,
            "exitReachableAfterUnlock": exit_after,
        }
        details.append(detail)
        if not is_bridge:
            issues.append(f"{lock_id}: locked edge is not a bridge/cut edge")
        if gate_side_reachable:
            issues.append(f"{lock_id}: gate-side endpoint is reachable before unlock")
        if exit_before:
            issues.append(f"{lock_id}: final main node is reachable before unlock")
        if not key_reachable:
            issues.append(f"{lock_id}: key/switch node is not reachable before unlock")
        if not exit_after:
            issues.append(f"{lock_id}: final main node is not reachable after unlock")

    result = {"status": "PASS" if not issues else "FAIL", "lockCount": len(locks), "locks": details}
    if issues:
        result["issues"] = issues
    return result


def validate_semantic_layout(layout: SemanticLayout) -> dict[str, Any]:
    issues: list[str] = []
    if layout.width <= 0 or layout.height <= 0:
        issues.append("width and height must be positive")
    if not layout.floor_mask:
        issues.append("floorMask must not be empty")

    for point in sorted(layout.floor_mask):
        if not _in_bounds(layout, point):
            issues.append(f"floorMask point out of bounds: {point}")

    if layout.entrance not in layout.floor_mask:
        issues.append(f"entrance is not inside floorMask: {layout.entrance}")
    if layout.exit not in layout.floor_mask:
        issues.append(f"exit is not inside floorMask: {layout.exit}")
    if not _in_bounds(layout, layout.entrance):
        issues.append(f"entrance out of bounds: {layout.entrance}")
    if not _in_bounds(layout, layout.exit):
        issues.append(f"exit out of bounds: {layout.exit}")

    for marker_name, points in sorted(layout.special_markers.items()):
        for point in points:
            if not _in_bounds(layout, point):
                issues.append(f"specialMarkers.{marker_name} point out of bounds: {point}")

    reachable: set[tuple[int, int]] = set()
    if layout.entrance in layout.floor_mask and layout.exit in layout.floor_mask:
        reachable = _reachable_floor(layout)
        if layout.exit not in reachable:
            issues.append(f"exit is not reachable from entrance: {layout.entrance} -> {layout.exit}")
    route_lock_validation = validate_route_locks(layout)
    if route_lock_validation["status"] != "PASS":
        issues.extend(route_lock_validation.get("issues", []))

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "mapId": layout.map_id,
        "width": layout.width,
        "height": layout.height,
        "floorCells": len(layout.floor_mask),
        "reachableFloorCells": len(reachable),
        "routeLockValidation": route_lock_validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate semantic dungeon layout JSON.")
    parser.add_argument("layout_json", type=Path)
    args = parser.parse_args()
    try:
        layout = load_semantic_layout_json(args.layout_json)
        result = validate_semantic_layout(layout)
    except ValueError as exc:
        result = {"status": "FAIL", "issues": [str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
