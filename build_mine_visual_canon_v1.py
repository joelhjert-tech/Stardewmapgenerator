#!/usr/bin/env python3
"""Build Mine/Dungeon Visual Canon v1 from exact source-map crops.

This creates a small reviewable canon. It reads source maps and writes only
pattern_learning/, prototype_visual_maps/, reports/, and local validator data.
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_dungeon_visual_prototypes as proto  # noqa: E402
import build_fresh_mine_dungeon_patterns as fresh  # noqa: E402

CANON_ROOT = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1"
PREVIEW_DIR = CANON_ROOT / "previews"
REMAKE_ROOT = ROOT / "prototype_visual_maps" / "mine_visual_canon_tests"
REPORTS = ROOT / "reports"
TILESET_OUT = REMAKE_ROOT / "tilesheets" / "mine.png"

LAYERS = ("Back", "Buildings", "Front", "AlwaysFront", "Paths")
THEME = "vanilla_earth_mine"
EARTH_MAP_NUMBERS = set(range(1, 40))
STRUCTURAL_ROLES = {
    "straight_wall",
    "lower_wall_face",
    "left_edge",
    "right_edge",
    "outer_corner",
    "inner_corner",
    "angled_wall",
    "ladder_opening",
    "shaft_opening",
    "wall_shadow_strip",
    "floor_to_wall_transition",
    "deep_void_blocked_boundary",
    "small_complete_room_corner",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return str(path.resolve())


def ensure_dirs() -> None:
    for path in (CANON_ROOT, PREVIEW_DIR, REMAKE_ROOT, REMAKE_ROOT / "source_crop_remake_01",
                 REMAKE_ROOT / "source_crop_remake_02", REPORTS, REMAKE_ROOT / "tilesheets"):
        path.mkdir(parents=True, exist_ok=True)


def earth_source_paths() -> list[Path]:
    paths = []
    for p in sorted(fresh.BASEGAME_MINE.glob("*.tbin"), key=lambda q: int(q.stem) if q.stem.isdigit() else 9999):
        if p.stem.isdigit() and int(p.stem) in EARTH_MAP_NUMBERS:
            paths.append(p)
    return paths


def layer_tile(src: dict[str, Any], layer: str, x: int, y: int) -> Optional[dict[str, Any]]:
    val = fresh.get_tile(src, layer, x, y)
    if val is None:
        return None
    return {"tilesheetId": val[0], "localTileId": int(val[1])}


def stack_at(src: dict[str, Any], x: int, y: int) -> dict[str, Any]:
    stack = {}
    for layer in LAYERS:
        t = layer_tile(src, layer, x, y)
        if t is not None:
            stack[layer] = t
    return stack


def role_at(src: dict[str, Any], x: int, y: int) -> str:
    if fresh.tile_id(src, "Buildings", x, y) in fresh.LADDER_IDS:
        return "ladder_opening"
    if fresh.tile_id(src, "Buildings", x, y) in fresh.SHAFT_IDS:
        return "shaft_opening"
    n = fresh.neighbors8(src, x, y)
    wall = fresh.is_wall(src, x, y)
    front = fresh.tile_id(src, "Front", x, y)
    if front in fresh.FRONT_SHADOW_IDS and fresh.is_floor(src, x, y):
        return "wall_shadow_strip"
    if fresh.is_deep_void(src, x, y) and any(n.values()):
        return "deep_void_blocked_boundary"
    card = {d for d in ("N", "E", "S", "W") if n[d]}
    diag = {d for d in ("NE", "SE", "SW", "NW") if n[d]}
    if wall and card == {"S"}:
        return "lower_wall_face"
    if wall and card == {"E"}:
        return "left_edge"
    if wall and card == {"W"}:
        return "right_edge"
    if wall and (("S" in card and ("E" in card or "W" in card)) or ("N" in card and ("E" in card or "W" in card))):
        return "inner_corner"
    if wall and not card and diag:
        return "outer_corner"
    if wall and (len(card) >= 2 or len(diag) >= 2):
        return "angled_wall"
    if wall:
        return "straight_wall"
    if fresh.is_floor(src, x, y) and any(fresh.is_wall(src, x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
        return "floor_to_wall_transition"
    return "unclassified"


def crop_payload(src: dict[str, Any], crop_id: str, role: str, x: int, y: int, size: int) -> dict[str, Any]:
    half = size // 2
    cells = []
    masks = {"floorMask": [], "wallMask": [], "voidMask": [], "shadowMask": [], "collisionMask": [], "openingMask": []}
    tile_ids_by_layer: dict[str, list[int]] = {}
    for dy in range(size):
        for dx in range(size):
            sx, sy = x - half + dx, y - half + dy
            st = stack_at(src, sx, sy)
            cells.append({"dx": dx - half, "dy": dy - half, "stack": st})
            masks["floorMask"].append(bool(fresh.is_floor(src, sx, sy)))
            masks["wallMask"].append(bool(fresh.is_wall(src, sx, sy)))
            masks["voidMask"].append(bool(fresh.is_deep_void(src, sx, sy) or not st))
            masks["shadowMask"].append(fresh.tile_id(src, "Front", sx, sy) in fresh.FRONT_SHADOW_IDS)
            masks["collisionMask"].append(bool(fresh.is_wall(src, sx, sy) or fresh.is_deep_void(src, sx, sy)))
            masks["openingMask"].append(fresh.tile_id(src, "Buildings", sx, sy) in (fresh.LADDER_IDS | fresh.SHAFT_IDS))
            for layer, tile in st.items():
                tile_ids_by_layer.setdefault(layer, []).append(int(tile["localTileId"]))
    tile_ids_by_layer = {k: sorted(set(v)) for k, v in tile_ids_by_layer.items()}
    return {
        "sourceCropId": crop_id,
        "sourceMap": src["path"].name,
        "sourcePath": str(src["path"].resolve()),
        "sourceCategory": src["category"],
        "sourceCoordinate": {"x": x, "y": y},
        "width": size,
        "height": size,
        "layersIncluded": list(LAYERS),
        "role": role,
        "purpose": role.replace("_", " "),
        "whySelected": "Representative vanilla earth mine crop with complete source layer stacks for this structural role.",
        "sourceTilesheets": sorted({v["tilesheetId"] for c in cells for v in c["stack"].values()}),
        "tileIdsByLayer": tile_ids_by_layer,
        "cells": cells,
        **masks,
    }


def score_crop(src: dict[str, Any], x: int, y: int, size: int, role: str) -> int:
    half = size // 2
    score = 0
    for sy in range(y - half, y + half + 1):
        for sx in range(x - half, x + half + 1):
            if fresh.is_wall(src, sx, sy):
                score += 4
            if fresh.tile_id(src, "Front", sx, sy) in fresh.FRONT_SHADOW_IDS:
                score += 5
            if fresh.is_floor(src, sx, sy):
                score += 1
            if fresh.tile_id(src, "Buildings", sx, sy) in (fresh.LADDER_IDS | fresh.SHAFT_IDS):
                score += 8
    if role in {"ladder_opening", "shaft_opening", "wall_shadow_strip"}:
        score += 20
    return score


def select_crops() -> list[dict[str, Any]]:
    role_sizes = {
        "straight_wall": 9,
        "lower_wall_face": 9,
        "left_edge": 9,
        "right_edge": 9,
        "outer_corner": 9,
        "inner_corner": 9,
        "angled_wall": 11,
        "ladder_opening": 11,
        "shaft_opening": 11,
        "wall_shadow_strip": 7,
        "floor_to_wall_transition": 7,
        "deep_void_blocked_boundary": 7,
        "small_complete_room_corner": 15,
    }
    candidates: dict[str, list[tuple[int, dict[str, Any]]]] = {role: [] for role in role_sizes}
    for path in earth_source_paths():
        src = fresh.parse_source(path)
        if not src.get("parsed"):
            continue
        for y in range(2, src["height"] - 2):
            for x in range(2, src["width"] - 2):
                role = role_at(src, x, y)
                if role not in candidates:
                    continue
                size = role_sizes[role]
                half = size // 2
                if x - half < 0 or y - half < 0 or x + half >= src["width"] or y + half >= src["height"]:
                    continue
                payload = crop_payload(src, "pending", role, x, y, size)
                score = score_crop(src, x, y, size, role)
                candidates[role].append((score, payload))
                if role == "inner_corner":
                    room_payload = crop_payload(src, "pending", "small_complete_room_corner", x, y, 15)
                    candidates["small_complete_room_corner"].append((score + 10, room_payload))
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, int, int, int]] = set()
    for role in role_sizes:
        options = sorted(candidates[role], key=lambda item: item[0], reverse=True)
        for _score, crop in options:
            key = (crop["sourceMap"], crop["sourceCoordinate"]["x"], crop["sourceCoordinate"]["y"], crop["width"])
            if key in used:
                continue
            crop["sourceCropId"] = f"earth_{role}_{len(selected) + 1:02d}"
            selected.append(crop)
            used.add(key)
            break
    # Add a few second variants where available so the canon is not one-example thin.
    for role in ("lower_wall_face", "inner_corner", "outer_corner", "wall_shadow_strip", "ladder_opening"):
        options = sorted(candidates.get(role, []), key=lambda item: item[0], reverse=True)
        for _score, crop in options:
            key = (crop["sourceMap"], crop["sourceCoordinate"]["x"], crop["sourceCoordinate"]["y"], crop["width"])
            if key in used:
                continue
            crop["sourceCropId"] = f"earth_{role}_{len(selected) + 1:02d}"
            selected.append(crop)
            used.add(key)
            break
    return selected[:18]


def tile_image(tilesheet: Image.Image, local_id: int) -> Image.Image:
    cols = tilesheet.width // 16
    sx, sy = (local_id % cols) * 16, (local_id // cols) * 16
    return tilesheet.crop((sx, sy, sx + 16, sy + 16))


def render_crop(crop: dict[str, Any], out_prefix: Path, labels: bool = True) -> dict[str, str]:
    tilesheet = Image.open(proto.TILESET_SRC).convert("RGBA")

    def draw(which: str) -> Image.Image:
        img = Image.new("RGBA", (crop["width"] * 16, crop["height"] * 16), (0, 0, 0, 255 if which == "combined" else 0))
        for cell in crop["cells"]:
            dx = cell["dx"] + crop["width"] // 2
            dy = cell["dy"] + crop["height"] // 2
            layers = ["Back", "Buildings", "Front", "AlwaysFront"] if which == "combined" else [which]
            for layer in layers:
                tile = cell["stack"].get(layer)
                if tile is None:
                    continue
                img.alpha_composite(tile_image(tilesheet, int(tile["localTileId"])), (dx * 16, dy * 16))
        if labels:
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, img.width - 1, img.height - 1), outline=(255, 255, 255, 110))
        return img

    paths = {}
    for layer in ("combined", "Back", "Buildings", "Front", "AlwaysFront"):
        out = out_prefix.with_name(f"{out_prefix.name}_{layer.lower()}.png")
        draw(layer).save(out)
        paths[layer] = rel(out)
    return paths


def build_template(crop: dict[str, Any]) -> dict[str, Any]:
    tid = crop["sourceCropId"].replace("earth_", "canon_earth_")
    return {
        "templateId": tid,
        "templateName": crop["purpose"].title(),
        "visualTheme": THEME,
        "sourceMap": crop["sourceMap"],
        "sourcePath": crop["sourcePath"],
        "sourceCoordinate": crop["sourceCoordinate"],
        "sourceCropId": crop["sourceCropId"],
        "role": crop["role"],
        "structuralDesign": crop["role"],
        "width": crop["width"],
        "height": crop["height"],
        "anchor": {"x": crop["width"] // 2, "y": crop["height"] // 2},
        "Back": [c for c in crop["cells"] if "Back" in c["stack"]],
        "Buildings": [c for c in crop["cells"] if "Buildings" in c["stack"]],
        "Front": [c for c in crop["cells"] if "Front" in c["stack"]],
        "AlwaysFront": [c for c in crop["cells"] if "AlwaysFront" in c["stack"]],
        "layerStack": crop["cells"],
        "tileIdsByLayer": crop["tileIdsByLayer"],
        "tilesheet": "mine",
        "compatibleTilesheets": ["mine"],
        "floorMask": crop["floorMask"],
        "wallMask": crop["wallMask"],
        "voidMask": crop["voidMask"],
        "shadowMask": crop["shadowMask"],
        "collisionMask": crop["collisionMask"],
        "openingMask": crop["openingMask"],
        "requiredNeighborContext": {"exactSourceCropContextRequiredForClone": True},
        "allowedRotations": ["none"],
        "allowedMirrors": [],
        "placementRules": [
            "Use as a whole source-proven layer stack.",
            "Do not decompose into single tile role lists.",
            "For generator use, require Joel_approved + generator_ready.",
        ],
        "fallbackTemplateId": "marker_only_fallback",
        "visualStatus": "Joel_review_needed",
        "generatorStatus": "prototype_ready",
        "locked": False,
        "previewPath": "",
        "notes": "Source-crop canon v1 candidate. Exact remakes may use it; procedural generation must wait for Joel approval.",
    }


def render_atlas(templates: list[dict[str, Any]]) -> Path:
    thumbs = []
    for t in templates:
        previews = t.get("previewPaths") or {"combined": t.get("previewPath", "")}
        panels = []
        for label, key in (("Combined", "combined"), ("Back", "Back"), ("Buildings", "Buildings"), ("Front", "Front")):
            img_path = ROOT / previews.get(key, "")
            img = Image.open(img_path).convert("RGBA") if img_path.exists() else Image.new("RGBA", (96, 96), (30, 30, 30, 255))
            scale = max(1, 72 // max(img.width, img.height))
            if scale > 1:
                img = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
            panel = Image.new("RGBA", (92, 104), (16, 16, 18, 255))
            panel.alpha_composite(img, ((92 - img.width) // 2, 22))
            pd = ImageDraw.Draw(panel)
            pd.text((4, 4), label, fill=(235, 235, 235, 230))
            panels.append(panel)
        tile = Image.new("RGBA", (560, 170), (22, 22, 24, 255))
        for i, panel in enumerate(panels):
            tile.alpha_composite(panel, (8 + i * 96, 34))
        d = ImageDraw.Draw(tile)
        d.text((8, 6), t["templateId"][:54], fill=(255, 255, 255, 230))
        d.text((400, 36), f"role: {t['role']}", fill=(220, 220, 220, 230))
        d.text((400, 54), f"src: {t['sourceMap']} @ {t['sourceCoordinate']['x']},{t['sourceCoordinate']['y']}", fill=(200, 200, 200, 230))
        d.text((400, 72), f"status: {t['visualStatus']}", fill=(245, 210, 120, 230))
        d.text((400, 90), f"gen: {t['generatorStatus']}", fill=(245, 210, 120, 230))
        ids = ", ".join(f"{k}:{'/'.join(map(str, v[:5]))}" for k, v in t["tileIdsByLayer"].items())
        d.text((8, 146), ids[:80], fill=(190, 220, 255, 230))
        thumbs.append(tile)
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    atlas = Image.new("RGBA", (cols * 560, max(1, rows) * 170), (18, 18, 20, 255))
    for i, thumb in enumerate(thumbs):
        atlas.alpha_composite(thumb, ((i % cols) * 560, (i // cols) * 170))
    out = PREVIEW_DIR / "mine_dungeon_visual_canon_v1_atlas.png"
    atlas.save(out)
    return out


def create_negative_rules(templates: list[dict[str, Any]]) -> dict[str, Any]:
    front_ids = sorted({tid for t in templates for tid in t["tileIdsByLayer"].get("Front", [])})
    building_ids = sorted({tid for t in templates for tid in t["tileIdsByLayer"].get("Buildings", [])})
    return {
        "schemaVersion": 1,
        "generatedAt": now_iso(),
        "visualTheme": THEME,
        "rules": [
            {
                "ruleId": "no_loose_structural_tiles",
                "severity": "block",
                "description": "Walls, corners, shadows, ladders, shafts, and openings must be placed as complete approved templates, not single tile IDs.",
            },
            {
                "ruleId": "front_shadow_requires_wall_context",
                "severity": "block",
                "frontTileIdsObservedInCanon": front_ids,
                "description": "Front-layer shadow/overlay tiles require the paired Back/Buildings context from their source template.",
            },
            {
                "ruleId": "void_ids_are_not_wall_art",
                "severity": "block",
                "tileIds": sorted(fresh.DEEP_VOID_IDS),
                "description": "Deep void/filler IDs are not valid structural wall/corner overlays.",
            },
            {
                "ruleId": "wall_piece_never_alone",
                "severity": "block",
                "buildingTileIdsObservedInCanon": building_ids,
                "description": "A wall-looking Buildings tile is invalid unless its neighboring template context is present.",
            },
            {
                "ruleId": "opening_requires_socket",
                "severity": "block",
                "tileIds": sorted(fresh.LADDER_IDS | fresh.SHAFT_IDS),
                "description": "Ladder/shaft tiles require a source-proven socket template.",
            },
            {
                "ruleId": "unapproved_canon_not_generator_ready",
                "severity": "block",
                "description": "Joel_review_needed templates may be used in exact clone tests but not in procedural generation as generator_ready.",
            },
        ],
    }


def make_proto_from_crop(crop: dict[str, Any], map_id: str) -> proto.PrototypeMap:
    p = proto.PrototypeMap(
        map_id=map_id,
        title=f"{map_id} exact source crop remake",
        kind="source_crop_remake",
        source_map=crop["sourceMap"],
        source_origin="Mine/Dungeon Visual Canon v1 exact layer-stack clone",
        source_reason=f"Exact remake of {crop['sourceCropId']} for visual grammar proof.",
        width=crop["width"],
        height=crop["height"],
        seed=0,
        floor_style="earth",
        entrance=(0, 0),
        exit=(crop["width"] - 1, crop["height"] - 1),
    )
    p.init_layers()
    for layer in LAYERS:
        p.layers[layer] = [0] * (p.width * p.height)
    for cell in crop["cells"]:
        x = cell["dx"] + crop["width"] // 2
        y = cell["dy"] + crop["height"] // 2
        for layer, tile in cell["stack"].items():
            p.set_tile(layer, x, y, int(tile["localTileId"]))
        if cell["stack"].get("Back") and not cell["stack"].get("Buildings"):
            p.walkable.add((x, y))
        if cell["stack"].get("Buildings"):
            p.blocked.add((x, y))
    return p


def write_remake(crop: dict[str, Any], index: int) -> dict[str, Any]:
    out_dir = REMAKE_ROOT / f"source_crop_remake_{index:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    map_id = f"source_crop_remake_{index:02d}"
    p = make_proto_from_crop(crop, map_id)
    tmx = proto.write_tmx(p, out_dir, "../tilesheets/mine.png")
    tmj = proto.write_tmj(p, out_dir, "../tilesheets/mine.png")
    tilesheet = Image.open(proto.TILESET_SRC).convert("RGBA")
    clean, labeled = proto.render_map(p, tilesheet, out_dir)
    source_preview = ROOT / crop["previewPaths"]["combined"]
    src_img = Image.open(source_preview).convert("RGBA")
    gen_img = Image.open(clean).convert("RGBA")
    sheet = Image.new("RGBA", (src_img.width + gen_img.width + 16, max(src_img.height, gen_img.height) + 20), (18, 18, 20, 255))
    sheet.alpha_composite(src_img, (0, 20))
    sheet.alpha_composite(gen_img, (src_img.width + 16, 20))
    d = ImageDraw.Draw(sheet)
    d.text((4, 4), "source crop", fill=(255, 255, 255, 230))
    d.text((src_img.width + 20, 4), "remake", fill=(255, 255, 255, 230))
    source_vs_remake = out_dir / "source_vs_remake.png"
    sheet.save(source_vs_remake)
    metadata = {
        "generatedAt": now_iso(),
        "mapId": map_id,
        "sourceCropId": crop["sourceCropId"],
        "sourceMap": crop["sourceMap"],
        "sourceCoordinate": crop["sourceCoordinate"],
        "exactLayerStackClone": True,
        "prototypeOnly": True,
        "templateSource": "mine_dungeon_visual_canon_v1",
        "paths": {
            "tmx": rel(tmx),
            "tmj": rel(tmj),
            "preview_clean": rel(clean),
            "preview_labeled": rel(labeled),
            "source_vs_remake": rel(source_vs_remake),
        },
    }
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    report = out_dir / "validation_report.md"
    report.write_text(
        f"# {map_id} Validation\n\n"
        f"- Source crop: `{crop['sourceCropId']}`\n"
        f"- Source map: `{crop['sourceMap']}` @ {crop['sourceCoordinate']['x']},{crop['sourceCoordinate']['y']}\n"
        f"- Exact source layer stacks copied: pending validator\n"
        f"- Prototype only: true\n",
        encoding="utf-8",
    )
    return {"mapId": map_id, "sourceCropId": crop["sourceCropId"], "outDir": rel(out_dir), "metadata": rel(metadata_path)}


def write_schema() -> None:
    schema = {
        "schemaVersion": 1,
        "requiredFields": [
            "templateId", "visualTheme", "sourceMap", "sourceCoordinate", "sourceCropId", "role",
            "width", "height", "anchor", "Back", "Buildings", "Front", "AlwaysFront",
            "tileIdsByLayer", "floorMask", "wallMask", "voidMask", "shadowMask", "collisionMask",
            "openingMask", "visualStatus", "generatorStatus", "locked",
        ],
    }
    (CANON_ROOT / "mine_dungeon_visual_canon_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")


def write_reports(crops: list[dict[str, Any]], canon: dict[str, Any], atlas: Path, negative: dict[str, Any], remakes: list[dict[str, Any]]) -> None:
    role_counts = Counter(c["role"] for c in crops)
    theme_text = (
        "# Mine Visual Canon Theme Selection\n\n"
        f"- Selected theme: `{THEME}`\n"
        "- Reason: current conformance target is Earth mine p5/p50 visual density; this mission should not mix frost/lava/desert/Moonvillage styles.\n"
        "- Source maps used: vanilla mine floors 1-39 from `mission_assets/unpacked_basegame/Mine` (read-only).\n"
        "- Tilesheet used: vanilla `mine.png` local IDs.\n"
        "- Ratio reference: Earth frontToBuildingsRatio p5 0.774, p50 1.053, p95 1.524 from prior segmented calibration.\n"
        "- Visual goal: source-proven 3D mine wall objects with paired Back/Buildings/Front context.\n"
    )
    (REPORTS / "mine_visual_canon_theme_selection.md").write_text(theme_text, encoding="utf-8")

    crop_lines = [
        "# Mine Visual Canon Source Crop Selection\n",
        "| crop | role | source | coord | size | preview |",
        "|---|---|---|---:|---:|---|",
    ]
    for c in crops:
        crop_lines.append(
            f"| `{c['sourceCropId']}` | {c['role']} | `{c['sourceMap']}` | "
            f"{c['sourceCoordinate']['x']},{c['sourceCoordinate']['y']} | {c['width']}x{c['height']} | `{c['previewPaths']['combined']}` |"
        )
    (REPORTS / "mine_visual_canon_source_crop_selection.md").write_text("\n".join(crop_lines) + "\n", encoding="utf-8")

    atlas_md = (
        "# Mine/Dungeon Visual Canon v1 Atlas\n\n"
        f"- Atlas: `{rel(atlas)}`\n"
        f"- Templates: {len(canon['templates'])}\n"
        "- Each tile in the atlas shows Combined, Back, Buildings, and Front previews plus role, coordinate, key IDs, and review/generator status.\n"
    )
    (REPORTS / "mine_dungeon_visual_canon_v1_atlas.md").write_text(atlas_md, encoding="utf-8")

    rules_lines = ["# Negative Mine Template Rules\n"]
    for rule in negative["rules"]:
        rules_lines.append(f"- `{rule['ruleId']}` ({rule['severity']}): {rule['description']}")
    (REPORTS / "negative_mine_template_rules.md").write_text("\n".join(rules_lines) + "\n", encoding="utf-8")

    summary = (
        "# Mine/Dungeon Visual Canon v1 Summary\n\n"
        f"- Selected theme: `{THEME}`\n"
        f"- Source crops selected: {len(crops)}\n"
        f"- Templates created: {len(canon['templates'])}\n"
        f"- Role coverage: {dict(sorted(role_counts.items()))}\n"
        f"- Negative rules: {len(negative['rules'])}\n"
        f"- Exact remakes generated: {len(remakes)}\n"
        "- Smart Edge-Wrapper v2 integration: optional `--template-source visual-canon-v1` flag added; unapproved canon templates are skipped.\n"
        "- Generator readiness: not generator-ready until Joel review approves and locks selected templates.\n"
    )
    (REPORTS / "mine_visual_canon_v1_summary.md").write_text(summary, encoding="utf-8")

    safety = (
        "# Mine/Dungeon Visual Canon v1 Safety Status\n\n"
        "- Source maps were read only.\n"
        "- No production map generated.\n"
        "- No mission_assets, unpacked_basegame, Moonvillage source maps, or approved DB files were modified.\n"
        "- Structural tiles remain template-bound; no loose structural role list was created.\n"
        "- All canon templates are `Joel_review_needed` and `prototype_ready`, not `generator_ready`.\n"
    )
    (REPORTS / "mine_visual_canon_v1_safety_status.md").write_text(safety, encoding="utf-8")

    next_steps = (
        "# Mine/Dungeon Visual Canon v1 Next Steps\n\n"
        "1. Review `mine_dungeon_visual_canon_v1_atlas.png` visually.\n"
        "2. Mark approved templates as `Joel_approved`, `generator_ready`, and `locked` in a copied review pack.\n"
        "3. Add more exact crop remakes for any rejected or ambiguous role.\n"
        "4. Only then enable canon templates for procedural custom map generation.\n"
    )
    (REPORTS / "mine_visual_canon_v1_next_steps.md").write_text(next_steps, encoding="utf-8")

    validation = (
        "# Mine/Dungeon Visual Canon v1 Validation Results\n\n"
        "- Build completed. Run `python validate_mine_visual_canon.py` and `python validate_source_crop_remakes.py` for exact pass/fail.\n"
        f"- Remakes: {', '.join(r['mapId'] for r in remakes)}\n"
    )
    (REPORTS / "mine_visual_canon_v1_validation_results.md").write_text(validation, encoding="utf-8")


def main() -> int:
    ensure_dirs()
    if proto.TILESET_SRC.exists():
        shutil.copy2(proto.TILESET_SRC, TILESET_OUT)
    crops = select_crops()
    if len(crops) < 10:
        raise RuntimeError(f"expected at least 10 source crops, found {len(crops)}")
    templates = []
    for crop in crops:
        prefix = PREVIEW_DIR / crop["sourceCropId"]
        crop["previewPaths"] = render_crop(crop, prefix)
        template = build_template(crop)
        template["previewPath"] = crop["previewPaths"]["combined"]
        template["previewPaths"] = crop["previewPaths"]
        templates.append(template)
    canon = {
        "schemaVersion": 1,
        "generatedAt": now_iso(),
        "visualTheme": THEME,
        "description": "Small source-preview-backed visual canon for vanilla earth mine structural grammar.",
        "templateCount": len(templates),
        "templates": templates,
        "markerFallback": {
            "templateId": "marker_only_fallback",
            "description": "Use marker-only output when a reviewed structural template is missing.",
        },
    }
    source_crops = {
        "schemaVersion": 1,
        "generatedAt": now_iso(),
        "visualTheme": THEME,
        "sourceRoot": str(fresh.BASEGAME_MINE.resolve()),
        "crops": crops,
    }
    negative = create_negative_rules(templates)
    (CANON_ROOT / "source_crops.json").write_text(json.dumps(source_crops, indent=2), encoding="utf-8")
    (CANON_ROOT / "mine_dungeon_visual_canon_v1.json").write_text(json.dumps(canon, indent=2), encoding="utf-8")
    (CANON_ROOT / "negative_mine_template_rules.json").write_text(json.dumps(negative, indent=2), encoding="utf-8")
    write_schema()
    atlas = render_atlas(templates)
    remakes = [write_remake(crops[0], 1), write_remake(crops[1], 2)]
    write_reports(crops, canon, atlas, negative, remakes)
    print(json.dumps({
        "status": "built",
        "theme": THEME,
        "crops": len(crops),
        "templates": len(templates),
        "atlas": rel(atlas),
        "remakes": remakes,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
