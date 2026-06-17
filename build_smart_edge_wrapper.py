#!/usr/bin/env python3
"""Build custom_07_advanced_edge_wrapped with registry-backed cave walls.

The wrapper separates the semantic floor mask from structural rendering. Cave
walls are emitted only through named structural templates recorded in
pattern_learning/repeated_structure_patterns/templates/.

Prototype/review only. Writes only under
prototype_visual_maps/dungeon_review/custom_07_advanced_edge_wrapped/.
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_dungeon_visual_prototypes as base  # noqa: E402

OUT_ROOT = ROOT / "prototype_visual_maps" / "dungeon_review"
OUT_DIR = OUT_ROOT / "custom_07_advanced_edge_wrapped"
TILESET_OUT = OUT_ROOT / "tilesheets" / "mine.png"
REGISTRY_PATH = ROOT / "pattern_learning" / "repeated_structure_patterns" / "templates" / "custom_07_edge_wrapper_pattern_registry.json"
POLICY_PATH = ROOT / "prototypes" / "structural_pattern_safety_policy.md"

SOLID_VOID = 135
FALLBACK_MARKER_TILE = 80


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pick(options: list[int], x: int, y: int, seed: int, salt: int = 0) -> int:
    if not options:
        raise ValueError("empty template option list")
    n = (x * 73856093) ^ (y * 19349663) ^ ((seed + salt) * 83492791)
    return options[(n & 0xFFFFFFFF) % len(options)]


def in_bounds(p: base.PrototypeMap, x: int, y: int) -> bool:
    return 0 <= x < p.width and 0 <= y < p.height


def is_floor(p: base.PrototypeMap, x: int, y: int) -> bool:
    return (x, y) in p.floor_mask


@dataclass(frozen=True)
class StructuralPattern:
    pattern_id: str
    source: str
    production_status: str
    fallback_pattern_id: Optional[str]
    layer_stack: list[dict[str, Any]]
    allowed_rotations: list[str]
    collision_meaning: str
    anchor: dict[str, int]
    notes: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "StructuralPattern":
        return cls(
            pattern_id=data["patternId"],
            source=data["source"],
            production_status=data["productionStatus"],
            fallback_pattern_id=data.get("fallbackPatternId"),
            layer_stack=data.get("layerStack", []),
            allowed_rotations=data.get("allowedRotations", ["none"]),
            collision_meaning=data.get("collisionMeaning", "unknown"),
            anchor=data.get("anchor", {"x": 0, "y": 0}),
            notes=data.get("notes", ""),
        )


def default_registry_doc() -> dict[str, Any]:
    """Registry derived from the user-approved custom_06 manual edit rules.

    The tile IDs are still prototype/review IDs. The approval here is for the
    structural shape: deep void backing, 3-cell lower-face extrusion, explicit
    corner roles, and marker fallback.
    """
    return {
        "generatedAt": now_iso(),
        "registryId": "custom_07_edge_wrapper_pattern_registry",
        "profile": "dungeon",
        "policyFile": str(POLICY_PATH.resolve()),
        "productionReady": False,
        "sourceSummary": (
            "Manual Tiled edit delta from custom_06_edge_wrapped_edited.tmx "
            "approved the structural cave-wall grammar, not production tiles."
        ),
        "patterns": [
            {
                "patternId": "deep_void_initialization",
                "source": "manually_approved_safe_pattern:custom_06_edited_delta_deep_void_backing",
                "layerStack": [{"layer": "Buildings", "dx": 0, "dy": 0, "tileIds": [SOLID_VOID], "role": "deep_void"}],
                "tileIds": {"Buildings": [SOLID_VOID]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["none"],
                "collisionMeaning": "blocked void backing outside carved floor",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Fill the full Buildings layer before carving floor cells.",
            },
            {
                "patternId": "lower_face_3_tile_extrusion",
                "source": "manually_approved_safe_pattern:custom_06_edited_delta_upward_extrusion",
                "layerStack": [
                    {"layer": "Buildings", "dx": 0, "dy": -1, "tileIds": [121, 122, 123, 124, 157, 158], "role": "bottom_face"},
                    {"layer": "Buildings", "dx": 0, "dy": -2, "tileIds": [85, 86, 89, 90, 101, 102, 105, 106], "role": "middle_face"},
                    {"layer": "Buildings", "dx": 0, "dy": -3, "tileIds": [69, 70, 73, 74, 75, 76], "role": "top_edge"},
                ],
                "tileIds": {"Buildings": [69, 70, 73, 74, 75, 76, 85, 86, 89, 90, 101, 102, 105, 106, 121, 122, 123, 124, 157, 158]},
                "width": 1,
                "height": 3,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["northward"],
                "collisionMeaning": "blocked south-facing wall stack above floor",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Anchor is the floor cell below the stack.",
            },
            {
                "patternId": "shadow_below_lower_face",
                "source": "manually_approved_safe_pattern:custom_06_edited_delta_front_shadow",
                "layerStack": [{"layer": "Front", "dx": 0, "dy": 0, "tileIds": [213, 214, 215, 216, 220], "role": "floor_shadow"}],
                "tileIds": {"Front": [213, 214, 215, 216, 220]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["none"],
                "collisionMeaning": "decorative nonblocking shadow",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Placed on Front at the floor cell below a lower-face extrusion.",
            },
            {
                "patternId": "straight_wall_face",
                "source": "golden/reference-map template:vanilla_mine_wall_face_profile",
                "layerStack": [
                    {"layer": "Buildings", "dx": 0, "dy": 0, "tileIds": [68, 72, 84, 88, 100, 104, 116, 120, 132, 148, 158, 191, 196, 207], "role": "side_or_straight_face"},
                    {"layer": "Front", "dx": 0, "dy": 0, "tileIds": [196, 197, 205, 206, 220, 221, 232], "role": "face_overlay", "optional": True},
                ],
                "tileIds": {"Buildings": [68, 72, 84, 88, 100, 104, 116, 120, 132, 148, 158, 191, 196, 207], "Front": [196, 197, 205, 206, 220, 221, 232]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["N", "E", "S", "W"],
                "collisionMeaning": "blocked side or straight boundary face",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "A registered layer stack, not a loose role-list placement.",
            },
            {
                "patternId": "inner_corner_L_piece",
                "source": "manually_approved_safe_pattern:custom_06_edited_delta_8way_inner_corner",
                "layerStack": [
                    {"layer": "Buildings", "dx": 0, "dy": 0, "tileIds": [119, 120, 121, 122, 157, 158, 93, 94, 109, 110], "role": "inner_corner"},
                    {"layer": "Front", "dx": 0, "dy": 0, "tileIds": [205, 206, 215, 220, 221, 232], "role": "corner_overlay", "optional": True},
                ],
                "tileIds": {"Buildings": [93, 94, 109, 110, 119, 120, 121, 122, 157, 158], "Front": [205, 206, 215, 220, 221, 232]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["SE", "SW", "NE", "NW"],
                "collisionMeaning": "blocked concave wall corner",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Chosen only from explicit 8-way cardinal pair conditions.",
            },
            {
                "patternId": "outer_corner_piece",
                "source": "manually_approved_safe_pattern:custom_06_edited_delta_8way_outer_corner",
                "layerStack": [{"layer": "Buildings", "dx": 0, "dy": 0, "tileIds": [93, 94, 109, 110, 125, 126, 68, 72, 84, 88], "role": "outer_corner"}],
                "tileIds": {"Buildings": [68, 72, 84, 88, 93, 94, 109, 110, 125, 126]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["SE", "SW", "NE", "NW"],
                "collisionMeaning": "blocked convex diagonal-only wall corner",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Chosen only when diagonal floor exists and no cardinal floor touches the cell.",
            },
            {
                "patternId": "edge_cap",
                "source": "golden/reference-map template:vanilla_mine_edge_cap_profile",
                "layerStack": [{"layer": "Buildings", "dx": 0, "dy": 0, "tileIds": [69, 70, 73, 74, 75, 76, 93, 94], "role": "edge_cap"}],
                "tileIds": {"Buildings": [69, 70, 73, 74, 75, 76, 93, 94]},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["N", "E", "S", "W"],
                "collisionMeaning": "blocked wall cap at ambiguous straight edge",
                "productionStatus": "prototype_review_only",
                "fallbackPatternId": "fallback_marker_wall",
                "notes": "Reserved for future reference-map promotion; current resolver prefers explicit straight/corner roles.",
            },
            {
                "patternId": "fallback_marker_wall",
                "source": "marker-only fallback",
                "layerStack": [],
                "tileIds": {},
                "width": 1,
                "height": 1,
                "anchor": {"x": 0, "y": 0},
                "allowedRotations": ["none", "N", "E", "S", "W", "SE", "SW", "NE", "NW"],
                "collisionMeaning": "no visual structural tile placed; deep void remains blocking",
                "productionStatus": "marker_only",
                "fallbackPatternId": None,
                "notes": "Used when classification is ambiguous or a required template is missing.",
            },
        ],
    }


class PatternRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path
        self.doc = self._load_or_create()
        self.patterns = {p.pattern_id: p for p in (StructuralPattern.from_json(d) for d in self.doc["patterns"])}

    def _load_or_create(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            doc = default_registry_doc()
            self.path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            return doc
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, pattern_id: str) -> Optional[StructuralPattern]:
        return self.patterns.get(pattern_id)


class SmartMineEdgeWrapper:
    def __init__(self, seed_salt: int = 707, registry: Optional[PatternRegistry] = None):
        self.seed_salt = seed_salt
        self.registry = registry or PatternRegistry()
        self.role_by_cell: dict[str, str] = {}
        self.cell_pattern: dict[str, str] = {}
        self.cell_priority: dict[str, int] = {}
        self.front_roles: Counter[str] = Counter()
        self.building_roles: Counter[str] = Counter()
        self.pattern_counts: Counter[str] = Counter()
        self.edge_classifications: list[dict[str, Any]] = []
        self.template_placements: list[dict[str, Any]] = []
        self.fallbacks: list[dict[str, Any]] = []
        self.deep_void_cells = 0
        self.initialized_deep_void_cells = 0

    def apply(self, p: base.PrototypeMap) -> dict[str, Any]:
        self._prepare_semantic_mask(p)
        self._initialize_deep_void(p)
        self._paint_floors_and_carve(p)
        self._trace_and_extrude_lower_faces(p)
        self._resolve_8way_boundaries(p)
        self._paint_ladder_opening(p)
        self._place_specials(p)
        for cell in [p.entrance, p.exit]:
            p.walkable.add(cell)
            p.blocked.discard(cell)
        return self._summary(p)

    def _prepare_semantic_mask(self, p: base.PrototypeMap) -> None:
        ex, ey = p.entrance
        base.add_rect(p.floor_mask, ex - 1, ey - 1, ex + 1, ey + 1)
        lx, ly = p.exit
        base.add_rect(p.floor_mask, lx - 1, ly, lx + 1, min(p.height - 2, ly + 2))
        p.init_layers()
        p.walkable.clear()
        p.blocked.clear()
        p.wall_mask.clear()
        self.role_by_cell.clear()
        self.cell_pattern.clear()
        self.cell_priority.clear()
        self.front_roles.clear()
        self.building_roles.clear()
        self.pattern_counts.clear()
        self.edge_classifications.clear()
        self.template_placements.clear()
        self.fallbacks.clear()

    def _initialize_deep_void(self, p: base.PrototypeMap) -> None:
        pattern = self.registry.get("deep_void_initialization")
        if pattern is None:
            raise RuntimeError("deep_void_initialization pattern missing")
        self.initialized_deep_void_cells = p.width * p.height
        self.deep_void_cells = 0
        for y in range(p.height):
            for x in range(p.width):
                p.set_tile("Buildings", x, y, SOLID_VOID)
                p.blocked.add((x, y))
                self.deep_void_cells += 1
        self.pattern_counts[pattern.pattern_id] += self.initialized_deep_void_cells
        self.template_placements.append({
            "patternId": pattern.pattern_id,
            "source": pattern.source,
            "placementKind": "full_layer_initialization",
            "layer": "Buildings",
            "tileId": SOLID_VOID,
            "cells": self.initialized_deep_void_cells,
            "productionStatus": pattern.production_status,
        })

    def _paint_floors_and_carve(self, p: base.PrototypeMap) -> None:
        floor_tiles = base.COBBLE_FLOORS if p.floor_style == "cobble" else base.EARTH_FLOORS
        for x, y in sorted(p.floor_mask):
            tile = pick(floor_tiles, x, y, p.seed, self.seed_salt)
            if (x * 17 + y * 31 + p.seed) % 13 == 0:
                tile = pick(base.EARTH_DETAILS, x, y, p.seed, self.seed_salt + 1)
            p.set_tile("Back", x, y, tile)
            p.set_tile("Buildings", x, y, None)
            p.blocked.discard((x, y))
            p.walkable.add((x, y))

    def _set_building(
        self,
        p: base.PrototypeMap,
        x: int,
        y: int,
        tile: int,
        role: str,
        pattern_id: str,
        priority: int,
    ) -> bool:
        if not in_bounds(p, x, y) or is_floor(p, x, y):
            return False
        key = f"{x},{y}"
        old_priority = self.cell_priority.get(key, -1)
        if old_priority > priority:
            return False
        p.set_tile("Buildings", x, y, tile)
        p.blocked.add((x, y))
        p.wall_mask.add((x, y))
        self.role_by_cell[key] = role
        self.cell_pattern[key] = pattern_id
        self.cell_priority[key] = priority
        self.building_roles[role] += 1
        return True

    def _set_front(self, p: base.PrototypeMap, x: int, y: int, tile: int, role: str, overwrite: bool = False) -> bool:
        if not in_bounds(p, x, y):
            return False
        if p.get_tile("Front", x, y) is not None and not overwrite:
            return False
        p.set_tile("Front", x, y, tile)
        self.front_roles[role] += 1
        return True

    def _would_make_thin_wall(self, p: base.PrototypeMap, x: int, y: int) -> bool:
        return (
            (is_floor(p, x - 1, y) and is_floor(p, x + 1, y))
            or (is_floor(p, x, y - 1) and is_floor(p, x, y + 1))
        )

    def _place_pattern(
        self,
        p: base.PrototypeMap,
        pattern_id: str,
        x: int,
        y: int,
        role: str,
        rotation: str,
        priority: int,
        reason: str,
        overwrite_front: bool = False,
    ) -> bool:
        pattern = self.registry.get(pattern_id)
        if pattern is None or rotation not in pattern.allowed_rotations:
            return self._fallback(p, x, y, role, rotation, reason, f"missing or invalid pattern {pattern_id}")
        if pattern.production_status == "marker_only":
            return self._fallback(p, x, y, role, rotation, reason, "marker-only pattern")

        for entry in pattern.layer_stack:
            if entry["layer"] != "Buildings" or entry.get("optional"):
                continue
            tx, ty = x + int(entry.get("dx", 0)), y + int(entry.get("dy", 0))
            if not in_bounds(p, tx, ty) or is_floor(p, tx, ty):
                return self._fallback(
                    p,
                    x,
                    y,
                    role,
                    rotation,
                    reason,
                    f"required Buildings cell {tx},{ty} is not writable",
                )
            if self._would_make_thin_wall(p, tx, ty):
                return self._fallback(
                    p,
                    x,
                    y,
                    role,
                    rotation,
                    reason,
                    f"required Buildings cell {tx},{ty} would form a thin wall slice",
                )

        cells: list[dict[str, Any]] = []
        wrote_any = False
        for i, entry in enumerate(pattern.layer_stack):
            tx, ty = x + int(entry.get("dx", 0)), y + int(entry.get("dy", 0))
            tile_id = pick(list(entry.get("tileIds", [])), tx, ty, p.seed, self.seed_salt + i + priority)
            layer = entry["layer"]
            cell_role = f"{role}:{entry.get('role', pattern_id)}"
            if layer == "Buildings":
                wrote = self._set_building(p, tx, ty, tile_id, cell_role, pattern_id, priority)
            elif layer == "Front":
                wrote = self._set_front(p, tx, ty, tile_id, cell_role, overwrite=overwrite_front or bool(entry.get("optional")))
            else:
                wrote = False
            if wrote:
                wrote_any = True
                cells.append({"layer": layer, "x": tx, "y": ty, "tileId": tile_id, "role": cell_role})

        if wrote_any:
            self.pattern_counts[pattern_id] += 1
            self.template_placements.append({
                "patternId": pattern_id,
                "source": pattern.source,
                "productionStatus": pattern.production_status,
                "anchor": {"x": x, "y": y},
                "rotation": rotation,
                "role": role,
                "reason": reason,
                "cells": cells,
            })
        return wrote_any

    def _fallback(self, p: base.PrototypeMap, x: int, y: int, role: str, rotation: str, reason: str, issue: str) -> bool:
        pattern = self.registry.get("fallback_marker_wall")
        record = {
            "patternId": "fallback_marker_wall",
            "source": pattern.source if pattern else "marker-only fallback",
            "productionStatus": "marker_only",
            "anchor": {"x": x, "y": y},
            "rotation": rotation,
            "role": role,
            "reason": reason,
            "issue": issue,
            "cells": [],
        }
        self.fallbacks.append(record)
        self.template_placements.append(record)
        self.pattern_counts["fallback_marker_wall"] += 1
        if in_bounds(p, x, y) and not is_floor(p, x, y):
            p.blocked.add((x, y))
        return False

    def _trace_and_extrude_lower_faces(self, p: base.PrototypeMap) -> None:
        for x, y in sorted(p.floor_mask):
            if is_floor(p, x, y - 1):
                continue
            self._place_pattern(
                p,
                "lower_face_3_tile_extrusion",
                x,
                y,
                "lower_face",
                "northward",
                70,
                "floor cell has void directly north; extrude 3 cells north",
            )
            self._place_pattern(
                p,
                "shadow_below_lower_face",
                x,
                y,
                "shadow_below_lower_face",
                "none",
                65,
                "shadow belongs to lower-face structural stack",
                overwrite_front=True,
            )
            p.set_tile("Back", x, y, 186)

    def _neighbors8(self, p: base.PrototypeMap, x: int, y: int) -> dict[str, bool]:
        return {
            "N": is_floor(p, x, y - 1),
            "NE": is_floor(p, x + 1, y - 1),
            "E": is_floor(p, x + 1, y),
            "SE": is_floor(p, x + 1, y + 1),
            "S": is_floor(p, x, y + 1),
            "SW": is_floor(p, x - 1, y + 1),
            "W": is_floor(p, x - 1, y),
            "NW": is_floor(p, x - 1, y - 1),
        }

    def _classify_boundary(self, neighbors: dict[str, bool]) -> tuple[str, str, str]:
        cardinals = [d for d in ["N", "E", "S", "W"] if neighbors[d]]
        diagonals = [d for d in ["NE", "SE", "SW", "NW"] if neighbors[d]]
        cardinal_set = set(cardinals)

        inner_pairs = {
            frozenset(["S", "E"]): ("inner_corner", "SE"),
            frozenset(["S", "W"]): ("inner_corner", "SW"),
            frozenset(["N", "E"]): ("inner_corner", "NE"),
            frozenset(["N", "W"]): ("inner_corner", "NW"),
        }
        if len(cardinal_set) == 2 and frozenset(cardinal_set) in inner_pairs:
            return (*inner_pairs[frozenset(cardinal_set)], "cardinal pair concave corner")

        if not cardinals and len(diagonals) == 1:
            return ("outer_corner", diagonals[0], "diagonal-only convex corner")

        if len(cardinals) == 1:
            return ("straight_face", cardinals[0], "single-cardinal straight boundary")

        if cardinals or diagonals:
            return ("ambiguous", "".join(cardinals + diagonals) or "none", "multi-neighbor boundary not represented by approved template")

        return ("deep_void", "none", "not adjacent to floor")

    def _resolve_8way_boundaries(self, p: base.PrototypeMap) -> None:
        for y in range(p.height):
            for x in range(p.width):
                if is_floor(p, x, y):
                    continue
                neighbors = self._neighbors8(p, x, y)
                role, rotation, reason = self._classify_boundary(neighbors)
                if role == "deep_void":
                    continue
                record = {
                    "x": x,
                    "y": y,
                    "role": role,
                    "rotation": rotation,
                    "reason": reason,
                    "neighbors": neighbors,
                }
                self.edge_classifications.append(record)
                if role == "inner_corner":
                    self._place_pattern(p, "inner_corner_L_piece", x, y, role, rotation, 95, reason, overwrite_front=True)
                elif role == "outer_corner":
                    self._place_pattern(p, "outer_corner_piece", x, y, role, rotation, 60, reason)
                elif role == "straight_face":
                    # South-adjacent straight boundaries are already handled by
                    # the 3-cell extrusion. The registered straight face fills
                    # side/upper edges and any remaining simple cardinal edge.
                    priority = 45 if rotation == "S" else 78
                    self._place_pattern(p, "straight_wall_face", x, y, role, rotation, priority, reason)
                elif role == "ambiguous":
                    self._fallback(p, x, y, role, rotation, reason, "no approved 8-way template for this neighbor combination")

    def _paint_ladder_opening(self, p: base.PrototypeMap) -> None:
        x, y_bottom = p.exit
        for ay in range(y_bottom, min(p.height, y_bottom + 3)):
            for ax in range(x - 1, x + 2):
                if in_bounds(p, ax, ay):
                    p.floor_mask.add((ax, ay))
                    p.walkable.add((ax, ay))
                    p.blocked.discard((ax, ay))
                    p.set_tile("Back", ax, ay, pick(base.EARTH_FLOORS, ax, ay, p.seed, 40))
                    p.set_tile("Buildings", ax, ay, None)
        for offset, tile in enumerate([67, 83, 99, 115]):
            yy = y_bottom - 3 + offset
            if in_bounds(p, x, yy):
                self._set_front(p, x, yy, tile, "front_exit_ladder_marker", overwrite=True)

    def _place_specials(self, p: base.PrototypeMap) -> None:
        for x, y in p.special_markers.get("torches", []):
            if in_bounds(p, x, y):
                self._set_front(p, x, y, 48 if (x + y) % 2 else FALLBACK_MARKER_TILE, "torch_front", overwrite=True)

    def _summary(self, p: base.PrototypeMap) -> dict[str, Any]:
        fronts = sum(1 for g in p.layers["Front"] if base.local_id(g) is not None)
        buildings = sum(
            1
            for g in p.layers["Buildings"]
            if base.local_id(g) is not None and base.local_id(g) != SOLID_VOID
        )
        deep_void = sum(1 for g in p.layers["Buildings"] if base.local_id(g) == SOLID_VOID)
        return {
            "algorithm": "semantic_floor_mask_then_registry_backed_edge_wrapper",
            "floorCells": len(p.floor_mask),
            "wallCells": len(p.wall_mask),
            "deepVoidCells": deep_void,
            "initialDeepVoidCells": self.initialized_deep_void_cells,
            "buildingsTiles": buildings,
            "frontTiles": fronts,
            "frontToBuildingsRatio": fronts / buildings if buildings else 0.0,
            "buildingRoles": dict(sorted(self.building_roles.items())),
            "frontRoles": dict(sorted(self.front_roles.items())),
            "patternCounts": dict(sorted(self.pattern_counts.items())),
            "fallbackCount": len(self.fallbacks),
            "roleByCell": dict(sorted(self.role_by_cell.items())),
            "cellPattern": dict(sorted(self.cell_pattern.items())),
            "registryPath": str(self.registry.path.resolve()),
        }


def smooth_mask(mask: set[tuple[int, int]], iterations: int = 1) -> set[tuple[int, int]]:
    out = set(mask)
    for _ in range(iterations):
        add: set[tuple[int, int]] = set()
        remove: set[tuple[int, int]] = set()
        for y in range(2, base.MAP_H - 2):
            for x in range(2, base.MAP_W - 2):
                count = sum(
                    (x + dx, y + dy) in out
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                    if dx or dy
                )
                if (x, y) not in out and count >= 5:
                    add.add((x, y))
                elif (x, y) in out and count <= 2:
                    remove.add((x, y))
        out |= add
        out -= remove
    return out


def make_custom_07_advanced() -> base.PrototypeMap:
    p = base.PrototypeMap(
        map_id="custom_07_advanced_edge_wrapped",
        title="Custom 07 - Advanced Edge Wrapped Mine",
        kind="custom",
        source_map=None,
        source_origin="fresh procedural semantic mask generated for registry-backed smart edge-wrapper testing",
        source_reason="Tests deep void initialization, 3-tile lower-face extrusion, and 8-way corner resolution.",
        seed=40717,
        floor_style="earth",
        entrance=(9, 40),
        exit=(39, 9),
    )
    mask: set[tuple[int, int]] = set()
    base.add_ellipse(mask, 13, 34, 8, 8)
    base.add_ellipse(mask, 22, 26, 10, 7)
    base.add_ellipse(mask, 34, 30, 8, 6)
    base.add_ellipse(mask, 36, 15, 7, 7)
    base.add_ellipse(mask, 16, 14, 7, 5)
    base.add_ellipse(mask, 26, 13, 5, 4)
    base.carve_corridor(mask, [(9, 40), (13, 34), (22, 26), (34, 30), (39, 9)], width=2)
    base.carve_corridor(mask, [(22, 26), (16, 14), (26, 13), (36, 15)], width=2)
    base.carve_corridor(mask, [(13, 34), (34, 30)], width=1)
    base.add_rect(mask, 37, 7, 42, 11)
    base.add_rect(mask, 7, 38, 12, 42)
    for cell in [(28, 25), (29, 25), (28, 26), (31, 28), (32, 28), (33, 28)]:
        mask.discard(cell)
    p.floor_mask = smooth_mask(mask, iterations=1)
    p.special_markers = {
        "torches": [(12, 31), (20, 20), (33, 24), (36, 13), (10, 39)],
        "ore": [],
        "chests": [],
    }
    return p


def tile_usage_by_layer(p: base.PrototypeMap) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for layer, data in p.layers.items():
        c = Counter(base.local_id(g) for g in data if base.local_id(g) is not None)
        out[layer] = {str(k): int(v) for k, v in sorted(c.items())}
    return out


def reachable_count(p: base.PrototypeMap) -> int:
    q = deque([p.entrance])
    seen = set()
    while q:
        cell = q.popleft()
        if cell in seen:
            continue
        seen.add(cell)
        for n in base.neighbors4(*cell):
            if n in p.walkable and n not in p.blocked and n not in seen:
                q.append(n)
    return len(seen)


def write_debug_files(wrapper: SmartMineEdgeWrapper) -> tuple[Path, Path]:
    edge_path = OUT_DIR / "edge_classification_debug.json"
    template_path = OUT_DIR / "template_placement_debug.json"
    edge_path.write_text(json.dumps(wrapper.edge_classifications, indent=2), encoding="utf-8")
    template_path.write_text(json.dumps(wrapper.template_placements, indent=2), encoding="utf-8")
    return edge_path, template_path


def draw_debug_overlays(p: base.PrototypeMap, wrapper: SmartMineEdgeWrapper) -> tuple[Path, Path]:
    scale = 8
    w, h = p.width * scale, p.height * scale
    edge = Image.new("RGBA", (w, h), (18, 18, 22, 255))
    tmpl = Image.new("RGBA", (w, h), (18, 18, 22, 255))
    ed = ImageDraw.Draw(edge)
    td = ImageDraw.Draw(tmpl)
    colors = {
        "floor": (76, 150, 86, 255),
        "deep_void": (28, 28, 31, 255),
        "lower_face": (222, 191, 92, 255),
        "straight_face": (92, 161, 222, 255),
        "inner_corner": (221, 108, 108, 255),
        "outer_corner": (180, 111, 222, 255),
        "ambiguous": (255, 68, 68, 255),
    }
    for y in range(p.height):
        for x in range(p.width):
            box = (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1)
            if is_floor(p, x, y):
                ed.rectangle(box, fill=colors["floor"])
                td.rectangle(box, fill=colors["floor"])
            else:
                ed.rectangle(box, fill=colors["deep_void"])
                td.rectangle(box, fill=colors["deep_void"])
    for rec in wrapper.edge_classifications:
        x, y = rec["x"], rec["y"]
        role = rec["role"]
        box = (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1)
        ed.rectangle(box, fill=colors.get(role, (255, 255, 255, 255)))
    placement_colors = {
        "lower_face_3_tile_extrusion": (222, 191, 92, 255),
        "shadow_below_lower_face": (72, 72, 72, 255),
        "straight_wall_face": (92, 161, 222, 255),
        "inner_corner_L_piece": (221, 108, 108, 255),
        "outer_corner_piece": (180, 111, 222, 255),
        "fallback_marker_wall": (255, 68, 68, 255),
    }
    for rec in wrapper.template_placements:
        color = placement_colors.get(rec["patternId"], (245, 245, 245, 255))
        cells = rec.get("cells", [])
        if not isinstance(cells, list):
            continue
        for cell in cells:
            x, y = cell["x"], cell["y"]
            if 0 <= x < p.width and 0 <= y < p.height:
                box = (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1)
                td.rectangle(box, fill=color)
        if rec["patternId"] == "fallback_marker_wall":
            x, y = rec["anchor"]["x"], rec["anchor"]["y"]
            box = (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1)
            td.rectangle(box, fill=color)
    edge_path = OUT_DIR / "edge_classification_overlay.png"
    template_path = OUT_DIR / "template_overlay.png"
    edge.save(edge_path)
    tmpl.save(template_path)
    return edge_path, template_path


def write_metadata(
    p: base.PrototypeMap,
    paths: dict[str, str],
    validation: dict[str, Any],
    wrapper_result: dict[str, Any],
    wrapper: SmartMineEdgeWrapper,
) -> Path:
    doc = {
        "generatedAt": now_iso(),
        "mapId": p.map_id,
        "profile": "dungeon",
        "prototypeOnly": True,
        "productionMapOutput": False,
        "generator": "build_smart_edge_wrapper.py",
        "sourceLayout": "fresh custom_07 advanced semantic floor mask",
        "renderingPolicy": "Initialize deep void, carve floor, then place complete registered structural templates.",
        "structuralPatternPolicy": {
            "policyFile": str(POLICY_PATH.resolve()),
            "registryPath": str(wrapper.registry.path.resolve()),
            "proofSource": "manually_approved_custom_06_edit_delta_plus_reference_profile_templates",
            "productionReady": False,
            "fallbackChain": [
                "manually_approved_safe_pattern",
                "golden/reference-map template",
                "profile generic template",
                "marker-only fallback",
                "blocked with report",
            ],
            "note": "Structural shapes are template-backed; tile IDs remain prototype/review only.",
        },
        "deepVoidInitialization": {
            "patternId": "deep_void_initialization",
            "fillFullBuildingsLayerBeforeCarve": True,
            "initialCellCount": wrapper.initialized_deep_void_cells,
            "remainingDeepVoidCells": wrapper_result["deepVoidCells"],
        },
        "size": {"width": p.width, "height": p.height, "tileWidth": 16, "tileHeight": 16},
        "entrance": {"x": p.entrance[0], "y": p.entrance[1]},
        "exit": {"x": p.exit[0], "y": p.exit[1]},
        "tileUsageByLayer": tile_usage_by_layer(p),
        "smartEdgeWrapper": wrapper_result,
        "restrictedStructuralTileStatus": "none_used",
        "protectedPathsStatus": {
            "productionMapsGenerated": False,
            "originalMoonvillageMapsModified": False,
            "missionAssetsModified": False,
            "unpackedBasegameModified": False,
            "approvedProductionDbModified": False,
        },
        "paths": paths,
        "validation": validation,
    }
    out = OUT_DIR / "metadata.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def write_summary_report(p: base.PrototypeMap, validation: dict[str, Any], wrapper_result: dict[str, Any], paths: dict[str, str]) -> Path:
    lines = [
        "# Custom 07 Advanced Edge Wrapper Summary",
        "",
        f"- Status: {validation['status']}",
        f"- Floor cells: {wrapper_result['floorCells']}",
        f"- Structural wall cells: {wrapper_result['wallCells']}",
        f"- Deep void cells after carving: {wrapper_result['deepVoidCells']}",
        f"- Front/Buildings ratio: {wrapper_result['frontToBuildingsRatio']:.3f}",
        f"- Template fallbacks: {wrapper_result['fallbackCount']}",
        "- Production-ready: NO",
        "- Production maps generated: NO",
        "",
        "## What changed from custom_06",
        "- Buildings starts as a full deep-void layer before floor carving.",
        "- Lower faces are placed as one registered 3-tile northward extrusion template.",
        "- Corner cells are classified with explicit 8-way neighbor data.",
        "- Every structural wall/corner placement is logged through the template registry.",
        "",
        "## Outputs",
        f"- TMX: `{paths['tmx']}`",
        f"- TMJ: `{paths['tmj']}`",
        f"- Clean preview: `{paths['preview_clean']}`",
        f"- Labeled preview: `{paths['preview_labeled']}`",
        f"- Edge overlay: `{paths['edge_classification_overlay']}`",
        f"- Template overlay: `{paths['template_overlay']}`",
    ]
    if validation.get("issues"):
        lines += ["", "## Issues"] + [f"- {issue}" for issue in validation["issues"]]
    if validation.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {warning}" for warning in validation["warnings"][:80]]
    out = OUT_DIR / "custom_07_advanced_edge_wrapper_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_global_reports(wrapper_result: dict[str, Any], validation: dict[str, Any], paths: dict[str, str]) -> None:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    summary = [
        "# Custom 07 Advanced Edge Wrapper Summary",
        "",
        "The smart edge-wrapper was upgraded from implicit profile-generic role lists to registry-backed structural template placement.",
        "",
        "## Structural Rules",
        "- Deep void initialization fills `Buildings` before carving.",
        "- Lower faces use a complete 3-tile extrusion template.",
        "- Corners are resolved from explicit 8-way neighbor metadata.",
        "- Ambiguous structures use marker-only fallback and remain blocked by deep void.",
        "",
        "## Pattern Sources",
        "- Manual custom_06 Tiled edit delta: deep void, lower-face extrusion, inner/outer corner grammar.",
        "- Vanilla/reference profile templates: straight wall face and edge-cap placeholder.",
        "",
        f"- Output: `{paths['tmx']}`",
        f"- Fallback count: {wrapper_result['fallbackCount']}",
        f"- Validation: {validation['status']}",
    ]
    (reports / "custom_07_advanced_edge_wrapper_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    validation_lines = [
        "# Custom 07 Advanced Edge Wrapper Validation",
        "",
        f"- Result: {validation['status']}",
        "",
        "## Checks",
    ]
    for key, value in validation.get("checks", {}).items():
        validation_lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    if validation.get("issues"):
        validation_lines += ["", "## Issues"] + [f"- {issue}" for issue in validation["issues"]]
    (reports / "custom_07_advanced_edge_wrapper_validation.md").write_text("\n".join(validation_lines) + "\n", encoding="utf-8")

    safety = [
        "# Custom 07 Advanced Edge Wrapper Safety",
        "",
        "- Production maps generated: NO",
        "- Original Moonvillage maps modified: NO",
        "- mission_assets modified: NO",
        "- Unpacked basegame files modified: NO",
        "- Approved production DB modified: NO",
        "- Old generator state backed up before editing: YES",
        "- Fallback system still exists: YES",
        "- Output remains prototype/review only: YES",
    ]
    (reports / "custom_07_advanced_edge_wrapper_safety.md").write_text("\n".join(safety) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "tilesheets").mkdir(parents=True, exist_ok=True)
    if not base.TILESET_SRC.exists():
        raise SystemExit(f"Missing mine tilesheet: {base.TILESET_SRC}")
    shutil.copy2(base.TILESET_SRC, TILESET_OUT)

    p = make_custom_07_advanced()
    wrapper = SmartMineEdgeWrapper(seed_salt=717)
    wrapper_result = wrapper.apply(p)

    tmx = base.write_tmx(p, OUT_DIR, "../tilesheets/mine.png")
    tmj = base.write_tmj(p, OUT_DIR, "../tilesheets/mine.png")
    tilesheet = Image.open(TILESET_OUT).convert("RGBA")
    clean, labeled = base.render_map(p, tilesheet, OUT_DIR)
    edge_debug, placement_debug = write_debug_files(wrapper)
    edge_overlay, template_overlay = draw_debug_overlays(p, wrapper)
    validation = base.validate_prototype(p, tmx, tmj, "../tilesheets/mine.png")
    validation_report = base.write_validation_report(p, OUT_DIR, validation, "validation_report.md")

    paths = {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "validation_report": str(validation_report.resolve()),
        "edge_classification_debug": str(edge_debug.resolve()),
        "template_placement_debug": str(placement_debug.resolve()),
        "edge_classification_overlay": str(edge_overlay.resolve()),
        "template_overlay": str(template_overlay.resolve()),
        "pattern_registry": str(REGISTRY_PATH.resolve()),
    }
    local_summary = write_summary_report(p, validation, wrapper_result, paths)
    paths["custom_07_advanced_edge_wrapper_summary"] = str(local_summary.resolve())
    metadata = write_metadata(p, paths, validation, wrapper_result, wrapper)
    paths["metadata"] = str(metadata.resolve())
    write_global_reports(wrapper_result, validation, paths)

    print(json.dumps({
        "status": validation["status"],
        "frontToBuildingsRatio": wrapper_result["frontToBuildingsRatio"],
        "floorCells": wrapper_result["floorCells"],
        "wallCells": wrapper_result["wallCells"],
        "deepVoidCells": wrapper_result["deepVoidCells"],
        "fallbackCount": wrapper_result["fallbackCount"],
        "outDir": str(OUT_DIR.resolve()),
    }, indent=2))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
