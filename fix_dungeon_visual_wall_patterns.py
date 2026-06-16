#!/usr/bin/env python3
"""Regenerate dungeon visual prototypes with vanilla-like mine wall patterns."""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "prototype_visual_maps" / "dungeon_review"
REPORTS = ROOT / "reports"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))
import build_dungeon_visual_prototypes as base  # noqa: E402
from mine_wall_pattern_resolver import TILE_ROLE_CORRECTIONS, VANILLA_MINE_WALL_PATTERNS, MineWallPatternResolver  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_aprons(p: base.PrototypeMap) -> None:
    ex, ey = p.entrance
    base.add_rect(p.floor_mask, ex - 1, ey - 1, ex + 1, ey + 1)
    lx, ly = p.exit
    base.add_rect(p.floor_mask, lx - 1, ly, lx + 1, min(p.height - 2, ly + 2))


def place_fixed_specials(p: base.PrototypeMap) -> None:
    ex, ey = p.entrance
    for y in range(ey - 1, ey + 2):
        for x in range(ex - 1, ex + 2):
            if 0 <= x < p.width and 0 <= y < p.height:
                p.walkable.add((x, y))
                p.blocked.discard((x, y))
                p.set_tile("Back", x, y, base.hpick(base.EARTH_FLOORS, x, y, p.seed))
    for x, y in p.special_markers.get("torches", []):
        if 0 <= x < p.width and 0 <= y < p.height and (x, y) not in p.floor_mask:
            p.set_tile("Front", x, y, 48 if (x + y) % 2 else 80)
        elif 0 <= x < p.width and 0 <= y < p.height:
            p.set_tile("Front", x, y, 48 if (x + y) % 2 else 80)
    for x, y in p.special_markers.get("ore", []):
        if (x, y) in p.floor_mask and (x, y) not in (p.entrance, p.exit):
            p.set_tile("Buildings", x, y, 239)
            p.blocked.add((x, y))
    for x, y in p.special_markers.get("chests", []):
        if (x, y) in p.floor_mask and (x, y) not in (p.entrance, p.exit):
            p.set_tile("Buildings", x, y, 238)
            p.blocked.add((x, y))
    for x, y in p.special_markers.get("wood", []):
        if 0 <= x < p.width and 0 <= y < p.height:
            p.set_tile("Buildings", x, y, base.hpick([20, 21, 22, 36, 37, 38], x, y, p.seed))
            p.blocked.add((x, y))


def collect_roles(p: base.PrototypeMap) -> None:
    p.provisional_roles = []
    used = set()
    for layer, data in p.layers.items():
        for g in data:
            tid = base.local_id(g)
            if tid is None:
                continue
            role = base.TILE_ROLES.get(tid)
            if role and (tid, layer) not in used:
                # Keep the observed layer, because some tile IDs appear in more
                # than one layer context in vanilla.
                p.provisional_roles.append(base.TileRole(tid, role.role, layer, role.collision, role.reason, role.confidence))
                used.add((tid, layer))


def finalize_fixed_map(p: base.PrototypeMap) -> None:
    add_aprons(p)
    p.init_layers()
    base.decorate_floor(p)
    resolver = MineWallPatternResolver()
    resolver.apply(p)
    place_fixed_specials(p)
    for x, y in [p.entrance, p.exit]:
        p.walkable.add((x, y))
        p.blocked.discard((x, y))
    collect_roles(p)


def write_fixed_metadata(p: base.PrototypeMap, out_dir: Path, paths: Dict[str, str], validation: Dict) -> Path:
    metadata = base.write_metadata(p, out_dir, paths, validation, file_name="metadata_fixed.json")
    doc = json.loads(metadata.read_text(encoding="utf-8"))
    doc["wallPatternResolver"] = {
        "resolver": "prototypes/mine_wall_pattern_resolver.py",
        "patternSource": "pattern_learning/vanilla_mine_patterns/vanilla_mine_wall_pattern_index.json",
        "tileRoleCorrectionSource": "pattern_learning/vanilla_mine_patterns/mine_tile_role_corrections.json",
        "prototypeOnly": True,
        "rules": {
            "tile220": "Front overlay only; not random Back floor",
            "tile186": "Back under-wall/shadow floor only",
            "tiles119To124And158": "Buildings cave wall/edge stack only",
        },
    }
    metadata.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return metadata


