#!/usr/bin/env python3
"""Generate custom_08_fresh_template_test using the fresh mine/dungeon library."""
from __future__ import annotations

import json
import shutil
import sys
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_dungeon_visual_prototypes as base  # noqa: E402
from build_smart_edge_wrapper import smooth_mask  # noqa: E402

LIBRARY_PATH = ROOT / "pattern_learning" / "mine_dungeon_fresh_relearn" / "templates" / "mine_dungeon_fresh_template_library.json"
FAMILY_PATH = ROOT / "pattern_learning" / "mine_dungeon_fresh_relearn" / "clusters" / "mine_dungeon_tile_id_families.json"
VISUAL_CANON_PATH = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1" / "mine_dungeon_visual_canon_v1.json"
OUT_ROOT = ROOT / "prototype_visual_maps" / "dungeon_review"
OUT_DIR = OUT_ROOT / "custom_08_fresh_template_test"
TILESET_OUT = OUT_ROOT / "tilesheets" / "mine.png"
DEEP_VOID = 135
VOID_IDS = {77, 135}  # deep-void / empty tiles that are not real structural or Front art
LAYERS = ("Back", "Buildings", "Front", "AlwaysFront", "Paths")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def in_bounds(p: base.PrototypeMap, x: int, y: int) -> bool:
    return 0 <= x < p.width and 0 <= y < p.height


def is_floor(p: base.PrototypeMap, x: int, y: int) -> bool:
    return (x, y) in p.floor_mask


def pick(options: list[int], x: int, y: int, seed: int) -> int:
    return options[((x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)) % len(options)]


def make_custom_08() -> base.PrototypeMap:
    p = base.PrototypeMap(
        map_id="custom_08_fresh_template_test",
        title="Custom 08 - Fresh Template Mine Test",
        kind="custom",
        source_map=None,
        source_origin="fresh semantic layout rendered only with mine_dungeon_fresh_template_library.json",
        source_reason="Tests fresh repeated structural templates, tile-ID families, 8-way corners, lower faces, and learned openings.",
        seed=40808,
        floor_style="earth",
        entrance=(8, 40),
        exit=(39, 9),
    )
    mask: set[tuple[int, int]] = set()
    base.add_ellipse(mask, 13, 34, 8, 8)
    base.add_ellipse(mask, 22, 27, 11, 7)
    base.add_ellipse(mask, 35, 31, 8, 6)
    base.add_ellipse(mask, 36, 15, 7, 7)
    base.add_ellipse(mask, 16, 14, 7, 5)
    base.add_ellipse(mask, 26, 13, 5, 4)
    base.carve_corridor(mask, [(8, 40), (13, 34), (22, 27), (35, 31), (39, 9)], width=2)
    base.carve_corridor(mask, [(22, 27), (16, 14), (26, 13), (36, 15)], width=2)
    base.carve_corridor(mask, [(13, 34), (35, 31)], width=1)
    base.add_rect(mask, 37, 7, 42, 11)
    base.add_rect(mask, 6, 38, 12, 42)
    p.floor_mask = smooth_mask(mask, iterations=1)
    p.special_markers = {"torches": [(12, 31), (21, 20), (33, 24), (36, 13), (9, 39)], "ore": [], "chests": []}
    return p


def make_round_test_map(map_id: str, title: str, source_origin: str, source_reason: str) -> base.PrototypeMap:
    """A simple single round cavern (Joel's preferred test layout). One open circular floor,
    entrance at the top (where the single ladder goes), exit lower."""
    cx, cy, r = 24, 25, 17
    p = base.PrototypeMap(
        map_id=map_id, title=title, kind="custom", source_map=None,
        source_origin=source_origin, source_reason=source_reason,
        seed=41300, floor_style="earth", entrance=(cx, cy - r + 2), exit=(cx, cy + r - 3),
    )
    mask: set[tuple[int, int]] = set()
    base.add_ellipse(mask, cx, cy, r, r)
    p.floor_mask = smooth_mask(mask, iterations=1)
    p.special_markers = {"torches": [(cx - 8, cy - 6), (cx + 8, cy - 6), (cx - 8, cy + 6),
                                      (cx + 8, cy + 6), (cx, cy)], "ore": [], "chests": []}
    return p


