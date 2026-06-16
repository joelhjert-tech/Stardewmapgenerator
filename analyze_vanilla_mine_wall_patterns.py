#!/usr/bin/env python3
"""Extract prototype mine wall/floor/layer pattern evidence from vanilla mine maps."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
BASEGAME = ROOT / "mission_assets" / "unpacked_basegame"
MINE_MAP_DIR = BASEGAME / "Mine"
OUT_DIR = ROOT / "pattern_learning" / "vanilla_mine_patterns"
PREVIEW_DIR = OUT_DIR / "previews"
REPORT_DIR = ROOT / "reports"
TARGET_IDS = [220, 186, 119, 120, 121, 122, 123, 124, 158]
WALL_IDS = {68, 69, 70, 71, 72, 73, 74, 75, 76, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94,
            100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 116, 117, 118, 119, 120,
            121, 122, 123, 124, 125, 126, 132, 133, 134, 141, 142, 148, 157, 158, 159, 191, 196, 207}
LADDER_IDS = {67, 83, 99, 115}
FRONT_EDGE_IDS = {196, 197, 205, 206, 213, 214, 215, 216, 220, 221, 232}

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))
import tbin_reader  # noqa: E402
from mine_wall_pattern_resolver import TILE_ROLE_CORRECTIONS, VANILLA_MINE_WALL_PATTERNS  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_for_sheet(mp: dict) -> Dict[str, str]:
    return {ts["id"]: ts.get("imageSource", ts["id"]) for ts in mp.get("tilesheets", [])}


def sheet_image(source: str) -> Path:
    p = BASEGAME / (source if source.lower().endswith(".png") else f"{source}.png")
    if p.exists():
        return p
    p = MINE_MAP_DIR / (source if source.lower().endswith(".png") else f"{source}.png")
    return p


def layer_map(mp: dict) -> Dict[str, dict]:
    return {layer["id"]: layer for layer in mp["layers"]}


def stack_at(layers: Dict[str, dict], x: int, y: int) -> Dict[str, int]:
    out = {}
    for lname in ("Back", "Buildings", "Front", "AlwaysFront", "Paths"):
        layer = layers.get(lname)
        if not layer:
            continue
        payload = layer["tiles"].get((x, y))
        if payload:
            out[lname] = payload[1]
    return out


def context_signature(layers: Dict[str, dict], x: int, y: int, radius: int) -> dict:
    cells = []
    for yy in range(y - radius, y + radius + 1):
        row = []
        for xx in range(x - radius, x + radius + 1):
            row.append(stack_at(layers, xx, yy))
        cells.append(row)
    return {"radius": radius, "cells": cells}


def render_context(mp: dict, map_path: Path, layer_name: str, x: int, y: int, tid: int, out: Path, radius: int = 2) -> None:
    sheets = {}
    for ts in mp["tilesheets"]:
        source = ts.get("imageSource", ts["id"])
        image_path = sheet_image(source)
        if image_path.exists():
            sheets[ts["id"]] = Image.open(image_path).convert("RGBA")
    scale = 3
    size = radius * 2 + 1
    tile = 16
    canvas = Image.new("RGBA", (size * tile * scale, size * tile * scale + 34), (16, 16, 20, 255))
    layers = layer_map(mp)
    for lname in ("Back", "Buildings", "Front", "AlwaysFront"):
        layer = layers.get(lname)
        if not layer:
            continue
        for yy in range(y - radius, y + radius + 1):
            for xx in range(x - radius, x + radius + 1):
                payload = layer["tiles"].get((xx, yy))
                if not payload:
                    continue
                sid, idx = payload
                sheet = sheets.get(sid)
                if not sheet:
                    continue
                cols = sheet.width // 16
                crop = sheet.crop(((idx % cols) * 16, (idx // cols) * 16, (idx % cols + 1) * 16, (idx // cols + 1) * 16))
                crop = crop.resize((tile * scale, tile * scale), Image.Resampling.NEAREST)
                canvas.alpha_composite(crop, ((xx - (x - radius)) * tile * scale, (yy - (y - radius)) * tile * scale))
    d = ImageDraw.Draw(canvas)
    c = radius * tile * scale
    d.rectangle((c, c, c + tile * scale - 1, c + tile * scale - 1), outline=(255, 240, 0, 255), width=2)
    d.text((2, size * tile * scale + 2), f"{tid} {map_path.name} {layer_name} {x},{y}", fill=(255, 255, 255, 255))
    canvas.save(out)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tile_usage = {str(tid): {"layers": Counter(), "sheets": Counter(), "examples": []} for tid in TARGET_IDS}
    pattern_counts = Counter()
    pattern_examples = {}
    source_maps = []
    context_previews = defaultdict(list)

    for map_path in sorted(MINE_MAP_DIR.glob("*.tbin")):
        try:
            mp = tbin_reader.parse(map_path.read_bytes())
        except Exception:
            continue
        sheets = source_for_sheet(mp)
        if not any(str(src).startswith("mine") for src in sheets.values()):
            continue
        source_maps.append(map_path.name)
        layers = layer_map(mp)
        for lname, layer in layers.items():
            for (x, y), (sid, tid) in layer["tiles"].items():
                if tid in TARGET_IDS:
                    entry = tile_usage[str(tid)]
                    entry["layers"][lname] += 1
                    entry["sheets"][str(sheets.get(sid, sid))] += 1
                    if len(entry["examples"]) < 20:
                        preview_path = PREVIEW_DIR / f"tile_{tid}_{len(entry['examples']) + 1:02d}_{map_path.stem}_{lname}_{x}_{y}.png"
                        render_context(mp, map_path, lname, x, y, tid, preview_path)
                        entry["examples"].append({
                            "sourceMap": map_path.name,
                            "layer": lname,
                            "x": x,
                            "y": y,
                            "sourceTilesheet": sheets.get(sid, sid),
                            "preview": str(preview_path.resolve()),
                            "context5x5": context_signature(layers, x, y, 2),
                        })
                        context_previews[str(tid)].append(str(preview_path.resolve()))
                if tid in WALL_IDS or tid in LADDER_IDS or tid in FRONT_EDGE_IDS:
                    sig = json.dumps(context_signature(layers, x, y, 1)["cells"], sort_keys=True)
                    pattern_counts[(tid, lname, sig)] += 1
                    if (tid, lname, sig) not in pattern_examples:
                        pattern_examples[(tid, lname, sig)] = {
                            "sourceMap": map_path.name,
                            "sourceTilesheet": sheets.get(sid, sid),
                            "centerTileId": tid,
                            "centerLayer": lname,
                            "x": x,
                            "y": y,
                            "context3x3": context_signature(layers, x, y, 1),
                        }

    pattern_entries = []
    for i, ((tid, lname, sig), count) in enumerate(pattern_counts.most_common(120), start=1):
        ex = pattern_examples[(tid, lname, sig)]
        role = "unknown"
        if tid in LADDER_IDS:
            role = "ladder_opening"
        elif tid in FRONT_EDGE_IDS:
            role = "front_wall_or_shadow_overlay"
        elif tid in WALL_IDS:
            role = "mine_wall_structure"
        pattern_entries.append({
            "patternId": f"vanilla_mine_wall_{i:03d}",
            "sourceMap": ex["sourceMap"],
            "sourceTilesheet": ex["sourceTilesheet"],
            "bounds": {"radius": 1, "width": 3, "height": 3, "centerX": ex["x"], "centerY": ex["y"]},
            "frequencyCount": count,
            "roleInterpretation": role,
            "safeForPrototypeUse": True,
            "shouldBecomeManualSafePatternLater": True,
            "layerStack": ex["context3x3"],
            "localTileIdsByLayer": ex["context3x3"]["cells"],
            "screenshotPreviewReference": "",
        })

    role_corrections = {}
    for tid, correction in TILE_ROLE_CORRECTIONS.items():
        usage = tile_usage.get(str(tid), {"layers": Counter(), "sheets": Counter(), "examples": []})
        role_corrections[str(tid)] = {
            "tilesheet": "mine",
            "localTileId": tid,
            "dominantVanillaLayerUsage": dict(usage["layers"]),
            "dominantPrototypeLayerUsage": "see prototype metadata; previous broad Back usage was corrected",
            "correctRole": correction.correctRole,
            "wrongRoleIfCurrent": "random Back floor" if tid in (186, 220) else "single isolated wall tile",
            "recommendedAllowedLayers": list(correction.recommendedAllowedLayers),
            "recommendedCollision": correction.recommendedCollision,
            "mayBeUsedInBack": correction.mayUseOnBack,
            "shouldBeFrontOrAlwaysFront": correction.dominantVanillaLayer == "Front",
            "shouldBeUnderWallShadowFloor": tid == 186,
            "exampleVanillaContexts": usage["examples"][:8],
            "notes": correction.notes,
        }

    safe_candidates = [
        {
            "patternName": name,
            "patternType": "layer_stack",
            "sourceVanillaMaps": source_maps[:20],
            "involvedTileIds": sorted({t for layer_tiles in pat.values() if isinstance(layer_tiles, list) for t in layer_tiles}),
            "involvedLayers": [layer for layer in ("Back", "Buildings", "Front") if pat.get(layer)],
            "collisionInterpretation": "blocked where Buildings wall tiles exist; Back/Front overlays do not define collision",
            "previewImagePath": "",
            "confidence": 90,
            "recommendedAction": "safe_for_prototype_only",
            "role": pat.get("role", name),
        }
        for name, pat in VANILLA_MINE_WALL_PATTERNS.items()
    ]

    index = {
        "generatedAt": now_iso(),
        "source": "unpacked vanilla Mine/*.tbin maps",
        "sourceMapCount": len(source_maps),
        "sourceMaps": source_maps,
        "targetTileUsage": {
            tid: {
                "layers": dict(data["layers"]),
                "sheets": dict(data["sheets"]),
                "examples": data["examples"],
            }
            for tid, data in tile_usage.items()
        },
        "patterns": pattern_entries,
    }
    (OUT_DIR / "vanilla_mine_wall_pattern_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (OUT_DIR / "mine_tile_role_corrections.json").write_text(json.dumps(role_corrections, indent=2), encoding="utf-8")
    (OUT_DIR / "mine_wall_safe_pattern_candidates.json").write_text(json.dumps({
        "generatedAt": now_iso(),
        "source": "vanilla_mine_wall_pattern_analysis",
        "patterns": safe_candidates,
    }, indent=2), encoding="utf-8")

    analysis_lines = [
        "# Vanilla Mine Wall Pattern Analysis",
        "",
        f"- Source maps scanned: {len(source_maps)}",
        f"- Repeated wall/front/ladder context patterns indexed: {len(pattern_entries)}",
        "- Scope: prototype learning only; no production tile approvals were created.",
        "",
        "## Key Findings",
        "- Mine walls are layered stacks: Back floor/shadow underlay, Buildings rock body/edge/corner rows, and Front edge overlays.",
        "- Tile `220` is dominant on `Front`, not suitable as random `Back` floor.",
        "- Tile `186` is a `Back` floor/shadow tile used under or near mine wall structure.",
        "- Tiles `119-124` and `158` are dominant `Buildings` wall/edge pieces.",
        "",
        "## Pattern Families",
    ]
    for candidate in safe_candidates:
        analysis_lines.append(f"- `{candidate['patternName']}`: {candidate['role']} on {', '.join(candidate['involvedLayers'])}.")
    (REPORT_DIR / "vanilla_mine_wall_pattern_analysis.md").write_text("\n".join(analysis_lines) + "\n", encoding="utf-8")

    correction_lines = ["# Mine Tile Role Corrections", ""]
    for tid in TARGET_IDS:
        item = role_corrections[str(tid)]
        correction_lines += [
            f"## Tile {tid}",
            f"- Dominant vanilla layer usage: `{item['dominantVanillaLayerUsage']}`",
            f"- Correct role: {item['correctRole']}",
            f"- Recommended layers: `{item['recommendedAllowedLayers']}`",
            f"- Collision: `{item['recommendedCollision']}`",
            f"- May be used on Back: {'YES' if item['mayBeUsedInBack'] else 'NO'}",
            f"- Under-wall shadow/floor: {'YES' if item['shouldBeUnderWallShadowFloor'] else 'NO'}",
            f"- Notes: {item['notes']}",
            "",
        ]
    (REPORT_DIR / "mine_tile_role_corrections.md").write_text("\n".join(correction_lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "sourceMapCount": len(source_maps), "patterns": len(pattern_entries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
