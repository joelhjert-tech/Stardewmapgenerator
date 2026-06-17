#!/usr/bin/env python3
"""Generate custom_09_front_promotion_checkpoint.

Re-runs the UPDATED Smart Edge-Wrapper v2 (ranked template selection + relaxed
structural guard for real-Front templates + wall_body->wall_top remap) into a NEW
directory so custom_08 is preserved untouched. Measures the new frontToBuildingsRatio.

Prototype/review only. Reuses the proven base generator + the updated wrapper. No
production maps, no mission_assets/unpacked_basegame edits, no approved-DB writes,
no loose single-tile placement (Front comes only from complete templates), tile 946
unaffected.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))

import build_smart_edge_wrapper_v2 as w  # noqa: E402
import build_dungeon_visual_prototypes as base  # noqa: E402

OUT_DIR = w.OUT_ROOT / "custom_09_front_promotion_checkpoint"
CUSTOM08_PREVIEW = w.OUT_ROOT / "custom_08_fresh_template_test" / "preview_clean.png"


def front_layer_overlay(p, out_dir: Path) -> Path:
    scale = 8
    img = Image.new("RGBA", (p.width * scale, p.height * scale), (16, 16, 20, 255))
    d = ImageDraw.Draw(img)
    for y in range(p.height):
        for x in range(p.width):
            g = p.layers["Front"][p.idx(x, y)] if hasattr(p, "idx") else None
            lid = base.local_id(g) if g is not None else None
            if lid is not None and lid not in w.VOID_IDS:
                d.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1),
                            fill=(240, 200, 90, 255))
    out = out_dir / "front_layer_overlay.png"
    img.save(out)
    return out


def before_after(custom09_preview: Path, out_dir: Path) -> Path:
    b = Image.open(custom09_preview).convert("RGBA")
    if CUSTOM08_PREVIEW.exists():
        a = Image.open(CUSTOM08_PREVIEW).convert("RGBA")
    else:
        a = Image.new("RGBA", b.size, (18, 18, 22, 255))
    sheet = Image.new("RGBA", (a.width + b.width + 24, max(a.height, b.height) + 20), (18, 18, 22, 255))
    sheet.alpha_composite(a, (0, 20))
    sheet.alpha_composite(b, (a.width + 24, 20))
    dd = ImageDraw.Draw(sheet)
    dd.text((10, 4), "custom_08 (front=torches only)", fill=(255, 255, 255, 230))
    dd.text((a.width + 34, 4), "custom_09 front promotion checkpoint", fill=(255, 255, 255, 230))
    out = out_dir / "before_after_custom_08_vs_custom_09_checkpoint.png"
    sheet.save(out)
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (w.OUT_ROOT / "tilesheets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(base.TILESET_SRC, w.TILESET_OUT)

    # Redirect the wrapper module's output-dir globals so its helper writers target custom_09.
    w.OUT_DIR = OUT_DIR

    p = w.make_custom_08()
    p.map_id = "custom_09_front_promotion_checkpoint"
    p.title = "Custom 09 - Front Promotion Checkpoint"

    wrapper = w.FreshTemplateWrapper()
    result = wrapper.apply(p)

    tmx = base.write_tmx(p, OUT_DIR, "../tilesheets/mine.png")
    tmj = base.write_tmj(p, OUT_DIR, "../tilesheets/mine.png")
    tilesheet = Image.open(w.TILESET_OUT).convert("RGBA")
    clean, labeled = base.render_map(p, tilesheet, OUT_DIR)
    debug_paths = w.write_debug(wrapper)
    overlay_paths = w.draw_overlays(p, wrapper)
    fol = front_layer_overlay(p, OUT_DIR)
    ba = before_after(clean, OUT_DIR)
    validation = base.validate_prototype(p, tmx, tmj, "../tilesheets/mine.png")
    validation_report = base.write_validation_report(p, OUT_DIR, validation, "validation_report.md")

    paths = {
        "tmx": str(tmx.resolve()), "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()), "preview_labeled": str(labeled.resolve()),
        "front_layer_overlay": str(fol.resolve()),
        "template_overlay": str(overlay_paths["template_overlay"].resolve()),
        "before_after_custom_08_vs_custom_09_checkpoint": str(ba.resolve()),
        "validation_report": str(validation_report.resolve()),
        "template_placement_debug": str(debug_paths["placements"].resolve()),
    }
    metadata = w.write_metadata(p, wrapper, result, validation, paths)
    paths["metadata"] = str(metadata.resolve())

    print(json.dumps({
        "status": validation["status"],
        "frontToBuildingsRatio": round(result["frontToBuildingsRatio"], 4),
        "frontTiles": result["frontTiles"],
        "buildingsTiles": result["buildingsTiles"],
        "frontCellsWritten": result.get("frontCellsWritten"),
        "frontBearingTemplatesUsed": result.get("frontBearingTemplatesUsed"),
        "skippedFrontBearing": len(result.get("skippedFrontBearing", [])),
        "fallbackCount": result["fallbackCount"],
        "outDir": str(OUT_DIR.resolve()),
    }, indent=2))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