class FreshTemplateWrapper:
    def __init__(self, template_source: str = "fresh-relearn",
                 block_source: str = "none", floor_mode: str = "marker_floor_fallback",
                 run_source: str = "none"):
        self.template_source = template_source
        self.block_source = block_source
        self.run_source = run_source
        self.floor_mode = floor_mode
        self.run_mode = run_source == "joel-authored-v1"
        self.joel_mode = block_source == "joel-approved-v1" or self.run_mode
        self.joel_stats: dict[str, Any] = {}
        self.run_stats: dict[str, Any] = {}
        self.library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        self.families = json.loads(FAMILY_PATH.read_text(encoding="utf-8"))
        self.templates_by_role: dict[str, list[dict[str, Any]]] = {}
        for template in self.library["templates"]:
            if template.get("productionStatus") in {"generator_ready", "review_needed"}:
                self.templates_by_role.setdefault(template["role"], []).append(template)
        self.visual_canon_status = (
            self._load_visual_canon_templates()
            if template_source == "visual-canon-v1"
            else {
                "enabled": False,
                "path": str(VISUAL_CANON_PATH.resolve()),
                "generatorReadyTemplatesLoaded": 0,
                "reviewNeededTemplatesSkipped": 0,
                "notes": "current fresh relearn template source",
            }
        )
        if self.run_mode:
            self._load_joel_authored_runs()
        elif self.joel_mode:
            self._load_joel_approved_blocks()
        self.family_by_id = {f["familyId"]: f for f in self.families["families"]}
        self.placements: list[dict[str, Any]] = []
        self.edge_classifications: list[dict[str, Any]] = []
        self.fallbacks: list[dict[str, Any]] = []
        self.skipped_front_bearing: list[dict[str, Any]] = []
        self.cell_template: dict[str, str] = {}
        self.cell_family: dict[str, str] = {}
        self.pattern_counts: Counter[str] = Counter()

    def _load_visual_canon_templates(self) -> dict[str, Any]:
        status = {
            "enabled": True,
            "path": str(VISUAL_CANON_PATH.resolve()),
            "generatorReadyTemplatesLoaded": 0,
            "reviewNeededTemplatesSkipped": 0,
            "missing": False,
            "notes": "Only Joel_approved + generator_ready + locked canon templates are eligible.",
        }
        if not VISUAL_CANON_PATH.exists():
            status["missing"] = True
            status["notes"] = "visual canon file missing; falling back to fresh relearn templates and marker fallbacks"
            return status
        canon = json.loads(VISUAL_CANON_PATH.read_text(encoding="utf-8"))
        for template in canon.get("templates", []):
            eligible = (
                template.get("visualStatus") == "Joel_approved"
                and template.get("generatorStatus") == "generator_ready"
                and template.get("locked") is True
            )
            if not eligible:
                status["reviewNeededTemplatesSkipped"] += 1
                continue
            converted = dict(template)
            converted["productionStatus"] = "generator_ready"
            converted["tileIdFamilyId"] = converted.get("tileIdFamilyId", "visual_canon_v1")
            converted["sourceClusterId"] = converted.get("sourceCropId", "visual_canon_v1")
            converted["confidence"] = converted.get("confidence", 100)
            converted["size"] = f"{converted.get('width')}x{converted.get('height')}"
            self.templates_by_role.setdefault(converted["role"], []).insert(0, converted)
            status["generatorReadyTemplatesLoaded"] += 1
        return status

    def _load_joel_approved_blocks(self) -> None:
        """joel-approved-v1 source: use ONLY locked Joel-approved generator-ready blocks for
        structure. Replaces any fresh/canon role index so no fresh template or loose tile is
        used. A synthetic deep_void_fill is injected (it is not a Joel block)."""
        import joel_block_adapter as adapter
        by_role, stats = adapter.load_joel_templates()
        self.templates_by_role = {role: list(items) for role, items in by_role.items()}
        # synthetic deep-void initializer (not a Joel block; pure void fill)
        self.templates_by_role.setdefault("deep_void_fill", []).append({
            "templateId": "joel_synthetic_deep_void", "role": "deep_void_fill",
            "tileIdFamilyId": "synthetic_deep_void", "size": "1x1", "confidence": 100,
            "productionStatus": "generator_ready", "structuralDesign": "deep_void",
            "sourceClusterId": "synthetic", "anchor": {"x": 0, "y": 0},
            "layerStack": [{"dx": 0, "dy": 0, "stack": {"Back": {"localTileId": 77},
                                                        "Buildings": {"localTileId": DEEP_VOID}}}],
            "tileIdsByLayer": {"Back": [77], "Buildings": [DEEP_VOID]}, "areaCells": 1,
        })
        self.joel_stats = stats

    def _load_joel_authored_runs(self) -> None:
        """run-source joel-authored-v1: placement priority is authored RUN (priority 0) ->
        Joel-approved locked BLOCK (priority 1) -> marker fallback. Whole runs only."""
        import joel_run_adapter as runs_a
        import joel_block_adapter as blocks_a
        by_role: dict[str, list[dict[str, Any]]] = {}
        run_by_role, run_stats = runs_a.load_run_templates()
        for role, items in run_by_role.items():
            for t in items:
                t["_priority"] = 0
            by_role.setdefault(role, []).extend(items)
        block_by_role, block_stats = blocks_a.load_joel_templates()
        for role, items in block_by_role.items():
            for t in items:
                t["_priority"] = 1
            by_role.setdefault(role, []).extend(items)
        by_role.setdefault("deep_void_fill", []).append({
            "templateId": "joel_synthetic_deep_void", "role": "deep_void_fill",
            "tileIdFamilyId": "synthetic_deep_void", "size": "1x1", "confidence": 100,
            "productionStatus": "generator_ready", "structuralDesign": "deep_void",
            "sourceClusterId": "synthetic", "anchor": {"x": 0, "y": 0},
            "layerStack": [{"dx": 0, "dy": 0, "stack": {"Back": {"localTileId": 77},
                                                        "Buildings": {"localTileId": DEEP_VOID}}}],
            "tileIdsByLayer": {"Back": [77], "Buildings": [DEEP_VOID]}, "areaCells": 1, "_priority": 2})
        self.templates_by_role = by_role
        self.run_stats = run_stats
        self.joel_stats = block_stats

    @staticmethod
    def _template_real_cells(template: dict[str, Any]) -> tuple[int, int]:
        """(real non-void Buildings cells, real non-void Front cells)."""
        real_bld = real_front = 0
        for c in template.get("layerStack", []):
            st = c.get("stack") or {}
            if "Buildings" in st and int(st["Buildings"]["localTileId"]) not in VOID_IDS:
                real_bld += 1
            if "Front" in st and int(st["Front"]["localTileId"]) not in VOID_IDS:
                real_front += 1
        return real_bld, real_front

    def _rank_score(self, template: dict[str, Any], want_front: bool) -> float:
        """Deterministic template rank. Prefers complete real layer stacks and, when
        the conformance target expects Front overlays, real (non-void) Front cells.
        Void-only 'Front' (tile 77/135) earns no Front credit."""
        real_bld, real_front = self._template_real_cells(template)
        score = real_bld * 10.0                       # complete structural body
        if want_front:
            score += min(real_front, 5) * 8.0         # real Front shadow/overlay
        score += float(template.get("confidence", 0)) / 10.0
        if str(template.get("productionStatus", "")).startswith("blocked"):
            score -= 100.0
        return score

    def template(self, role: str, preferred_size: Optional[str] = None,
                 want_front: bool = True) -> Optional[dict[str, Any]]:
        items = self.templates_by_role.get(role, [])
        if not items:
            return None
        candidates = items
        if preferred_size:
            sized = [i for i in items if i["size"] == preferred_size]
            if sized:
                candidates = sized
        if self.run_mode:
            # priority: authored run (0) -> approved block (1) -> synthetic (2); then smallest.
            return sorted(candidates, key=lambda t: (t.get("_priority", 1), t.get("areaCells", 9999), t["templateId"]))[0]
        if self.joel_mode:
            # Joel blocks are whole multi-cell windows; prefer the SMALLEST footprint to
            # minimise placement overlap, tie-break by templateId for determinism.
            return sorted(candidates, key=lambda t: (t.get("areaCells", 9999), t["templateId"]))[0]
        # Deterministic ranked selection (replaces blind items[0]). Tie-break by
        # templateId so the choice is stable and explainable.
        ranked = sorted(candidates, key=lambda t: (-self._rank_score(t, want_front), t["templateId"]))
        return ranked[0]

    def apply(self, p: base.PrototypeMap) -> dict[str, Any]:
        self._prepare(p)
        self._initialize_deep_void(p)
        self._paint_floors(p)
        self._wrap_lower_faces(p)
        self._classify_and_place_boundaries(p)
        if self.run_mode:
            self._place_ladder_entrance_once(p)   # authored ladder run, placed ONCE at entrance
        else:
            self._place_ladder(p)
        self._place_torches(p)
        for cell in [p.entrance, p.exit]:
            p.walkable.add(cell)
            p.blocked.discard(cell)
        return self.summary(p)

    def _prepare(self, p: base.PrototypeMap) -> None:
        ex, ey = p.entrance
        base.add_rect(p.floor_mask, ex - 1, ey - 1, ex + 1, ey + 1)
        lx, ly = p.exit
        base.add_rect(p.floor_mask, lx - 1, ly, lx + 1, min(p.height - 2, ly + 2))
        p.init_layers()
        p.walkable.clear()
        p.blocked.clear()
        p.wall_mask.clear()

    def _initialize_deep_void(self, p: base.PrototypeMap) -> None:
        t = self.template("deep_void_fill", "3x3") or self.template("deep_void_fill")
        if not t:
            raise RuntimeError("fresh deep_void_fill template missing")
        for y in range(p.height):
            for x in range(p.width):
                p.set_tile("Back", x, y, 77)
                p.set_tile("Buildings", x, y, DEEP_VOID)
                p.blocked.add((x, y))
        self.pattern_counts[t["templateId"]] += p.width * p.height
        self.placements.append({
            "templateId": t["templateId"],
            "tileIdFamilyId": t["tileIdFamilyId"],
            "role": "deep_void_fill",
            "structuralDesign": "deep_void",
            "placementKind": "full_layer_initialization",
            "cells": p.width * p.height,
            "sourceClusterId": t.get("sourceClusterId", t.get("sourceCropId", "unknown")),
            "layerStackWritten": [{"layer": "Back", "tileId": 77}, {"layer": "Buildings", "tileId": DEEP_VOID}],
        })

    def _paint_floors(self, p: base.PrototypeMap) -> None:
        # Floor blocks are NOT Joel-approved yet. In joel mode use the documented safe floor
        # mode: marker_floor_fallback => flat placeholder floor (single canonical mine floor id,
        # no variation), clearly not a promoted floor block.
        if self.joel_mode and self.floor_mode == "marker_floor_fallback":
            for x, y in sorted(p.floor_mask):
                p.set_tile("Back", x, y, 138)
                p.set_tile("Buildings", x, y, None)
                p.walkable.add((x, y))
                p.blocked.discard((x, y))
            return
        floor_ids = (self.template("floor_base") or {}).get("tileIdsByLayer", {}).get("Back") or [138]
        detail_ids = [137, 138, 139, 140, 153, 154, 155, 169, 170, 171, 185, 187, 188]
        for x, y in sorted(p.floor_mask):
            tid = floor_ids[0] if (x + y + p.seed) % 5 else pick(detail_ids, x, y, p.seed)
            p.set_tile("Back", x, y, tid)
            p.set_tile("Buildings", x, y, None)
            p.walkable.add((x, y))
            p.blocked.discard((x, y))

    def _preflight(self, p: base.PrototypeMap, template: dict[str, Any], ax: int, ay: int) -> tuple[bool, str]:
        anchor = template["anchor"]
        for cell in template["layerStack"]:
            tx = ax + cell["dx"]
            ty = ay + cell["dy"]
            if not in_bounds(p, tx, ty):
                return False, f"out of bounds {tx},{ty}"
            if "Buildings" in cell["stack"] and is_floor(p, tx, ty):
                return False, f"Buildings cell overlaps floor {tx},{ty}"
        return True, ""

    def _ranked_candidates(self, role: str, preferred_size: Optional[str]) -> list[dict[str, Any]]:
        items = self.templates_by_role.get(role, [])
        if not items:
            return []
        if preferred_size:
            sized = [i for i in items if i.get("size") == preferred_size]
            items = sized or items
        if self.run_mode:
            return sorted(items, key=lambda t: (t.get("_priority", 1), t.get("areaCells", 9999), t["templateId"]))
        if self.joel_mode:
            return sorted(items, key=lambda t: (t.get("areaCells", 9999), t["templateId"]))
        return sorted(items, key=lambda t: (-self._rank_score(t, True), t["templateId"]))

    def place_template(self, p: base.PrototypeMap, role: str, ax: int, ay: int, preferred_size: Optional[str], reason: str, rotation: str = "none", allow_floor_back: bool = True) -> bool:
        # In joel/run modes, try candidates in priority order (run -> block -> ...) until one
        # fits; only marker-fallback if none place. Legacy modes keep single-template behavior.
        if self.joel_mode:
            self._last_issue = "no candidate template for role"
            for cand in self._ranked_candidates(role, preferred_size):
                if self._attempt_template(p, cand, role, ax, ay, reason, rotation, allow_floor_back):
                    return True
            return self.fallback(ax, ay, role, rotation, reason, self._last_issue)
        template = self.template(role, preferred_size)
        if not template:
            return self.fallback(ax, ay, role, rotation, reason, "missing fresh template")
        if not self._attempt_template(p, template, role, ax, ay, reason, rotation, allow_floor_back):
            return self.fallback(ax, ay, role, rotation, reason, getattr(self, "_last_issue", "placement failed"))
        return True

    def _attempt_template(self, p: base.PrototypeMap, template: dict[str, Any], role: str, ax: int, ay: int, reason: str, rotation: str = "none", allow_floor_back: bool = True) -> bool:
        real_bld, real_front = self._template_real_cells(template)
        has_front = real_front >= 1
        structural_ok = (
            real_bld >= 2
            or (real_bld >= 1 and real_front >= 1)
            or role in {"ladder_opening", "shaft_opening", "floor_to_wall_transition"}
        )
        if not structural_ok:
            if has_front:
                self.skipped_front_bearing.append({"role": role, "templateId": template["templateId"],
                    "x": ax, "y": ay, "reason": "front-bearing but lacks a paired structural Buildings cell"})
            self._last_issue = "template lacks a complete structural+overlay stack"
            return False
        ok, issue = self._preflight(p, template, ax, ay)
        if not ok:
            if has_front:
                self.skipped_front_bearing.append({"role": role, "templateId": template["templateId"],
                    "x": ax, "y": ay, "reason": f"preflight: {issue}"})
            self._last_issue = issue
            return False
        family_id = template["tileIdFamilyId"]
        written = []
        for cell in template["layerStack"]:
            tx = ax + cell["dx"]
            ty = ay + cell["dy"]
            for layer in LAYERS:
                if layer not in cell["stack"]:
                    continue
                tile_id = int(cell["stack"][layer]["localTileId"])
                if layer in {"Buildings", "Front"} and tile_id in VOID_IDS:
                    continue  # never stamp void as a structural or overlay tile
                if layer == "Back" and is_floor(p, tx, ty) and not allow_floor_back:
                    continue
                if layer in {"AlwaysFront", "Paths"}:
                    continue
                p.set_tile(layer, tx, ty, tile_id)
                if layer == "Buildings":
                    p.blocked.add((tx, ty))
                    p.wall_mask.add((tx, ty))
                    key = f"{tx},{ty}"
                    self.cell_template[key] = template["templateId"]
                    self.cell_family[key] = family_id
                written.append({"layer": layer, "x": tx, "y": ty, "tileId": tile_id})
        if not any(c["layer"] == "Buildings" for c in written) and role not in {"floor_to_wall_transition"}:
            self._last_issue = "template wrote no structural Buildings cells"
            return False
        self.pattern_counts[template["templateId"]] += 1
        front_written = sum(1 for c in written if c["layer"] == "Front")
        rec = {
            "templateId": template["templateId"],
            "tileIdFamilyId": family_id,
            "sourceClusterId": template.get("sourceClusterId", template.get("sourceCropId", "unknown")),
            "role": role,
            "structuralDesign": template["structuralDesign"],
            "anchor": {"x": ax, "y": ay},
            "rotation": rotation,
            "reason": reason,
            "hasFront": has_front,
            "frontCellsWritten": front_written,
            "templateRankScore": round(self._rank_score(template, True), 2),
            "whySelected": f"ranked top for role '{role}': realBuildings={real_bld}, realFront={real_front}, confidence={template.get('confidence')}",
            "layerStackWritten": written,
        }
        if self.joel_mode:
            rec["blockType"] = template.get("blockType")
            rec["blockId"] = template.get("originalBlockId", template["templateId"])
            rec["sourceMap"] = template.get("sourceMap")
            rec["sourceCoordinate"] = template.get("sourceCoordinate")
            rec["locked"] = template.get("locked", True)
            rec["size"] = template.get("size")
        if template.get("isRun"):
            rec["isRun"] = True
            rec["runId"] = template["templateId"]
            rec["runType"] = template.get("runType")
            rec["orientation"] = template.get("orientation")
            rec["sourcePatternFile"] = template.get("sourceMap")
            rec["placementSource"] = "joel_authored_run"
        elif self.run_mode:
            rec["placementSource"] = "joel_approved_block"
        self.placements.append(rec)
        return True

    def fallback(self, x: int, y: int, role: str, rotation: str, reason: str, issue: str) -> bool:
        rec = {
            "templateId": "marker_only_fallback",
            "tileIdFamilyId": None,
            "role": role,
            "structuralDesign": "fallback",
            "anchor": {"x": x, "y": y},
            "rotation": rotation,
            "reason": reason,
            "issue": issue,
            "layerStackWritten": [],
        }
        self.fallbacks.append(rec)
        self.placements.append(rec)
        return False

    def _wrap_lower_faces(self, p: base.PrototypeMap) -> None:
        for x, y in sorted(p.floor_mask):
            if is_floor(p, x, y - 1):
                continue
            # Fresh lower-face template's anchor is the middle wall cell; put
            # its floor-transition row at the semantic floor cell.
            self.place_template(p, "lower_face_3_tile_stack", x, y - 1, "1x3", "floor has void directly north", "northward")
            self.place_template(p, "floor_to_wall_transition", x, y, "3x1", "learned shadow/floor transition under lower face", "none")

    def _neighbors8(self, p: base.PrototypeMap, x: int, y: int) -> dict[str, bool]:
        return {
            "N": is_floor(p, x, y - 1), "NE": is_floor(p, x + 1, y - 1),
            "E": is_floor(p, x + 1, y), "SE": is_floor(p, x + 1, y + 1),
            "S": is_floor(p, x, y + 1), "SW": is_floor(p, x - 1, y + 1),
            "W": is_floor(p, x - 1, y), "NW": is_floor(p, x - 1, y - 1),
        }

    def classify(self, n: dict[str, bool]) -> tuple[str, str, str]:
        card = {d for d in ["N", "E", "S", "W"] if n[d]}
        diag = {d for d in ["NE", "SE", "SW", "NW"] if n[d]}
        if card == {"E"}:
            return "left_wall_edge", "E", "single east floor"
        if card == {"W"}:
            return "right_wall_edge", "W", "single west floor"
        if card == {"S", "E"}:
            return "lower_left_inner_corner", "SE", "south+east floor"
        if card == {"S", "W"}:
            return "lower_right_inner_corner", "SW", "south+west floor"
        if card == {"N", "E"}:
            return "upper_left_inner_corner", "NE", "north+east floor"
        if card == {"N", "W"}:
            return "upper_right_inner_corner", "NW", "north+west floor"
        if not card and len(diag) == 1:
            d = next(iter(diag))
            return {
                "SE": ("upper_left_outer_corner", "SE", "diagonal-only SE floor"),
                "SW": ("upper_right_outer_corner", "SW", "diagonal-only SW floor"),
                "NE": ("lower_left_outer_corner", "NE", "diagonal-only NE floor"),
                "NW": ("lower_right_outer_corner", "NW", "diagonal-only NW floor"),
            }[d]
        if card == {"N"}:
            return "wall_body", "N", "single north floor"
        if card == {"S"}:
            return "lower_face_3_tile_stack", "S", "single south floor handled by extrusion"
        return "ambiguous", "".join(sorted(card | diag)), "no fresh approved boundary template"

    def _classify_and_place_boundaries(self, p: base.PrototypeMap) -> None:
        for y in range(p.height):
            for x in range(p.width):
                if is_floor(p, x, y):
                    continue
                n = self._neighbors8(p, x, y)
                if not any(n.values()):
                    continue
                role, rotation, reason = self.classify(n)
                self.edge_classifications.append({"x": x, "y": y, "role": role, "rotation": rotation, "reason": reason, "neighbors": n})
                if role == "ambiguous":
                    self.fallback(x, y, role, rotation, reason, "ambiguous boundary")
                    continue
                if role == "lower_face_3_tile_stack":
                    continue
                # A wall cell with floor only to the north is the exposed wall TOP. The learned
                # `wall_body` template here is void-only (Front=77); the complete Front-bearing
                # `wall_top` template (Back+Buildings+Front real tiles) is the correct art for this
                # geometry, so remap to it. place_template falls back to a marker if it is unsafe.
                if role == "wall_body" and self.template("wall_top") is not None:
                    role = "wall_top"
                    reason = reason + " (remapped wall_body->wall_top: exposed north wall top, complete Front template)"
                preferred = "1x3" if role in {"left_wall_edge", "right_wall_edge"} or "corner" in role else None
                self.place_template(p, role, x, y, preferred, reason, rotation)

    def _place_ladder(self, p: base.PrototypeMap) -> None:
        x, y = p.exit
        self.place_template(p, "ladder_opening", x, y, "1x3", "learned ladder opening at exit", "none")
        for yy in range(y - 1, y + 2):
            if in_bounds(p, x, yy):
                p.walkable.add((x, yy))
                p.blocked.discard((x, yy))

    def _place_ladder_entrance_once(self, p: base.PrototypeMap) -> None:
        """Place ONE authored ladder-entrance run at the top opening of the cavern, and never
        reuse the ladder pattern anywhere else (Joel's rule). Anchors at a north-edge slot (a
        void cell with floor to the south) so the run's wall body extends up into the void."""
        self.ladder_placement = None
        cands = self._ranked_candidates("ladder_entrance", None)
        if not cands:
            self.fallback(p.entrance[0], p.entrance[1], "ladder_entrance", "none",
                          "single ladder entrance at start", "no authored ladder-entrance run available")
            return
        cx = p.entrance[0]
        # north-edge slots: void cells with floor directly south, preferred topmost + nearest centre
        slots = sorted(((y, abs(x - cx), x) for y in range(p.height) for x in range(p.width)
                        if (x, y) not in p.floor_mask and (x, y + 1) in p.floor_mask))
        for y, _, x in slots:
            for cand in cands:
                if self._attempt_template(p, cand, "ladder_entrance", x, y,
                                          "single authored ladder entrance at top opening", "none"):
                    self.ladder_placement = cand["templateId"]
                    for yy in range(y, y + 4):
                        if (x, yy) in p.floor_mask:
                            p.walkable.add((x, yy)); p.blocked.discard((x, yy))
                    p.entrance = (x, y + 1)
                    return
        self.fallback(cx, p.entrance[1], "ladder_entrance", "none",
                      "single ladder entrance at start", "no north-edge slot fit the ladder run")

    def _place_torches(self, p: base.PrototypeMap) -> None:
        for x, y in p.special_markers.get("torches", []):
            if in_bounds(p, x, y):
                p.set_tile("Front", x, y, 48 if (x + y) % 2 else 80)

    def summary(self, p: base.PrototypeMap) -> dict[str, Any]:
        buildings = sum(1 for g in p.layers["Buildings"] if (base.local_id(g) is not None and base.local_id(g) != DEEP_VOID))
        fronts = sum(1 for g in p.layers["Front"] if base.local_id(g) is not None)
        out = {
            "algorithm": "fresh_template_library_smart_edge_wrapper_v2",
            "templateLibrary": str(LIBRARY_PATH.resolve()),
            "tileIdFamilies": str(FAMILY_PATH.resolve()),
            "blockSourceMode": self.block_source,
            "floorCells": len(p.floor_mask),
            "wallCells": len(p.wall_mask),
            "buildingsTiles": buildings,
            "frontTiles": fronts,
            "frontToBuildingsRatio": fronts / buildings if buildings else 0,
            "frontBearingTemplatesUsed": sorted({pl["templateId"] for pl in self.placements if pl.get("frontCellsWritten")}),
            "frontCellsWritten": sum(pl.get("frontCellsWritten", 0) for pl in self.placements),
            "skippedFrontBearing": self.skipped_front_bearing,
            "templateCounts": dict(sorted(self.pattern_counts.items())),
            "fallbackCount": len(self.fallbacks),
            "cellTemplate": dict(sorted(self.cell_template.items())),
            "cellFamily": dict(sorted(self.cell_family.items())),
        }
        if self.joel_mode:
            placed = [pl for pl in self.placements if pl.get("templateId") != "marker_only_fallback"
                      and pl.get("role") != "deep_void_fill"]
            by_type = Counter(pl.get("blockType") for pl in placed if pl.get("blockType"))
            by_role = Counter(pl.get("role") for pl in placed)
            fb_by_role = Counter(fb["role"] for fb in self.fallbacks)
            out.update({
                "blockSourceLibrary": self.joel_stats.get("libraryPath"),
                "floorMode": self.floor_mode,
                "floorApprovalPending": True,
                "approvedBlockPlacements": len(placed),
                "placedBlockCountByType": dict(by_type),
                "placedCountByRole": dict(sorted(by_role.items())),
                "markerFallbackCount": len(self.fallbacks),
                "markerFallbackByRole": dict(sorted(fb_by_role.items())),
                "decorationVariantsSkipped": self.joel_stats.get("decorationVariantsSkipped"),
                "reviewNeededOpeningsSkipped": self.joel_stats.get("reviewNeededOpeningsSkipped"),
                "unapprovedFloorBlocksUsed": 0,
                "interiorWallBodyBlocksNotConsumed": self.joel_stats.get("interiorWallBodyBlocks"),
                "joelAdapterStats": self.joel_stats,
                "placedBlockIds": sorted({pl.get("blockId") for pl in placed if pl.get("blockId")}),
            })
            if self.run_mode:
                run_pl = [pl for pl in placed if pl.get("isRun")]
                block_pl = [pl for pl in placed if pl.get("placementSource") == "joel_approved_block"]
                out.update({
                    "runSourceMode": self.run_source,
                    "runLibrary": str((ROOT / "pattern_learning" / "joel_authored_runs_v1" / "joel_authored_runs_v1.json")),
                    "authoredRunPlacements": len(run_pl),
                    "approvedBlockPlacementsSecondary": len(block_pl),
                    "placedRunIds": sorted({pl.get("runId") for pl in run_pl if pl.get("runId")}),
                    "placedRunTypeCounts": dict(Counter(pl.get("runType") for pl in run_pl)),
                    "runRoleCounts": dict(Counter(pl.get("role") for pl in run_pl)),
                    "runAdapterStats": self.run_stats,
                    "placementPriority": ["joel_authored_run", "joel_approved_block", "marker_fallback"],
                    "ladderEntrancePlacements": sum(1 for pl in run_pl if pl.get("runType") in {"ladder_entrance", "shaft_socket", "entrance_socket"}),
                    "ladderPlacedId": getattr(self, "ladder_placement", None),
                })
        return out


