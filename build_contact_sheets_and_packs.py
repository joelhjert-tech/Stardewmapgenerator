#!/usr/bin/env python3
"""
build_contact_sheets_and_packs.py  (READ-ONLY w.r.t. sources)

From the cleaned mine block library, render focused ENLARGED contact sheets (combined +
per-layer splits, with labels/scores/flags) limited to the best 20-50 candidates per
category, render per-block previews for the approval packs, and write small approval packs
(decision: null). Nothing is promoted; mine.png is the only image read.
"""
from __future__ import annotations
import json, sys, collections
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
SHEETS = CLEANED / "review_contact_sheets"
PREVIEWS = CLEANED / "previews"
PACKS = CLEANED / "review_packs"
TILESHEET = ROOT / "prototype_visual_maps" / "dungeon_review" / "tilesheets" / "mine.png"
CLEAN_LIB = CLEANED / "cleaned_building_block_library.json"
QUAR = CLEANED / "quarantine" / "quarantined_building_blocks.json"
COMBO = MBB / "tile_id_combination_index.json"
TS = datetime.now(timezone.utc).isoformat()
TILE = 16
VOID = {77, 135}
sys.path.insert(0, str(ROOT))
import score_map_building_blocks as S  # noqa: E402

try:
    FONT = ImageFont.truetype("arial.ttf", 11)
    FONT_SM = ImageFont.truetype("arial.ttf", 9)
except Exception:
    FONT = ImageFont.load_default(); FONT_SM = ImageFont.load_default()


