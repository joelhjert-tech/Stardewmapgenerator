#!/usr/bin/env python3
"""Graph primitives for semantic dungeon generation."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class DungeonNode:
    node_id: str
    kind: str
    index: int


@dataclass(frozen=True)
class DungeonEdge:
    a: str
    b: str
    kind: str


@dataclass
class DungeonGraph:
    nodes: dict[str, DungeonNode]
    edges: list[DungeonEdge]
    loop_debug: list[dict]


def edge_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def build_adjacency(edges: list[DungeonEdge]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.a, set()).add(edge.b)
        adjacency.setdefault(edge.b, set()).add(edge.a)
    return adjacency


def shortest_hops(graph: DungeonGraph, start: str, goal: str) -> int | None:
    if start == goal:
        return 0

    adjacency = build_adjacency(graph.edges)
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}

    while queue:
        node, dist = queue.popleft()
        for nxt in sorted(adjacency.get(node, [])):
            if nxt == goal:
                return dist + 1
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))

    return None
