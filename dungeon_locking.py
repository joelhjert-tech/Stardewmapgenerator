#!/usr/bin/env python3
"""Graph-based route lock selection and proof helpers."""
from __future__ import annotations

from collections import deque
from typing import Any

from dungeon_graph import DungeonEdge, DungeonGraph
from dungeon_layout_planner import PlannedRoom


def main_index(node_id: str) -> int | None:
    """Return numeric suffix for main_NN nodes, else None."""
    if not node_id.startswith("main_"):
        return None
    suffix = node_id.removeprefix("main_")
    if not suffix.isdigit():
        return None
    return int(suffix)


def sorted_main_nodes(graph: DungeonGraph) -> list[str]:
    """Return main nodes sorted by numeric suffix."""
    nodes = [node_id for node_id in graph.nodes if main_index(node_id) is not None]
    return sorted(nodes, key=lambda node_id: (main_index(node_id), node_id))


def edge_without_direction(a: str, b: str) -> tuple[str, str]:
    """Return a stable undirected edge key."""
    return tuple(sorted((a, b)))


def reachable_nodes_without_edge(
    graph: DungeonGraph,
    start: str,
    removed_edge: tuple[str, str],
) -> set[str]:
    """BFS over graph.edges while ignoring removed_edge."""
    removed = edge_without_direction(*removed_edge)
    adjacency: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge_without_direction(edge.a, edge.b) == removed:
            continue
        adjacency.setdefault(edge.a, set()).add(edge.b)
        adjacency.setdefault(edge.b, set()).add(edge.a)

    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        for nxt in sorted(adjacency.get(node, [])):
            if nxt not in seen:
                queue.append(nxt)
    return seen


def reachable_nodes(graph: DungeonGraph, start: str) -> set[str]:
    """BFS over the full graph."""
    return reachable_nodes_without_edge(graph, start, ("__none_a__", "__none_b__"))


def is_bridge_edge(
    graph: DungeonGraph,
    earlier_endpoint: str,
    later_endpoint: str,
    entrance_node: str = "main_00",
) -> tuple[bool, set[str]]:
    """
    Remove earlier_endpoint-later_endpoint.
    Return whether later_endpoint is unreachable from entrance_node,
    plus the entrance-side reachable component.
    """
    reachable = reachable_nodes_without_edge(graph, entrance_node, (earlier_endpoint, later_endpoint))
    return later_endpoint not in reachable, reachable


def nearest_floor_tile(
    target: tuple[int, int],
    floor_mask: set[tuple[int, int]],
) -> tuple[int, int]:
    """Return nearest floor tile to target using deterministic tie-breaks."""
    if not floor_mask:
        raise ValueError("floor_mask is empty; cannot place route-lock marker")
    tx, ty = target
    return min(floor_mask, key=lambda p: ((p[0] - tx) ** 2 + (p[1] - ty) ** 2, p[1], p[0]))


def _ordered_main_edges(main_nodes: list[str]) -> list[tuple[str, str]]:
    return list(zip(main_nodes, main_nodes[1:]))