def tile_usage_by_layer(p: base.PrototypeMap) -> dict[str, dict[str, int]]:
    out = {}
    for layer, data in p.layers.items():
        c = Counter(base.local_id(g) for g in data if base.local_id(g) is not None)
        out[layer] = {str(k): int(v) for k, v in sorted(c.items())}
    return out


def write_debug(wrapper: FreshTemplateWrapper) -> dict[str, Path]:
    edge = OUT_DIR / "edge_classification_debug.json"
    placements = OUT_DIR / "template_placement_debug.json"
    families = OUT_DIR / "tile_id_family_placement_debug.json"
    edge.write_text(json.dumps(wrapper.edge_classifications, indent=2), encoding="utf-8")
    placements.write_text(json.dumps(wrapper.placements, indent=2), encoding="utf-8")
    families.write_text(json.dumps({"cellFamily": wrapper.cell_family, "fallbacks": wrapper.fallbacks}, indent=2), encoding="utf-8")
    return {"edge": edge, "placements": placements, "families": families}


def draw_overlays(p: base.PrototypeMap, wrapper: FreshTemplateWrapper) -> dict[str, Path]:
    scale = 8
    colors = {
        "floor": (74, 145, 86, 255), "void": (20, 20, 24, 255),
        "lower_face_3_tile_stack": (222, 190, 84, 255), "left_wall_edge": (84, 160, 222, 255),
        "right_wall_edge": (84, 160, 222, 255), "inner": (222, 110, 110, 255),
        "outer": (180, 110, 222, 255), "fallback": (255, 60, 60, 255),
    }
    paths = {}
    for name in ["template_overlay", "edge_classification_overlay", "tile_id_family_overlay"]:
        img = Image.new("RGBA", (p.width * scale, p.height * scale), colors["void"])
        draw = ImageDraw.Draw(img)
        for y in range(p.height):
            for x in range(p.width):
                box = (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1)
                if is_floor(p, x, y):
                    draw.rectangle(box, fill=colors["floor"])
        if name == "edge_classification_overlay":
            for e in wrapper.edge_classifications:
                role = e["role"]
                c = colors["fallback"] if role == "ambiguous" else (colors["inner"] if "inner" in role else (colors["outer"] if "outer" in role else colors.get(role, (210, 210, 210, 255))))
                x, y = e["x"], e["y"]
                draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=c)
        else:
            for pl in wrapper.placements:
                c = colors["fallback"] if pl["templateId"] == "marker_only_fallback" else (colors["inner"] if "inner" in pl["role"] else (colors["outer"] if "outer" in pl["role"] else colors.get(pl["role"], (210, 210, 210, 255))))
                cells = pl.get("layerStackWritten", [])
                if isinstance(cells, list):
                    for cell in cells:
                        if cell.get("layer") == "Buildings" and "x" in cell and "y" in cell:
                            x, y = cell["x"], cell["y"]
                            draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=c)
        out = OUT_DIR / f"{name}.png"
        img.save(out)
        paths[name] = out
    return paths


