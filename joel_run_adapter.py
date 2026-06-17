#!/usr/bin/env python3
"""
joel_run_adapter.py  (READ-ONLY)

Adapts joel_authored_runs_v1 runs into the Smart Edge-Wrapper v2 template schema, keyed by
each run's generatorRole and anchored at its floor-contact cell so the whole authored run is
stamped as one structure (the run body extends into the void, never onto floor). Whole runs
only -- no trimming, no loose tiles.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "pattern_learning" / "joel_authored_runs_v1" / "joel_authored_runs_v1.json"


LADDER_RUN_TYPES = {"ladder_entrance", "shaft_socket", "entrance_socket"}


def convert_run(run):
    # Ladder/entrance runs get a DEDICATED role so they are never pulled into generic
    # wall/boundary placement. They are placed exactly once, at the map entrance.
    if run.get("runType") in LADDER_RUN_TYPES:
        role = "ladder_entrance"
    else:
        role = run.get("generatorRole")
    if not role:
        return None
    ax, ay = run["anchor"]["x"], run["anchor"]["y"]
    layer_stack = []
    ids = {"Back": set(), "Buildings": set(), "Front": set()}
    for c in run["normalizedLayerStack"]:
        layer = c["layer"]
        if layer not in ids:
            continue
        tid = int(c["tileId"])
        layer_stack.append({"dx": c["dx"] - ax, "dy": c["dy"] - ay, "stack": {layer: {"localTileId": tid}}})
        ids[layer].add(tid)
    return {
        "templateId": run["runId"], "role": role, "tileIdFamilyId": "joel_authored_v1",
        "size": f"{run['width']}x{run['height']}", "confidence": 95,
        "productionStatus": "generator_ready", "structuralDesign": run["runType"],
        "sourceClusterId": run["runId"], "anchor": {"x": ax, "y": ay},
        "layerStack": layer_stack, "tileIdsByLayer": {k: sorted(v) for k, v in ids.items()},
        "blockType": run["runType"], "originalBlockId": run["runId"],
        "runType": run["runType"], "orientation": run["orientation"],
        "sourceMap": run["sourcePatternFile"], "sourceCoordinate": {"x": ax, "y": ay},
        "areaCells": run["width"] * run["height"], "joelVisualStatus": run["visualStatus"],
        "decorationVariant": run.get("decorationVariant", False), "isRun": True,
        "locked": False,
    }


def load_run_templates(path=RUNS):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    by_role = {}
    stats = {"runsTotal": len(data["runs"]), "converted": 0, "skippedNoRole": 0,
             "decorationVariants": 0, "roleCounts": {}}
    for r in data["runs"]:
        if r.get("decorationVariant"):
            stats["decorationVariants"] += 1
        conv = convert_run(r)
        if conv is None:
            stats["skippedNoRole"] += 1
            continue
        # Decoration variants are not used as generic core structure -- EXCEPT ladder/entrance
        # runs, which carry an opening but are placed exactly once via the dedicated
        # 'ladder_entrance' role (never as generic wall).
        if r.get("decorationVariant") and r.get("runType") not in LADDER_RUN_TYPES:
            continue
        by_role.setdefault(conv["role"], []).append(conv)
        stats["converted"] += 1
    for role in by_role:
        by_role[role].sort(key=lambda t: (t["areaCells"], t["templateId"]))
    stats["roleCounts"] = {r: len(v) for r, v in sorted(by_role.items())}
    return by_role, stats


if __name__ == "__main__":
    by_role, stats = load_run_templates()
    print(json.dumps(stats, indent=2))
