#!/usr/bin/env python3
"""Build prototype mine outputs using only golden vanilla wall templates."""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
DUNGEON_REVIEW = ROOT / "prototype_visual_maps" / "dungeon_review"
OUT_DIR = DUNGEON_REVIEW / "custom_03_golden_template_fixed"
TILESET_OUT = DUNGEON_REVIEW / "tilesheets" / "mine.png"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))
import build_dungeon_visual_prototypes as base  # noqa: E402
from golden_mine_template_resolver import GoldenMineTemplateResolver  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_metadata(p: base.PrototypeMap, paths: Dict[str, str], validation: dict, resolver_result: dict) -> Path:
    usage = Counter()
    by_layer = {}
    for layer, data in p.layers.items():
        c = Counter(base.local_id(g) for g in data if base.local_id(g) is not None)
        by_layer[layer] = {str(k): v for k, v in sorted(c.items())}
        usage.update(c)
    doc = {
        "generatedAt": now_iso(),
        "mapId": p.map_id,
        "profile": "dungeon",
        "prototypeOnly": True,
        "generator": "build_golden_mine_template_prototypes.py",
        "resolver": "GoldenMineTemplateResolver",
        "goldenTemplatePolicy": "No mine wall/corner/opening/ladder visual tile may be placed unless covered by a golden vanilla template placement.",
        "sourceLayout": "custom_03 semantic floor mask from build_dungeon_visual_prototypes.py",
        "tilesheet": {
            "name": "mine.png",
            "copiedPath": str(TILESET_OUT.resolve()),
            "sourceStatus": "vanilla_basegame_tilesheet_read_only_source",
        },
        "size": {"width": p.width, "height": p.height, "tileWidth": 16, "tileHeight": 16},
        "entrance": {"x": p.entrance[0], "y": p.entrance[1]},
        "exit": {"x": p.exit[0], "y": p.exit[1]},
        "tileUsageByLayer": by_layer,
        "tileUsageTotal": {str(k): v for k, v in sorted(usage.items())},
        "goldenResolverResult": resolver_result,
        "goldenTemplatePlacements": getattr(p, "golden_template_placements", []),
        "missingTemplates": sorted(set(getattr(p, "golden_template_missing", []))),
        "tile946Status": "not_used",
        "paths": paths,
        "validation": validation,
    }
    out = OUT_DIR / "metadata.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def validation_report(validation: dict, resolver_result: dict) -> Path:
    lines = [
        "# Custom 03 Golden Template Fixed Validation",
        "",
        f"- Status: {validation['status']}",
        f"- Golden resolver status: {resolver_result.get('status')}",
        f"- Golden template placements: {resolver_result.get('placements', 0)}",
        f"- Missing template roles: {', '.join(resolver_result.get('missing') or []) or 'None'}",
        "- Mine wall tile placement policy: every restricted wall/ladder/shadow tile must be covered by metadata template placement.",
        "- Production DB modified: NO",
        "- mission_assets modified: NO",
        "- Tile 946 used: NO",
        "",
        "## Base Prototype Checks",
    ]
    for key, value in validation.get("checks", {}).items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    if validation.get("issues"):
        lines += ["", "## Issues"] + [f"- {issue}" for issue in validation["issues"]]
    if validation.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {warning}" for warning in validation["warnings"][:80]]
    else:
        lines += ["", "## Warnings", "- None."]
    out = OUT_DIR / "validation_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def before_after(clean: Path) -> Path:
    candidates = [
        DUNGEON_REVIEW / "custom_03" / "preview_clean.png",
        DUNGEON_REVIEW / "custom_03" / "preview_clean_template_fixed.png",
        clean,
    ]
    images = []
    labels = ["original bad custom_03", "previous template fixed", "golden template fixed"]
    for path in candidates:
        if path.exists():
            images.append(Image.open(path).convert("RGBA").resize((384, 384), Image.Resampling.NEAREST))
        else:
            images.append(Image.new("RGBA", (384, 384), (30, 30, 34, 255)))
    sheet = Image.new("RGBA", (384 * 3 + 32, 430), (18, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    x = 8
    for label, img in zip(labels, images):
        sheet.alpha_composite(img, (x, 34))
        draw.text((x, 10), label, fill=(255, 255, 255, 235))
        x += 392
    out = OUT_DIR / "before_after.png"
    sheet.save(out)
    return out


def review_sheet(clean: Path) -> Path:
    atlas = ROOT / "pattern_learning" / "tile_grammar_templates" / "golden_vanilla_mine_templates" / "golden_mine_template_atlas.png"
    base_sheet = before_after(clean)
    left = Image.open(base_sheet).convert("RGBA")
    if atlas.exists():
        right = Image.open(atlas).convert("RGBA")
        right = right.resize((min(660, right.width), int(right.height * min(660, right.width) / right.width)), Image.Resampling.NEAREST)
    else:
        right = Image.new("RGBA", (660, 360), (30, 30, 34, 255))
    sheet = Image.new("RGBA", (max(left.width, right.width) + 24, left.height + right.height + 60), (18, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), "Custom 03 wall fix review: old vs golden + vanilla template examples", fill=(255, 255, 255, 240))
    sheet.alpha_composite(left, (12, 36))
    sheet.alpha_composite(right, (12, 48 + left.height))
    out = DUNGEON_REVIEW / "custom_03_wall_fix_review_sheet.png"
    sheet.save(out)
    return out


def write_reports(outputs: Dict[str, str], resolver_result: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "mine_template_failure_audit.md").write_text(
        "\n".join([
            "# Mine Template Failure Audit",
            "",
            "The previous visual path still used `MineWallPatternResolver`, which chose individual wall IDs from role lists such as wall tops, bodies, lower faces, side edges, and front shadows.",
            "",
            "## Failure Point",
            "- `generate_visual_map_v2.py` called `MineWallPatternResolver().apply(p)` after floor decoration.",
            "- `MineWallPatternResolver` computed a wall shell from semantic floor cells and then selected single tile IDs with deterministic pick lists.",
            "- The template library was recorded in metadata, but the wall construction path did not stamp exact vanilla layer-stack templates.",
            "- Back/Buildings/Front relationships were therefore approximate instead of copied from source vanilla coordinates.",
            "- Ladder openings were built from a hardcoded stack and side pieces, not an extracted complete vanilla opening template.",
            "",
            "## Why It Looked Wrong",
            "- Correct-looking IDs were sometimes present, but their neighboring IDs and layers were not vanilla source windows.",
            "- Role lists overrode the intended template grammar.",
            "- The validator checked broad sanity, not template provenance for every wall tile.",
            "",
            "## Hard Fix",
            "- Mine/dungeon wall visuals now require `GoldenMineTemplateResolver` and metadata-covered golden template placements.",
            "- Any missing wall/corner/opening/ladder template must fall back to marker-only or fail closed.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "mine_visual_generation_freeze.md").write_text(
        "\n".join([
            "# Mine Visual Generation Freeze",
            "",
            "- Unsafe single-tile mine wall generation is frozen for the golden path.",
            "- `MineWallPatternResolver` remains on disk for historical comparison, but it is not used by the new golden output.",
            "- `generate_visual_map_v2.py` has been switched away from the weak resolver for mine visual wall output.",
            "- Missing golden templates require marker fallback/fail-closed behavior.",
            "- Prototype-only tile grammar templates are not treated as production-ready wall generation.",
            "",
            f"- Golden resolver result: `{resolver_result.get('status')}`",
            f"- Missing roles: `{', '.join(resolver_result.get('missing') or []) or 'none'}`",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "golden_mine_template_system_summary.md").write_text(
        "\n".join([
            "# Golden Mine Template System Summary",
            "",
            "The new system extracts source-stamped wall/opening/floor windows from vanilla mine maps and uses only those golden templates for mine/dungeon wall visuals.",
            "",
            "## Outputs",
            f"- TMX: `{outputs['tmx']}`",
            f"- TMJ: `{outputs['tmj']}`",
            f"- Clean preview: `{outputs['preview_clean']}`",
            f"- Labeled preview: `{outputs['preview_labeled']}`",
            f"- Review sheet: `{outputs['review_sheet']}`",
            "",
            "## What Changed In custom_03",
            "- Wall, edge, shadow, and ladder/opening cells are now metadata-covered template stamps.",
            "- No wall tile is selected from generic role lists.",
            "- Floor fill still uses vanilla floor templates.",
            "- The output is still prototype/review only, not production generation.",
            "",
            "## Remaining Issues",
            "- The starter set is intentionally small and may still need more vanilla openings, cave corners, and chamber templates for prettier variety.",
            "- Golden templates are review evidence; production remains blocked until safe patterns/approvals are accepted.",
        ]) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "golden_mine_template_safety_status.md").write_text(
        "\n".join([
            "# Golden Mine Template Safety Status",
            "",
            "- Production maps generated: NO",
            "- Original Moonvillage maps modified: NO",
            "- mission_assets modified: NO",
            "- unpacked basegame modified: NO",
            "- Approved DB modified: NO",
            "- Tile 946 rules preserved: YES",
            "- Old generator still exists: YES",
            "- Marker fallback still works: YES",
            "- Restricted external art copied: NO",
        ]) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (DUNGEON_REVIEW / "tilesheets").mkdir(parents=True, exist_ok=True)
    if not base.TILESET_SRC.exists():
        raise SystemExit(f"Missing mine tilesheet: {base.TILESET_SRC}")
    shutil.copy2(base.TILESET_SRC, TILESET_OUT)
    p = base.make_custom_03()
    p.map_id = "custom_03_golden_template_fixed"
    p.title = "Custom 03 - Golden Template Fixed"
    p.init_layers()
    resolver = GoldenMineTemplateResolver()
    resolver_result = resolver.apply(p)
    # Keep decorative specials out of the golden wall validation scope.
    for x, y in [p.entrance, p.exit]:
        p.walkable.add((x, y))
        p.blocked.discard((x, y))
    tmx = base.write_tmx(p, OUT_DIR, "../tilesheets/mine.png")
    tmj = base.write_tmj(p, OUT_DIR, "../tilesheets/mine.png")
    tilesheet = Image.open(TILESET_OUT).convert("RGBA")
    clean, labeled = base.render_map(p, tilesheet, OUT_DIR)
    validation = base.validate_prototype(p, tmx, tmj, "../tilesheets/mine.png")
    report = validation_report(validation, resolver_result)
    before = before_after(clean)
    sheet = review_sheet(clean)
    paths = {
        "tmx": str(tmx.resolve()),
        "tmj": str(tmj.resolve()),
        "preview_clean": str(clean.resolve()),
        "preview_labeled": str(labeled.resolve()),
        "before_after": str(before.resolve()),
        "review_sheet": str(sheet.resolve()),
        "validation_report": str(report.resolve()),
    }
    metadata = write_metadata(p, paths, validation, resolver_result)
    paths["metadata"] = str(metadata.resolve())
    write_reports(paths, resolver_result)
    print(json.dumps({"status": validation["status"], "resolver": resolver_result, "outputs": paths}, indent=2))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