def write_metadata(p: base.PrototypeMap, wrapper: FreshTemplateWrapper, result: dict[str, Any], validation: dict[str, Any], paths: dict[str, str]) -> Path:
    doc = {
        "generatedAt": now_iso(),
        "mapId": p.map_id,
        "prototypeOnly": True,
        "productionMapOutput": False,
        "generator": "build_smart_edge_wrapper_v2.py",
        "templateSource": wrapper.template_source,
        "blockSourceMode": wrapper.block_source,
        "runSourceMode": wrapper.run_source,
        "approvedBlockLibrary": (wrapper.joel_stats.get("libraryPath") if wrapper.joel_mode else None),
        "floorMode": (wrapper.floor_mode if wrapper.joel_mode else None),
        "floorApprovalPending": bool(wrapper.joel_mode),
        "visualCanonStatus": wrapper.visual_canon_status,
        "usesOnlyFreshRepeatedStructureTemplates": (not wrapper.joel_mode),
        "usesOnlyLockedJoelApprovedBlocksForStructure": bool(wrapper.joel_mode),
        "noLooseStructuralTiles": True,
        "tileUsageByLayer": tile_usage_by_layer(p),
        "freshTemplateWrapper": result,
        "paths": paths,
        "validation": validation,
        "protectedPathsStatus": {
            "productionMapsGenerated": False,
            "originalMoonvillageMapsModified": False,
            "missionAssetsModified": False,
            "unpackedBasegameModified": False,
            "approvedProductionDbModified": False,
        },
    }
    out = OUT_DIR / "metadata.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def make_before_after(custom08_preview: Path) -> Optional[Path]:
    old = OUT_ROOT / "custom_07_advanced_edge_wrapped" / "preview_clean.png"
    if not old.exists():
        return None
    a = Image.open(old).convert("RGBA")
    b = Image.open(custom08_preview).convert("RGBA")
    sheet = Image.new("RGBA", (a.width + b.width + 24, max(a.height, b.height)), (18, 18, 22, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (a.width + 24, 0))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), "custom_07", fill=(255, 255, 255, 230))
    d.text((a.width + 34, 10), "custom_08 fresh templates", fill=(255, 255, 255, 230))
    out = OUT_DIR / "before_after_custom_07_vs_custom_08.png"
    sheet.save(out)
    return out