def make_before_after(before: Path, after: Path, out: Path, title: str) -> None:
    left = Image.open(before).convert("RGBA")
    right = Image.open(after).convert("RGBA")
    w = left.width + right.width + 24
    h = max(left.height, right.height) + 36
    sheet = Image.new("RGBA", (w, h), (18, 18, 22, 255))
    sheet.alpha_composite(left, (0, 36))
    sheet.alpha_composite(right, (left.width + 24, 36))
    d = ImageDraw.Draw(sheet)
    d.text((8, 8), title, fill=(255, 255, 255, 240))
    d.text((8, 22), "before", fill=(255, 220, 140, 230))
    d.text((left.width + 32, 22), "fixed", fill=(140, 255, 180, 230))
    sheet.save(out)


def make_contact_sheet(outputs: Dict[str, Dict[str, str]]) -> Path:
    entries = [
        ("custom_03 original", OUT_ROOT / "custom_03" / "preview_clean.png"),
        ("custom_03 fixed", Path(outputs["custom_03"]["preview_clean_fixed"])),
        ("remake_01 fixed", Path(outputs["remake_01"]["preview_clean_fixed"])),
        ("remake_02 fixed", Path(outputs["remake_02"]["preview_clean_fixed"])),
    ]
    vanilla_preview_dir = ROOT / "pattern_learning" / "vanilla_mine_patterns" / "previews"
    for tile_id in (220, 186, 121, 158):
        candidates = sorted(vanilla_preview_dir.glob(f"tile_{tile_id}_*.png"))
        if candidates:
            entries.append((f"vanilla tile {tile_id} context", candidates[0]))
    thumbs = []
    for label, path in entries:
        img = Image.open(path).convert("RGBA")
        max_w = 360
        if img.width > max_w:
            scale = max_w / img.width
            img = img.resize((max_w, int(img.height * scale)), Image.Resampling.NEAREST)
        thumbs.append((label, img))
    cols = 2
    pad = 16
    cell_w = max(img.width for _, img in thumbs) + pad
    cell_h = max(img.height for _, img in thumbs) + 42
    sheet = Image.new("RGBA", (cols * cell_w + pad, ((len(thumbs) + cols - 1) // cols) * cell_h + pad), (18, 18, 22, 255))
    d = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(thumbs):
        x = pad + (i % cols) * cell_w
        y = pad + (i // cols) * cell_h
        d.text((x, y), label, fill=(255, 255, 255, 235))
        sheet.alpha_composite(img, (x, y + 24))
    out = OUT_ROOT / "mine_wall_fix_contact_sheet.png"
    sheet.save(out)
    return out


def write_reports(outputs: Dict[str, Dict[str, str]], validations: Dict[str, Dict]) -> None:
    summary = [
        "# Dungeon Visual Wall Fix Summary",
        "",
        "## What Was Wrong",
        "- The first visual prototype placed mine wall tiles one cell at a time, which produced noisy wall edges instead of vanilla mine wall stacks.",
        "- Tile `220` was available to Back-floor detail generation even though vanilla mine data uses it almost entirely on Front.",
        "- Tile `186` was used as random floor variation, but vanilla contexts show it belongs under/near wall structures as a Back shadow/floor tile.",
        "",
        "## Vanilla Maps Analyzed",
        "- All unpacked vanilla `mission_assets/unpacked_basegame/Mine/*.tbin` files were scanned read-only.",
        "- The fixed resolver focuses on the vanilla `mine` tilesheet family and repeated wall/ladder/front-edge contexts.",
        "",
        "## Patterns Learned",
        "- `wall_top_row`: Buildings `69,70,73,74,75,76,93,94`.",
        "- `wall_body_row`: Buildings `85,86,89,90,101,102,105,106,107,108,117,118,133,134`.",
        "- `wall_lower_face_row`: Buildings `119,120,121,122,123,124,157,158`.",
        "- `floor_under_wall_shadow`: Back `186` plus Front `213,214,215,216,220` where appropriate.",
        "- `ladder_opening`: Buildings `67,83,99,115` anchored into surrounding wall pieces.",
        "",
        "## Tile Conclusions",
        "- Tile `220`: Front wall/side overlay. Removed from Back floor generation.",
        "- Tile `186`: Back under-wall/shadow floor. Removed from random broad floor generation and used only at wall-adjacent floor cells.",
        "- Tiles `119-124` and `158`: Buildings wall/edge pieces. Used as part of lower wall-face stacks, not isolated random walls.",
        "",
        "## Fixed Outputs",
    ]
    for map_id in ("custom_03", "remake_01", "remake_02"):
        v = validations[map_id]
        summary += [
            f"### {map_id}",
            f"- Fixed TMX: `{outputs[map_id]['tmx_fixed']}`",
            f"- Fixed preview: `{outputs[map_id]['preview_clean_fixed']}`",
            f"- Validation: {v['status']}",
            "",
        ]
    summary += [
        "## Remaining Issues",
        "- These are still prototype-only visual outputs. The learned wall stacks should be reviewed and promoted as manual safe patterns before production generation.",
        "- The fixed resolver is intentionally conservative and vanilla-mine-specific; desert/lava/frost mine variants should get separate palette-specific pattern tables later.",
        "",
        "## Next Recommended Manual Safe-Pattern Approvals",
        "- Mine wall top/body/lower-face 3-row stack.",
        "- Floor-under-wall shadow stack using Back `186` and Front edge overlays.",
        "- Ladder opening stack `67/83/99/115` with side caps.",
    ]
    (REPORTS / "dungeon_visual_wall_fix_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    safety = [
        "# Dungeon Visual Wall Fix Safety Status",
        "",
        "- Production maps generated: NO.",
        "- Original Moonvillage maps modified: NO.",
        "- mission_assets modified: NO; vanilla mine maps and tilesheets were read-only sources.",
        "- unpacked basegame modified: NO.",
        "- Approved production DB modified: NO.",
        "- Tile 946 rules preserved: YES; tile 946 is not used by these mine prototypes.",
        "- Only prototype outputs under `tools/tiled-map-assistant/prototype_visual_maps/dungeon_review/` and reports/pattern-learning files were written.",
    ]
    (REPORTS / "dungeon_visual_wall_fix_safety_status.md").write_text("\n".join(safety) + "\n", encoding="utf-8")


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "tilesheets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(base.TILESET_SRC, OUT_ROOT / "tilesheets" / "mine.png")
    tilesheet = Image.open(OUT_ROOT / "tilesheets" / "mine.png").convert("RGBA")

    factories = {
        "remake_01": base.make_remake_01,
        "remake_02": base.make_remake_02,
        "custom_03": base.make_custom_03,
    }
    outputs: Dict[str, Dict[str, str]] = {}
    validations: Dict[str, Dict] = {}
    for map_id, factory in factories.items():
        p = factory()
        original_id = p.map_id
        p.map_id = f"{original_id}_fixed"
        p.title = f"{p.title} (Fixed Wall Pattern Pass)"
        finalize_fixed_map(p)
        out_dir = OUT_ROOT / original_id
        out_dir.mkdir(parents=True, exist_ok=True)
        tilesheet_rel = "../tilesheets/mine.png"
        tmx = base.write_tmx(p, out_dir, tilesheet_rel)
        tmj = base.write_tmj(p, out_dir, tilesheet_rel)
        clean, labeled = base.render_map(p, tilesheet, out_dir, "preview_clean_fixed.png", "preview_labeled_fixed.png")
        source_preview = base.render_source_reference(p.source_map, out_dir)
        if source_preview:
            base.side_by_side(source_preview, clean, out_dir, f"source_vs_{original_id}_fixed_preview.png")
        validation = base.validate_prototype(p, tmx, tmj, tilesheet_rel)
        validation_report = base.write_validation_report(p, out_dir, validation, "validation_report_fixed.md")
        paths = {
            "tmx_fixed": str(tmx.resolve()),
            "tmj_fixed": str(tmj.resolve()),
            "preview_clean_fixed": str(clean.resolve()),
            "preview_labeled_fixed": str(labeled.resolve()),
            "validation_report_fixed": str(validation_report.resolve()),
        }
        metadata = write_fixed_metadata(p, out_dir, paths, validation)
        paths["metadata_fixed"] = str(metadata.resolve())
        before = out_dir / "preview_clean.png"
        if before.exists():
            ba = out_dir / (f"before_after_{original_id}.png" if original_id != "custom_03" else "before_after_custom_03.png")
            make_before_after(before, clean, ba, f"{original_id}: original vs fixed mine wall grammar")
            paths["before_after"] = str(ba.resolve())
        outputs[original_id] = paths
        validations[original_id] = validation

    contact = make_contact_sheet(outputs)
    (OUT_ROOT / "mine_wall_fix_outputs.json").write_text(json.dumps({
        "generatedAt": now_iso(),
        "outputs": outputs,
        "validations": validations,
        "contactSheet": str(contact.resolve()),
    }, indent=2), encoding="utf-8")
    write_reports(outputs, validations)
    failed = [m for m, v in validations.items() if v["status"] != "PASS"]
    print(json.dumps({"status": "PASS" if not failed else "FAIL", "failed": failed, "contactSheet": str(contact.resolve())}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
