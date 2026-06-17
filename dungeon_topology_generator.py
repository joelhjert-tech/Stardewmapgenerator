#!/usr/bin/env python3
"""Build the room graph for a semantic dungeon."""
from __future__ import annotations

import random

from dungeon_graph import DungeonEdge, DungeonGraph, DungeonNode, edge_key, shortest_hops
from dungeon_spec import DungeonSpec


def build_main_path(spec: DungeonSpec) -> DungeonGraph:
    if spec.main_path_rooms < 2:
        raise ValueError("main_path_rooms must be at least 2")
    nodes = {
        f"main_{i:02d}": DungeonNode(node_id=f"main_{i:02d}", kind="main", index=i)
        for i in range(spec.main_path_rooms)
    }
    edges = [
        DungeonEdge(a=f"main_{i:02d}", b=f"main_{i + 1:02d}", kind="main")
        for i in range(spec.main_path_rooms - 1)
    ]
    return DungeonGraph(nodes=nodes, edges=edges, loop_debug=[])


def add_side_branches(graph: DungeonGraph, spec: DungeonSpec, rng: random.Random) -> None:
    main_ids = [f"main_{i:02d}" for i in range(spec.main_path_rooms)]
    attachable = main_ids[1:-1] or main_ids
    for i in range(spec.side_branches):
        branch_id = f"branch_{i:02d}"
        parent = rng.choice(attachable)
        graph.nodes[branch_id] = DungeonNode(node_id=branch_id, kind="branch", index=i)
        graph.edges.append(DungeonEdge(a=parent, b=branch_id, kind="branch"))


def add_loop_edges(
    graph: DungeonGraph,
    spec: DungeonSpec,
    rng: random.Random,
    allow_partial_loops: bool = False,
) -> None:
    candidates: list[tuple[str, str, int]] = []

    node_ids = sorted(graph.nodes)
    existing = {edge_key(e.a, e.b) for e in graph.edges}

    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1:]:
            key = edge_key(a, b)
            if key in existing:
                continue

            hops = shortest_hops(graph, a, b)
            if hops is None:
                continue
            if hops >= spec.min_loop_hops:
                candidates.append((a, b, hops))

    rng.shuffle(candidates)

    added = 0
    for a, b, hops in candidates:
        if added >= spec.loops:
            break

        key = edge_key(a, b)
        existing_now = {edge_key(e.a, e.b) for e in graph.edges}
        if key in existing_now:
            continue

        current_hops = shortest_hops(graph, a, b)
        if current_hops is None or current_hops < spec.min_loop_hops:
            continue

        graph.edges.append(DungeonEdge(a=a, b=b, kind="loop"))
        graph.loop_debug.append({"a": a, "b": b, "hopsBeforeAdded": current_hops})
        added += 1

    if added < spec.loops:
        message = f"Only {added} valid non-trivial loop candidates found for requested {spec.loops}"
        if not allow_partial_loops:
            raise ValueError(message)
        graph.loop_debug.append({"warning": message})


def generate_topology(
    spec: DungeonSpec,
    rng: random.Random,
    allow_partial_loops: bool = False,
) -> DungeonGraph:
    graph = build_main_path(spec)
    add_side_branches(graph, spec, rng)
    add_loop_edges(graph, spec, rng, allow_partial_loops=allow_partial_loops)
    return graph