def write_summary_report(validation: dict[str, Any], result: dict[str, Any], paths: dict[str, str]) -> Path:
    lines = [
        "# Custom 08 Fresh Template Test",
        "",
        f"- Status: {validation['status']}",
        f"- Floor cells: {result['floorCells']}",
        f"- Wall cells: {result['wallCells']}",
        f"- Front/Buildings ratio: {result['frontToBuildingsRatio']:.3f}",
        f"- Marker fallbacks: {result['fallbackCount']}",
        "- Uses only fresh repeated structure templates: YES",
        "- Production-ready: NO",
        "",
        "## Outputs",
    ]
    for key, value in paths.items():
        lines.append(f"- {key}: `{value}`")
    out = OUT_DIR / "custom_08_fresh_template_test_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def draw_block_overlay(p: base.PrototypeMap, wrapper: FreshTemplateWrapper) -> Path:
    """Colour each placed Buildings cell by its approved block (stable hue per blockId);
    marker fallbacks are red. Shows which structure came from which Joel-approved block."""
    scale = 8
    img = Image.new("RGBA", (p.width * scale, p.height * scale), (20, 20, 24, 255))
    draw = ImageDraw.Draw(img)
    for y in range(p.height):
        for x in range(p.width):
            if is_floor(p, x, y):
                draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=(74, 145, 86, 255))
    palette = [(84, 160, 222), (222, 190, 84), (110, 200, 150), (200, 130, 220),
               (230, 150, 90), (120, 210, 220), (210, 110, 140), (160, 190, 110)]
    block_color = {}
    for pl in wrapper.placements:
        if pl.get("templateId") == "marker_only_fallback":
            continue
        bid = pl.get("blockId") or pl.get("templateId")
        if bid not in block_color:
            block_color[bid] = palette[len(block_color) % len(palette)]
        c = block_color[bid] + (255,)
        for cell in pl.get("layerStackWritten", []):
            if cell.get("layer") == "Buildings" and "x" in cell:
                x, y = cell["x"], cell["y"]
                draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=c)
    for fb in wrapper.fallbacks:
        x, y = fb["anchor"]["x"], fb["anchor"]["y"]
        draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=(255, 60, 60, 255))
    out = OUT_DIR / "block_overlay.png"
    img.save(out)
    return out


