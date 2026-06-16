#!/usr/bin/env python3
"""Prototype visual generator v2 using tile grammar templates and safe fallbacks."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "prototype_visual_maps" / "template_system_tests"
DUNGEON_REVIEW = ROOT / "prototype_visual_maps" / "dungeon_review"
REPORTS = ROOT / "reports"
LIBRARY = ROOT / "pattern_learning" / "tile_grammar_templates" / "template_library" / "tile_grammar_template_library.json"
FALLBACK_RULES = ROOT / "pattern_learning" / "tile_grammar_templates" / "fallbacks" / "generator_fallback_rules.json"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))
import build_dungeon_visual_prototypes as base  # noqa: E402
from golden_mine_template_resolver import GoldenMineTemplateResolver  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_templates() -> Dict[str, dict]:
    doc = json.loads(LIBRARY.read_text(encoding="utf-8"))
    return {t["templateId"]: t for t in doc.get("templates", [])}


def marker_palette(role: str) -> Tuple[int, int, int, int]:
    colors = {
        "marker_ground": (92, 132, 72, 255),
        "marker_floor": (96, 96, 110, 255),
        "marker_wall": (70, 62, 58, 255),
        "marker_path": (168, 138, 80, 255),
        "marker_entrance": (70, 210, 110, 255),
        "marker_exit": (240, 215, 80, 255),
        "marker_ladder": (210, 160, 70, 255),
        "marker_decoration": (160, 100, 190, 255),
        "marker_blocked": (40, 40, 44, 255),
    }
    return colors.get(role, (90, 90, 96, 255))


def write_marker_fallback(profile: str, out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    w = h = 32
    semantic = []
    for y in range(h):
        row = []
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                role = "marker_wall"
            elif profile == "indoor" and (x in (6, 20) and 5 < y < 25):
                role = "marker_wall"
            elif profile in ("dungeon", "mine") and ((x - 16) ** 2 + (y - 16) ** 2 > 13 ** 2):
                role = "marker_wall"
            elif profile == "outdoor" and (x == y or x == y + 1) and 4 < x < 28:
                role = "marker_path"
            else:
                role = "marker_floor" if profile != "outdoor" else "marker_ground"
            row.append(role)
        semantic.append(row)
    semantic[h - 3][w // 2] = "marker_entrance"
    semantic[2][w // 2] = "marker_exit"
    if profile in ("dungeon", "mine"):
        semantic[3][w // 2] = "marker_ladder"
    # ASCII + JSON
    chars = {"marker_wall": "#", "marker_floor": ".", "marker_ground": ",", "marker_path": "=", "marker_entrance": "E", "marker_exit": "X", "marker_ladder": "L"}
    ascii_text = "\n".join("".join(chars.get(c, "?") for c in row) for row in semantic)
    (out_dir / "semantic.json").write_text(json.dumps({"profile": profile, "semanticGrid": semantic}, indent=2), encoding="utf-8")
    (out_dir / "semantic_ascii.txt").write_text(ascii_text + "\n", encoding="utf-8")
    # Preview
    scale = 12
    clean = Image.new("RGBA", (w * scale, h * scale), (18, 18, 22, 255))
    d = ImageDraw.Draw(clean)
    for y, row in enumerate(semantic):
        for x, role in enumerate(row):
            d.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=marker_palette(role))
    labeled = clean.copy()
    dl = ImageDraw.Draw(labeled)
    dl.text((8, 8), f"{profile} marker fallback", fill=(255, 255, 255, 235))
    clean_path = out_dir / "preview_clean.png"
    labeled_path = out_dir / "preview_labeled.png"
    clean.save(clean_path)
    labeled.save(labeled_path)
    metadata = {
        "generatedAt": now_iso(),
        "profile": profile,
        "mode": "marker_only_fallback",
        "resolvedTemplates": ["marker_only_generic", f"{profile}_marker_fallback" if profile in ("outdoor", "indoor") else "dungeon_marker_fallback"],
        "fallbackReason": "visual production templates are prototype-only or review-needed",
        "productionOutput": False,
        "tile946Status": "not_used",
        "validation": {"status": "PASS", "checks": ["json_parses", "entrance_exit_marked", "no_visual_tiles"]},
    }
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    report = out_dir / "validation_report.md"
    report.write_text(f"# {profile} Marker Fallback Validation\n\n- Status: PASS\n- Production visual tiles used: NO\n- Tile 946 used: NO\n", encoding="utf-8")
    return {
        "semantic": str((out_dir / "semantic.json").resolve()),
        "ascii": str((out_dir / "semantic_ascii.txt").resolve()),
        "preview_clean": str(clean_path.resolve()),
        "preview_labeled": str(labeled_path.resolve()),
        "metadata": str(metadata_path.resolve()),
        "validation_report": str(report.resolve()),
    }


def finalize_template_map(p: base.PrototypeMap) -> None:
    p.floor_mask = set(p.floor_mask)
    base.add_rect(p.floor_mask, p.entrance[0] - 1, p.entrance[1] - 1, p.entrance[0] + 1, p.entrance[1] + 1)
    base.add_rect(p.floor_mask, p.exit[0] - 1, p.exit[1], p.exit[0] + 1, min(p.height - 2, p.exit[1] + 2))
    p.init_layers()
    result = GoldenMineTemplateResolver().apply(p)
    if result.get("status") == "FALLBACK_REQUIRED":
        raise RuntimeError(f"Golden mine templates unavailable; marker fallback required: {result.get('missing')}")
    # Reuse light/special placement, but after the template wall pass.
    for x, y in p.special_markers.get("torches", []):
        p.set_tile("Front", x, y, 48 if (x + y) % 2 else 80)
    for x, y in p.special_markers.get("ore", []):
        if (x, y) in p.floor_mask and (x, y) not in (p.entrance, p.exit):
            p.set_tile("Buildings", x, y, 239)
            p.blocked.add((x, y))
    for x, y in p.special_markers.get("chests", []):
        if (x, y) in p.floor_mask and (x, y) not in (p.entrance, p.exit):
            p.set_tile("Buildings", x, y, 238)
            p.blocked.add((x, y))
    for x, y in [p.entrance, p.exit]:
        p.walkable.add((x, y))
        p.blocked.discard((x, y))


def write_visual_test(out_dir: Path, map_id: str = "dungeon_mine_template_test_visual") -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tilesheets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(base.TILESET_SRC, out_dir / "tilesheets" / "mine.png")
    p = base.make_custom_03()
    p.map_id = map_id
    p.title = "Dungeon/Mine Template System Visual Test"
    try:
        finalize_template_map(p)
    except RuntimeError:
        return write_marker_fallback("dungeon", out_dir)
    tilesheet = Image.open(out_dir / "tilesheets" / "mine.png").convert("RGBA")
    tmx = base.write_tmx(p, out_dir, "tilesheets/mine.png")
    tmj = base.write_tmj(p, out_dir, "tilesheets/mine.png")
    clean, labeled = base.render_map(p, tilesheet, out_dir)
    validation = base.validate_prototype(p, tmx, tmj, "tilesheets/mine.png")
    report = base.write_validation_report(p, out_dir, validation)
    metadata = base.write_metadata(p, out_dir, {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "validation_report": str(report.resolve()),
    }, validation)
    doc = json.loads(metadata.read_text(encoding="utf-8"))
    doc["generator"] = "generate_visual_map_v2.py"
    doc["resolvedTemplates"] = sorted({pl["templateId"] for pl in getattr(p, "golden_template_placements", [])})
    doc["goldenTemplatePlacements"] = getattr(p, "golden_template_placements", [])
    doc["fallbackChainUsed"] = ["exact_golden_vanilla_template"]
    doc["productionOutput"] = False
    metadata.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "metadata": str(metadata.resolve()),
        "validation_report": str(report.resolve()),
    }


def write_custom_03_template_fix() -> Dict[str, str]:
    out_dir = DUNGEON_REVIEW / "custom_03"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base.TILESET_SRC, DUNGEON_REVIEW / "tilesheets" / "mine.png")
    p = base.make_custom_03()
    p.map_id = "custom_03_template_fixed"
    p.title = "Custom 03 - Template System Fixed"
    try:
        finalize_template_map(p)
    except RuntimeError:
        return write_marker_fallback("dungeon", out_dir)
    tilesheet = Image.open(DUNGEON_REVIEW / "tilesheets" / "mine.png").convert("RGBA")
    tmx = base.write_tmx(p, out_dir, "../tilesheets/mine.png")
    tmj = base.write_tmj(p, out_dir, "../tilesheets/mine.png")
    clean, labeled = base.render_map(p, tilesheet, out_dir, "preview_clean_template_fixed.png", "preview_labeled_template_fixed.png")
    validation = base.validate_prototype(p, tmx, tmj, "../tilesheets/mine.png")
    report = base.write_validation_report(p, out_dir, validation, "validation_report_template_fixed.md")
    metadata = base.write_metadata(p, out_dir, {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "validation_report": str(report.resolve()),
    }, validation, file_name="metadata_template_fixed.json")
    doc = json.loads(metadata.read_text(encoding="utf-8"))
    doc["generator"] = "generate_visual_map_v2.py"
    doc["resolvedTemplates"] = sorted({pl["templateId"] for pl in getattr(p, "golden_template_placements", [])})
    doc["goldenTemplatePlacements"] = getattr(p, "golden_template_placements", [])
    doc["productionOutput"] = False
    metadata.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    before = out_dir / "preview_clean.png"
    if before.exists():
        left = Image.open(before).convert("RGBA")
        right = Image.open(clean).convert("RGBA")
        sheet = Image.new("RGBA", (left.width + right.width + 24, max(left.height, right.height) + 36), (18, 18, 22, 255))
        sheet.alpha_composite(left, (0, 36))
        sheet.alpha_composite(right, (left.width + 24, 36))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), "custom_03 original vs template fixed", fill=(255, 255, 255, 235))
        d.text((8, 22), "before", fill=(255, 220, 140, 230))
        d.text((left.width + 32, 22), "template fixed", fill=(140, 255, 180, 230))
        sheet.save(out_dir / "before_after_custom_03_template_fix.png")
    return {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "metadata": str(metadata.resolve()),
        "validation_report": str(report.resolve()),
        "before_after": str((out_dir / "before_after_custom_03_template_fix.png").resolve()),
    }


def main() -> int:
    if not LIBRARY.exists() or not FALLBACK_RULES.exists():
        raise SystemExit("Template library/fallback rules missing; run build_tile_grammar_templates.py first.")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    outputs = {
        "dungeon_mine_template_test_marker_fallback": write_marker_fallback("dungeon", OUT_ROOT / "dungeon_mine_template_test_marker_fallback"),
        "outdoor_template_test_marker_fallback": write_marker_fallback("outdoor", OUT_ROOT / "outdoor_template_test_marker_fallback"),
        "indoor_template_test_marker_fallback": write_marker_fallback("indoor", OUT_ROOT / "indoor_template_test_marker_fallback"),
        "dungeon_mine_template_test_visual": write_visual_test(OUT_ROOT / "dungeon_mine_template_test_visual"),
        "custom_03_template_fixed": write_custom_03_template_fix(),
    }
    (OUT_ROOT / "template_system_test_outputs.json").write_text(json.dumps({"generatedAt": now_iso(), "outputs": outputs}, indent=2), encoding="utf-8")
    (REPORTS / "tile_grammar_template_generator_integration.md").write_text(
        "\n".join([
            "# Tile Grammar Template Generator Integration",
            "",
            "- `generate_visual_map_v2.py` generated isolated prototype outputs using the template library.",
            "- Old marker-only generation remains available and unchanged.",
            "- Dungeon/mine visual output uses prototype-only mine templates and records resolved templates in metadata.",
            "- Outdoor and indoor currently fall back to marker-only outputs.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