def _preferred_main_edges(main_nodes: list[str]) -> list[tuple[str, str]]:
    edges = _ordered_main_edges(main_nodes)
    if len(edges) <= 2:
        return edges
    first_preferred = max(1, len(main_nodes) // 3)
    last_preferred = max(first_preferred, len(main_nodes) - 3)
    preferred = edges[first_preferred:last_preferred + 1]
    fallback = [edge for edge in edges if edge not in preferred]
    return preferred + fallback


def _branch_key_candidates(graph: DungeonGraph, entrance_side: set[str]) -> list[str]:
    branches: list[str] = []
    for edge in graph.edges:
        if edge.kind != "branch":
            continue
        if edge.a.startswith("branch_") and edge.a in entrance_side:
            branches.append(edge.a)
        if edge.b.startswith("branch_") and edge.b in entrance_side:
            branches.append(edge.b)
    return sorted(set(branches))


def _main_key_candidates(main_nodes: list[str], entrance_side: set[str], locked_edge: tuple[str, str]) -> list[str]:
    earlier = locked_edge[0]
    earlier_i = main_index(earlier)
    candidates: list[str] = []
    for node_id in main_nodes:
        idx = main_index(node_id)
        if idx is None or earlier_i is None:
            continue
        if idx <= earlier_i and node_id in entrance_side:
            candidates.append(node_id)
    return candidates


def _marker_for_edge(
    rooms: dict[str, PlannedRoom],
    floor_mask: set[tuple[int, int]],
    a: str,
    b: str,
) -> tuple[int, int]:
    room_a = rooms[a]
    room_b = rooms[b]
    midpoint = (round((room_a.x + room_b.x) / 2), round((room_a.y + room_b.y) / 2))
    if midpoint in floor_mask:
        return midpoint
    return nearest_floor_tile(midpoint, floor_mask)


def _marker_for_node(
    rooms: dict[str, PlannedRoom],
    floor_mask: set[tuple[int, int]],
    node_id: str,
) -> tuple[int, int]:
    room = rooms[node_id]
    center = (room.x, room.y)
    if center in floor_mask:
        return center
    return nearest_floor_tile(center, floor_mask)


def select_route_locks(
    graph: DungeonGraph,
    rooms: dict[str, PlannedRoom],
    floor_mask: set[tuple[int, int]],
    lock_count: int,
    style: str,
) -> list[dict[str, Any]]:
    if lock_count == 0:
        return []
    if lock_count > 1:
        raise NotImplementedError("Only --locks 0 and --locks 1 are supported; multi-lock dependency ordering is deferred.")
    if style not in {"switch", "key"}:
        raise ValueError(f"unsupported lock style: {style}")

    main_nodes = sorted_main_nodes(graph)
    if len(main_nodes) < 2:
        raise ValueError("No valid main path found for requested route lock.")
    entrance_node = main_nodes[0]
    final_main_node = main_nodes[-1]
    full_reachable = reachable_nodes(graph, entrance_node)
    if final_main_node not in full_reachable:
        raise ValueError("Final main node is not reachable in full graph; cannot place route lock.")

    for earlier, later in _preferred_main_edges(main_nodes):
        existing_edges = {edge_without_direction(edge.a, edge.b) for edge in graph.edges}
        if edge_without_direction(earlier, later) not in existing_edges:
            continue
        is_bridge, entrance_side = is_bridge_edge(graph, earlier, later, entrance_node=entrance_node)
        if not is_bridge:
            continue
        if final_main_node in entrance_side:
            continue

        branch_candidates = _branch_key_candidates(graph, entrance_side)
        main_candidates = _main_key_candidates(main_nodes, entrance_side, (earlier, later))
        key_candidates = branch_candidates + [node for node in main_candidates if node not in branch_candidates]
        if not key_candidates:
            continue
        key_node = key_candidates[0]
        gate_marker = _marker_for_edge(rooms, floor_mask, earlier, later)
        key_marker = _marker_for_node(rooms, floor_mask, key_node)
        proof = {
            "isBridge": True,
            "entranceSideEndpoint": earlier,
            "gateSideEndpoint": later,
            "entranceSideReachableCount": len(entrance_side),
            "keyNodeReachableBeforeUnlock": key_node in entrance_side,
            "gateSideReachableBeforeUnlock": later in entrance_side,
            "exitReachableBeforeUnlock": final_main_node in entrance_side,
            "exitReachableAfterUnlock": final_main_node in full_reachable,
        }
        return [{
            "lockId": "lock_00",
            "style": style,
            "gateEdge": [earlier, later],
            "keyNode": key_node,
            "gateMarker": [gate_marker[0], gate_marker[1]],
            "keyMarker": [key_marker[0], key_marker[1]],
            "bridgeProof": proof,
            "notes": "Key/switch is reachable before locked edge; gate-side is unreachable until unlock.",
        }]

    raise ValueError("No valid bridge edge found for requested route lock; loops may bypass all candidate main-path edges.")