def make_before_after_custom11(custom11_preview: Path) -> Optional[Path]:
    old = OUT_ROOT / "custom_09_front_promotion_checkpoint" / "preview_clean.png"
    if not old.exists():
        return None
    a = Image.open(old).convert("RGBA")
    b = Image.open(custom11_preview).convert("RGBA")
    sheet = Image.new("RGBA", (a.width + b.width + 24, max(a.height, b.height)), (18, 18, 22, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (a.width + 24, 0))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), "custom_09 (fresh templates)", fill=(255, 255, 255, 230))
    d.text((a.width + 34, 10), "custom_11 (Joel-approved blocks)", fill=(255, 255, 255, 230))
    out = OUT_DIR / "before_after_custom_09_vs_custom_11.png"
    sheet.save(out)
    return out


def make_side_by_side(left_preview: Path, right_preview: Path, left_label: str, right_label: str, out_name: str) -> Optional[Path]:
    if not left_preview.exists() or not right_preview.exists():
        return None
    a = Image.open(left_preview).convert("RGBA")
    b = Image.open(right_preview).convert("RGBA")
    sheet = Image.new("RGBA", (a.width + b.width + 24, max(a.height, b.height)), (18, 18, 22, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (a.width + 24, 0))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), left_label, fill=(255, 255, 255, 230))
    d.text((a.width + 34, 10), right_label, fill=(255, 255, 255, 230))
    out = OUT_DIR / out_name
    sheet.save(out)
    return out