def render_layer(block, sheet, cols, layers, scale):
    w, h = block["width"], block["height"]
    img = Image.new("RGBA", (w * TILE, h * TILE), (16, 16, 20, 255))
    for cell in block["cells"]:
        px, py = cell["dx"] * TILE, cell["dy"] * TILE
        for layer in layers:
            tid = cell["stack"].get(layer)
            if tid is None or int(tid) in VOID:
                continue
            tid = int(tid)
            sx, sy = (tid % cols) * TILE, (tid // cols) * TILE
            img.alpha_composite(sheet.crop((sx, sy, sx + TILE, sy + TILE)), (px, py))
    return img.resize((w * TILE * scale, h * TILE * scale), Image.Resampling.NEAREST)


def block_card(block, sheet, cols, card_w):
    """Combined (large) + Back/Buildings/Front splits (small) + text, returned as an image."""
    big = render_layer(block, sheet, cols, ("Back", "Buildings", "Front"), 6)
    backs = render_layer(block, sheet, cols, ("Back",), 3)
    blds = render_layer(block, sheet, cols, ("Buildings",), 3)
    fronts = render_layer(block, sheet, cols, ("Front",), 3)
    pad = 6
    text_h = 64
    splits_h = max(backs.height, blds.height, fronts.height) + 14
    card_h = big.height + splits_h + text_h + pad * 3
    card = Image.new("RGBA", (card_w, card_h), (28, 28, 34, 255))
    d = ImageDraw.Draw(card)
    card.alpha_composite(big, (pad, pad))
    # splits row
    sy = pad + big.height + pad
    x = pad
    for label, im in (("Back", backs), ("Bld", blds), ("Front", fronts)):
        d.text((x, sy), label, font=FONT_SM, fill=(150, 200, 255, 255))
        card.alpha_composite(im, (x, sy + 12))
        x += max(im.width, 30) + 10
    # text block
    ty = sy + splits_h + 2
    sc = block["scores"]
    bid = (block.get("cleanedBlockId") or block["blockId"])
    d.text((pad, ty), bid[-30:], font=FONT_SM, fill=(235, 235, 230, 255))
    d.text((pad, ty + 12), f"{block['blockType']}  {block['sizeClass']}  freq={block['frequency']}",
           font=FONT_SM, fill=(200, 205, 210, 255))
    d.text((pad, ty + 24), f"reuse={sc['reusableGeneratorScore']:.2f} crop={sc['cropQualityScore']:.2f} "
                           f"conf={sc['classificationConfidence']:.2f}", font=FONT_SM, fill=(180, 220, 180, 255))
    src = (block.get("exampleSource") or [{}])[0]
    d.text((pad, ty + 36), f"src {src.get('map','?')} ({src.get('x','?')},{src.get('y','?')})",
           font=FONT_SM, fill=(170, 175, 185, 255))
    flags = [f for f in block.get("riskFlags", []) if f != "good_review_candidate"]
    if flags:
        d.text((pad, ty + 48), ("flags: " + ",".join(flags))[:46], font=FONT_SM, fill=(230, 180, 140, 255))
    return card


def contact_sheet(title, blocks, sheet, cols, out_path, per_row=4, limit=50):
    blocks = blocks[:limit]
    if not blocks:
        img = Image.new("RGBA", (640, 120), (24, 24, 28, 255))
        ImageDraw.Draw(img).text((12, 50), f"{title}: no clean candidates in this category.",
                                  font=FONT, fill=(230, 200, 160, 255))
        img.save(out_path)
        return 0
    card_w = 280
    cards = [block_card(b, sheet, cols, card_w) for b in blocks]
    card_h = max(c.height for c in cards)
    rows = (len(cards) + per_row - 1) // per_row
    header = 28
    W = per_row * (card_w + 8) + 8
    H = header + rows * (card_h + 8) + 8
    sheetimg = Image.new("RGBA", (W, H), (18, 18, 22, 255))
    d = ImageDraw.Draw(sheetimg)
    d.text((10, 7), f"{title}  ({len(blocks)} candidates)", font=FONT, fill=(120, 200, 255, 255))
    for i, c in enumerate(cards):
        r, col = divmod(i, per_row)
        x = 8 + col * (card_w + 8)
        y = header + r * (card_h + 8)
        sheetimg.alpha_composite(c, (x, y))
    sheetimg.save(out_path)
    return len(blocks)


def preview(block, sheet, cols):
    bid = (block.get("cleanedBlockId") or block["blockId"])
    img = render_layer(block, sheet, cols, ("Back", "Buildings", "Front"), 10)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    img.save(PREVIEWS / f"{bid}.png")
    return f"pattern_learning/map_building_blocks/cleaned_blocks/previews/{bid}.png"


def sheet_selections(clean, quar):
    """Single source of truth: which blocks each contact sheet shows, in render order.

    Returns an ordered dict {sheetFilename: {"title", "blocks" (full sorted list),
    "limit"}}. The blocks actually shown on a sheet are blocks[:limit]. Used by both the
    renderer and the Joel-approval mapper so sheet->blockId mapping needs no OCR.
    """
    def of(types, src=clean):
        return sorted([b for b in src if b["blockType"] in types],
                      key=lambda b: -b["scores"]["reusableGeneratorScore"])

    quar_sample, seen_reason = [], collections.Counter()
    for b in quar:
        key = b["cleaningReason"].split(":")[0]
        if seen_reason[key] < 4:
            quar_sample.append(b); seen_reason[key] += 1

    return {
        "review_floor_blocks_large.png": {"title": "Floor blocks", "blocks": of(S.FLOOR_TYPES), "limit": 40},
        "review_wall_forward_lower_face_large.png": {"title": "Wall — forward lower face",
            "blocks": of({"mine_wall_forward_lower_face", "mine_wall_back_top_edge"}), "limit": 40},
        "review_wall_body_large.png": {"title": "Wall body (re-cut, larger context)",
            "blocks": of({"mine_wall_body"}), "limit": 40},
        "review_wall_edges_large.png": {"title": "Wall edges (left/right)", "blocks": of(S.EDGE_TYPES), "limit": 30},
        "review_corners_large.png": {"title": "Corners (inner/outer)", "blocks": of(S.CORNER_TYPES), "limit": 40},
        "review_openings_large.png": {"title": "Openings (ladder/shaft sockets)",
            "blocks": sorted([b for b in clean + quar if b["roleCounts"].get("opening", 0) > 0],
                             key=lambda b: -b["scores"]["reusableGeneratorScore"]), "limit": 30},
        "review_shadow_and_front_overlay_large.png": {"title": "Shadow / Front overlay blocks",
            "blocks": sorted([b for b in clean if b.get("shadowMask")],
                             key=lambda b: (-b["scores"]["frontPairingScore"], -b["scores"]["reusableGeneratorScore"])),
            "limit": 30},
        "review_quarantined_examples_large.png": {"title": "Quarantined examples (do NOT approve)",
            "blocks": quar_sample, "limit": 24},
    }


def main():
    SHEETS.mkdir(parents=True, exist_ok=True)
    PACKS.mkdir(parents=True, exist_ok=True)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    clean = json.loads(CLEAN_LIB.read_text(encoding="utf-8"))["blocks"]
    quar = json.loads(QUAR.read_text(encoding="utf-8"))["blocks"]
    combos = json.loads(COMBO.read_text(encoding="utf-8"))["combinations"]
    sheet = Image.open(TILESHEET).convert("RGBA")
    cols = sheet.width // TILE

    sel = sheet_selections(clean, quar)

    rendered = {}
    for fname, spec in sel.items():
        rendered[fname] = contact_sheet(spec["title"], spec["blocks"], sheet, cols,
                                        SHEETS / fname, limit=spec["limit"])
    floor = sel["review_floor_blocks_large.png"]["blocks"]
    lower = sel["review_wall_forward_lower_face_large.png"]["blocks"]
    wbody = sel["review_wall_body_large.png"]["blocks"]
    edges = sel["review_wall_edges_large.png"]["blocks"]
    corners = sel["review_corners_large.png"]["blocks"]
    openings = sel["review_openings_large.png"]["blocks"]

    # ---- approval packs (strong candidates only) + per-block previews ----
    def pack(name, blocks, limit, title):
        items = []
        for b in blocks[:limit]:
            ppath = preview(b, sheet, cols)
            bid = b["blockId"]
            src = (b.get("exampleSource") or [{}])[0]
            items.append({
                "blockId": bid, "cleanedBlockId": b.get("cleanedBlockId"),
                "blockType": b["blockType"], "sourceMap": src.get("map"),
                "sourceCoordinate": {"x": src.get("x"), "y": src.get("y")},
                "previewPath": ppath, "contactSheet": title,
                "size": b["sizeClass"], "layers": sorted({L for c in b["cells"] for L in c["stack"]}),
                "tileIdsByLayer": combos.get(bid, {}).get("tileIdsByLayer"),
                "qualityScores": b["scores"], "riskFlags": b["riskFlags"],
                "cleaningDecision": b["cleaningDecision"],
                "decision": None, "notes": "",
            })
        (PACKS / name).write_text(json.dumps({
            "generatedAt": TS, "pack": name.replace("_approval_pack.json", ""),
            "instruction": "Set each item's 'decision' to true (approve) or false (reject). "
                           "Approved items are later promoted by promote_cleaned_blocks; nothing is auto-approved.",
            "itemCount": len(items), "items": items,
        }, indent=2), encoding="utf-8")
        return len(items)

    packs = {}
    packs["floor_blocks_approval_pack.json"] = pack("floor_blocks_approval_pack.json", floor, 30, "review_floor_blocks_large.png")
    packs["wall_blocks_approval_pack.json"] = pack("wall_blocks_approval_pack.json", wbody + lower + edges, 40, "review_wall_body_large.png")
    packs["corner_blocks_approval_pack.json"] = pack("corner_blocks_approval_pack.json", corners, 24, "review_corners_large.png")
    packs["opening_blocks_approval_pack.json"] = pack("opening_blocks_approval_pack.json", openings, 24, "review_openings_large.png")

    print(json.dumps({"contactSheets": rendered, "approvalPacks": packs,
                      "openingsFound": len(openings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
