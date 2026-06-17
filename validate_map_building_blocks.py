#!/usr/bin/env python3
"""validate_map_building_blocks.py  (READ-ONLY) — integrity gate for the mine block library."""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
REPORT = ROOT / "reports" / "map_building_blocks_validation_results.md"
MINE_DIR = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
REQUIRED = ["blockId", "blockType", "profile", "sourceCategory", "width", "height",
            "anchor", "cells", "floorMask", "wallMask", "voidMask", "shadowMask",
            "frequency", "sourceMapCount", "visualStatus", "generatorStatus", "locked"]
STRUCTURAL = {"mine_wall_forward_lower_face", "mine_wall_back_top_edge", "mine_wall_body",
              "mine_wall_left_edge", "mine_wall_right_edge", "mine_inner_corner",
              "mine_outer_corner", "mine_angled_wall", "mine_blocked_boundary"}


def main():
    errors, warnings, checks = [], [], []

    def parse(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"parse failed {Path(p).name}: {e}")
            return None

    files = ["building_block_library.json", "building_block_schema.json", "block_type_schema.json",
             "tile_id_combination_index.json", "negative_building_block_rules.json",
             "clusters/building_block_clusters.json", "by_type/building_blocks_by_type.json",
             "by_size/building_blocks_by_size.json", "source_inventory.json"]
    docs = {}
    for f in files:
        docs[f] = parse(MBB / f)
    checks.append(("all JSON parse", not errors))

    lib = docs.get("building_block_library.json")
    if lib:
        blocks = lib.get("blocks", [])
        mine_names = {p.name for p in MINE_DIR.glob("*.tbin")}
        missing_fields = single_tile = bad_source = void_only = not_repeated = gen_ready_unlocked = 0
        for b in blocks:
            if any(k not in b for k in REQUIRED):
                missing_fields += 1
            # structural blocks must preserve a multi-cell layer stack (not a single loose tile)
            if b["blockType"] in STRUCTURAL and len(b.get("cells", [])) < 2:
                single_tile += 1
            # source maps must exist
            for ex in b.get("exampleSourceCoordinates", [])[:1]:
                if ex.get("map") not in mine_names:
                    bad_source += 1
            # not void-only
            real = any(int(t) not in {77, 135} for c in b["cells"] for t in c["stack"].values())
            if not real:
                void_only += 1
            if b.get("frequency", 0) < 4 or b.get("sourceMapCount", 0) < 3:
                not_repeated += 1
            if b.get("generatorStatus") == "generator_ready" and not (b.get("locked") and b.get("visualStatus") == "approved"):
                gen_ready_unlocked += 1
        checks += [
            ("library has blocks", len(blocks) > 0),
            ("all blocks have required fields", missing_fields == 0),
            ("structural blocks preserve multi-cell layer stacks (not single loose tile)", single_tile == 0),
            ("block source maps exist", bad_source == 0),
            ("no void-only blocks promoted", void_only == 0),
            ("all library blocks are repeated (freq>=4, maps>=3)", not_repeated == 0),
            ("no generator_ready block is unapproved/unlocked", gen_ready_unlocked == 0),
        ]
        if missing_fields: errors.append(f"{missing_fields} blocks missing required fields")
        if single_tile: errors.append(f"{single_tile} structural blocks are single-tile (loose) — forbidden")
        if bad_source: errors.append(f"{bad_source} blocks reference a non-existent source map")
        if void_only: errors.append(f"{void_only} void-only blocks were promoted")
        if not_repeated: errors.append(f"{not_repeated} library blocks are not repeated")
        if gen_ready_unlocked: errors.append(f"{gen_ready_unlocked} generator_ready blocks are not approved+locked")

    neg = docs.get("negative_building_block_rules.json")
    checks.append(("negative rules exist", bool(neg and neg.get("rules"))))

    status = "PASS" if not errors else "FAIL"
    lines = ["# Map Building Blocks — Validation", "", f"- Status: **{status}**",
             f"- Errors: {len(errors)} | Warnings: {len(warnings)}", "", "## Checks"]
    for name, ok in checks:
        lines.append(f"- [{'OK' if ok else 'FAIL'}] {name}")
    if errors:
        lines += ["", "## Errors"] + [f"- {e}" for e in errors]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Map building blocks validation {status}; errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