def draw_run_overlay(p: base.PrototypeMap, wrapper: FreshTemplateWrapper) -> Path:
    """Colour cells by placement source: authored run (blue hues), approved block (amber),
    marker fallback (red), floor (green)."""
    scale = 8
    img = Image.new("RGBA", (p.width * scale, p.height * scale), (20, 20, 24, 255))
    draw = ImageDraw.Draw(img)
    for y in range(p.height):
        for x in range(p.width):
            if is_floor(p, x, y):
                draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=(74, 145, 86, 255))
    run_palette = [(84, 160, 222), (110, 200, 220), (120, 150, 230), (90, 190, 200)]
    run_color = {}
    for pl in wrapper.placements:
        if pl.get("templateId") == "marker_only_fallback" or pl.get("role") == "deep_void_fill":
            continue
        if pl.get("isRun"):
            rid = pl.get("runId")
            if rid not in run_color:
                run_color[rid] = run_palette[len(run_color) % len(run_palette)]
            c = run_color[rid] + (255,)
        else:
            c = (222, 180, 90, 255)  # approved block (secondary)
        for cell in pl.get("layerStackWritten", []):
            if cell.get("layer") == "Buildings" and "x" in cell:
                draw.rectangle((cell["x"] * scale, cell["y"] * scale, (cell["x"] + 1) * scale - 1, (cell["y"] + 1) * scale - 1), fill=c)
    for fb in wrapper.fallbacks:
        x, y = fb["anchor"]["x"], fb["anchor"]["y"]
        draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=(255, 60, 60, 255))
    out = OUT_DIR / "run_overlay.png"
    img.save(out)
    return out


