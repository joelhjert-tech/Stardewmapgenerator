#!/usr/bin/env python3
"""Configuration for graph-first semantic dungeon generation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DungeonSpec:
    seed: int = 123
    width: int = 96
    height: int = 96

    main_path_rooms: int = 12
    side_branches: int = 4
    loops: int = 2

    min_loop_hops: int = 3

    min_room_radius: int = 4
    max_room_radius: int = 9
    corridor_width: int = 2
    margin: int = 8

    torch_count: int = 8