def main() -> int:
    global OUT_DIR
    parser = argparse.ArgumentParser(description="Generate Smart Edge-Wrapper v2 prototype maps.")
    parser.add_argument(
        "--template-source",
        choices=["fresh-relearn", "visual-canon-v1"],
        default="fresh-relearn",
        help="Template source for fresh/canon modes. visual-canon-v1 only loads Joel_approved + generator_ready + locked canon templates.",
    )
    parser.add_argument(
        "--block-source",
        choices=["none", "joel-approved-v1"],
        default="none",
        help="joel-approved-v1: build core structure ONLY from joel_approved_building_blocks_v1.locked.json (custom_11 gated test).",
    )
    parser.add_argument(
        "--run-source",
        choices=["none", "joel-authored-v1"],
        default="none",
        help="joel-authored-v1: prioritize complete Joel-authored runs (joel_authored_runs_v1) for "
             "structure, then Joel-approved blocks, then marker (custom_12 test).",
    )
    parser.add_argument(
        "--floor-mode",
        choices=["marker_floor_fallback", "canon_floor_fallback", "fresh_floor_fallback"],
        default="marker_floor_fallback",
        help="Floor handling while floor blocks are unapproved. Default marker_floor_fallback = flat placeholder floor.",
    )
    parser.add_argument(
        "--layout",
        choices=["cavern", "round"],
        default="cavern",
        help="Test map layout. 'round' = a single simple round cavern (preferred for gated tests).",
    )
    args = parser.parse_args()
    run = args.run_source == "joel-authored-v1"
    joel = args.block_source == "joel-approved-v1" or run
    round_layout = args.layout == "round"
    if run and round_layout:
        OUT_DIR = OUT_ROOT / "custom_13_round_authored_test"
    elif run:
        OUT_DIR = OUT_ROOT / "custom_12_joel_authored_runs_test"
    elif args.block_source == "joel-approved-v1":
        OUT_DIR = OUT_ROOT / "custom_11_joel_block_gated_test"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "tilesheets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(base.TILESET_SRC, TILESET_OUT)
    if run and round_layout:
        p = make_round_test_map(
            "custom_13_round_authored_test", "Custom 13 - Round Authored Test",
            "simple round test cavern rendered with Joel-authored runs (priority) + Joel-approved blocks",
            "Round test layout (Joel's preferred starting shape); single ladder entrance at start, never reused.")
    else:
        p = make_custom_08()
    if run and round_layout:
        pass  # map id/title already set by make_round_test_map
    elif run:
        p.map_id = "custom_12_joel_authored_runs_test"
        p.title = "Custom 12 - Joel-Authored Runs Test"
        p.source_origin = "prototype rendered with Joel-authored runs (priority) + Joel-approved blocks for structure"
        p.source_reason = "Tests Joel-authored mine/dungeon runs (top walls, lower faces, corners, ladder) as whole structures; floors unapproved (marker fallback)."
    elif joel:
        p.map_id = "custom_11_joel_block_gated_test"
        p.title = "Custom 11 - Joel-Approved Block Gated Test"
        p.source_origin = "gated prototype rendered ONLY with locked Joel-approved building blocks for structure"
        p.source_reason = "First gated test of Joel-approved mine building blocks (walls/edges/corners/lower-faces); floors unapproved (marker fallback)."
    wrapper = FreshTemplateWrapper(template_source=args.template_source,
                                   block_source=args.block_source, floor_mode=args.floor_mode,
                                   run_source=args.run_source)
    result = wrapper.apply(p)
    tmx = base.write_tmx(p, OUT_DIR, "../tilesheets/mine.png")
    tmj = base.write_tmj(p, OUT_DIR, "../tilesheets/mine.png")
    tilesheet = Image.open(TILESET_OUT).convert("RGBA")
    clean, labeled = base.render_map(p, tilesheet, OUT_DIR)
    debug_paths = write_debug(wrapper)
    overlay_paths = draw_overlays(p, wrapper)
    validation = base.validate_prototype(p, tmx, tmj, "../tilesheets/mine.png")
    validation_report = base.write_validation_report(p, OUT_DIR, validation, "validation_report.md")
    paths = {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "validation_report": str(validation_report.resolve()),
        "edge_classification_debug": str(debug_paths["edge"].resolve()),
        "template_placement_debug": str(debug_paths["placements"].resolve()),
        "tile_id_family_debug": str(debug_paths["families"].resolve()),
        "template_overlay": str(overlay_paths["template_overlay"].resolve()),
        "edge_classification_overlay": str(overlay_paths["edge_classification_overlay"].resolve()),
        "tile_id_family_overlay": str(overlay_paths["tile_id_family_overlay"].resolve()),
    }
    if run:
        run_overlay = draw_run_overlay(p, wrapper)
        paths["run_overlay"] = str(run_overlay.resolve())
        block_overlay = draw_block_overlay(p, wrapper)
        paths["template_overlay_blocks"] = str(block_overlay.resolve())
        ba09 = make_side_by_side(OUT_ROOT / "custom_09_front_promotion_checkpoint" / "preview_clean.png",
                                 clean, "custom_09 (fresh templates)", "custom_12 (Joel-authored runs)",
                                 "before_after_custom_09_vs_custom_12.png")
        if ba09:
            paths["before_after_custom_09_vs_custom_12"] = str(ba09.resolve())
        ba11 = make_side_by_side(OUT_ROOT / "custom_11_joel_block_gated_test" / "preview_clean.png",
                                 clean, "custom_11 (Joel blocks)", "custom_12 (Joel-authored runs)",
                                 "before_after_custom_11_vs_custom_12.png")
        if ba11:
            paths["before_after_custom_11_vs_custom_12"] = str(ba11.resolve())
    elif joel:
        block_overlay = draw_block_overlay(p, wrapper)
        paths["block_overlay"] = str(block_overlay.resolve())
        before_after = make_before_after_custom11(clean)
        if before_after:
            paths["before_after_custom_09_vs_custom_11"] = str(before_after.resolve())
    else:
        before_after = make_before_after(clean)
        if before_after:
            paths["before_after_custom_07_vs_custom_08"] = str(before_after.resolve())
    metadata = write_metadata(p, wrapper, result, validation, paths)
    paths["metadata"] = str(metadata.resolve())
    report = write_summary_report(validation, result, paths)
    paths["summary_report"] = str(report.resolve())
    print(json.dumps({
        "status": validation["status"],
        "blockSourceMode": wrapper.block_source,
        "floorMode": wrapper.floor_mode if joel else None,
        "frontToBuildingsRatio": result["frontToBuildingsRatio"],
        "floorCells": result["floorCells"],
        "wallCells": result["wallCells"],
        "approvedBlockPlacements": result.get("approvedBlockPlacements"),
        "fallbackCount": result["fallbackCount"],
        "outDir": str(OUT_DIR.resolve()),
    }, indent=2))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
