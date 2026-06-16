import hashlib
import json
import math
import re
import struct
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
REVIEW_ROOT = TOOL_ROOT / "review"
SEED_ROOT = REVIEW_ROOT / "seed_approval"
DUP_ROOT = REVIEW_ROOT / "duplicate_resolution"
REPORTS_ROOT = TOOL_ROOT / "reports"
PREVIEW_ROOT = TOOL_ROOT / "previews" / "seed_approval"
CLASS_ROOT = TOOL_ROOT / "classification"
DB_ROOT = TOOL_ROOT / "database"
STYLEPACK_ROOT = TOOL_ROOT / "stylepacks"

PROPOSALS_PATH = REVIEW_ROOT / "auto_resolution" / "medium_confidence_proposed_tags.json"
EVIDENCE_PATH = REVIEW_ROOT / "auto_resolution" / "tile_evidence_index.json"
CANONICAL_PATH = CLASS_ROOT / "canonical_tile_candidates.json"
APPROVED_DB_PATH = DB_ROOT / "tile_database_v1_human_approved.json"

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "AlwaysFront2", "Paths", "Objects", "Map"}
VALID_COLLISIONS = {"unknown", "walkable", "blocked", "blocks", "decorative", "front_only", "water", "custom", "profile_specific"}
RESTRICTED_DEEPWOODS_MARKERS = {
    "deepwoodslaketilesheet",
    "deepwoodsinfestedoutdoorstilesheet",
    "deepwoodsmod-main",
    "deepwoodsmod\\src\\deepwoods\\assets",
    "deepwoodsmod/src/deepwoods/assets",
}


FONT = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["111", "100", "100", "100", "111"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["111", "100", "101", "101", "111"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "111"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "O": ["111", "101", "101", "101", "111"],
    "P": ["111", "101", "111", "100", "100"],
    "Q": ["111", "101", "101", "111", "001"],
    "R": ["111", "101", "111", "110", "101"],
    "S": ["111", "100", "111", "001", "111"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    ":": ["0", "1", "0", "1", "0"],
    "-": ["0", "0", "111", "0", "0"],
    "_": ["0", "0", "0", "0", "111"],
    " ": ["0", "0", "0", "0", "0"],
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data, *, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def unpack_bits(row, width, bit_depth):
    values = []
    mask = (1 << bit_depth) - 1
    for byte in row:
        for shift in range(8 - bit_depth, -1, -bit_depth):
            values.append((byte >> shift) & mask)
            if len(values) == width:
                return values
    return values


def decode_png_rgba(path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    palette = []
    transparency = b""
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", payload)
        elif kind == b"PLTE":
            palette = [tuple(payload[i : i + 3]) for i in range(0, len(payload), 3)]
        elif kind == b"tRNS":
            transparency = payload
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if interlace != 0:
        raise ValueError("interlaced PNG is not supported")
    if bit_depth not in {1, 2, 4, 8, 16}:
        raise ValueError(f"unsupported bit depth {bit_depth}")
    components_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in components_by_type:
        raise ValueError(f"unsupported color type {color_type}")
    components = components_by_type[color_type]
    bits_per_pixel = components * bit_depth
    row_bytes = (width * bits_per_pixel + 7) // 8
    filter_bpp = max(1, math.ceil(bits_per_pixel / 8))
    raw = zlib.decompress(bytes(idat))
    rows = []
    offset = 0
    prev = bytearray(row_bytes)
    for _y in range(height):
        filter_type = raw[offset]
        offset += 1
        cur = bytearray(raw[offset : offset + row_bytes])
        offset += row_bytes
        for i in range(row_bytes):
            left = cur[i - filter_bpp] if i >= filter_bpp else 0
            up = prev[i]
            upper_left = prev[i - filter_bpp] if i >= filter_bpp else 0
            if filter_type == 1:
                cur[i] = (cur[i] + left) & 0xFF
            elif filter_type == 2:
                cur[i] = (cur[i] + up) & 0xFF
            elif filter_type == 3:
                cur[i] = (cur[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                cur[i] = (cur[i] + paeth(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter {filter_type}")
        rows.append(bytes(cur))
        prev = cur

    rgba = bytearray(width * height * 4)
    out = 0
    for row in rows:
        if color_type == 3:
            indices = unpack_bits(row, width, bit_depth) if bit_depth < 8 else list(row[:width])
            for idx in indices:
                r, g, b = palette[idx] if idx < len(palette) else (0, 0, 0)
                a = transparency[idx] if idx < len(transparency) else 255
                rgba[out : out + 4] = bytes((r, g, b, a))
                out += 4
            continue
        step = components * (2 if bit_depth == 16 else 1)
        for x in range(width):
            px = row[x * step : (x + 1) * step]
            if bit_depth == 16:
                px = px[0::2]
            if color_type == 6:
                r, g, b, a = px
            elif color_type == 2:
                r, g, b = px
                a = 255
            elif color_type == 0:
                r = g = b = px[0]
                a = 255
            elif color_type == 4:
                r = g = b = px[0]
                a = px[1]
            else:
                raise ValueError(f"unsupported color type {color_type}")
            rgba[out : out + 4] = bytes((r, g, b, a))
            out += 4
    return width, height, bytes(rgba)


def write_png_rgba(path, width, height, rgba):
    rows = []
    stride = width * 4
    for y in range(height):
        rows.append(b"\x00" + bytes(rgba[y * stride : (y + 1) * stride]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + png_chunk(b"IEND", b"")
    )


def paste_scaled(canvas, canvas_width, src_rgba, src_width, src_height, dst_x, dst_y, scale):
    for sy in range(src_height):
        for sx in range(src_width):
            src_i = (sy * src_width + sx) * 4
            color = src_rgba[src_i : src_i + 4]
            if color[3] == 0:
                color = bytes((32, 32, 32, 255))
            for yy in range(scale):
                cy = dst_y + sy * scale + yy
                for xx in range(scale):
                    cx = dst_x + sx * scale + xx
                    dst_i = (cy * canvas_width + cx) * 4
                    canvas[dst_i : dst_i + 4] = color


def draw_rect(canvas, canvas_width, canvas_height, x, y, w, h, color):
    r, g, b, a = color
    for py in range(max(0, y), min(canvas_height, y + h)):
        for px in range(max(0, x), min(canvas_width, x + w)):
            i = (py * canvas_width + px) * 4
            canvas[i : i + 4] = bytes((r, g, b, a))


def draw_text(canvas, canvas_width, canvas_height, x, y, text, color=(245, 245, 245, 255), scale=2):
    cursor = x
    text = str(text).upper()
    for ch in text:
        pattern = FONT.get(ch, FONT[" "])
        char_width = max(len(row) for row in pattern)
        for py, row in enumerate(pattern):
            for px, bit in enumerate(row):
                if bit == "1":
                    draw_rect(canvas, canvas_width, canvas_height, cursor + px * scale, y + py * scale, scale, scale, color)
        cursor += (char_width + 1) * scale


def crop_tile(width, rgba, tile_x, tile_y, tile_w=16, tile_h=16):
    start_x = tile_x * tile_w
    start_y = tile_y * tile_h
    out = bytearray(tile_w * tile_h * 4)
    for y in range(tile_h):
        src_i = ((start_y + y) * width + start_x) * 4
        dst_i = y * tile_w * 4
        out[dst_i : dst_i + tile_w * 4] = rgba[src_i : src_i + tile_w * 4]
    return bytes(out)


def dominant_layer(observed_layers):
    if not observed_layers:
        return None, 0, 0.0
    total = sum(int(v) for v in observed_layers.values())
    layer, count = max(observed_layers.items(), key=lambda kv: int(kv[1]))
    return layer, int(count), (int(count) / total if total else 0.0)


def candidate_short_id(candidate_id):
    match = re.match(r"tile_([0-9a-f]+)_", str(candidate_id))
    if match:
        return match.group(1)[:6].upper()
    return str(candidate_id)[-6:].upper()


def tilesheet_family(name):
    stem = Path(str(name)).stem.lower()
    stem = re.sub(r"^(spring|summer|fall|winter)_", "", stem)
    stem = stem.replace("-copy", "").replace("_copy", "")
    return stem


def is_restricted_deepwoods_asset(entry):
    haystack = " ".join(
        str(entry.get(key, ""))
        for key in ("copiedImagePath", "tilesheetName", "sourceMod", "sourceCategory")
    ).lower()
    return any(marker in haystack for marker in RESTRICTED_DEEPWOODS_MARKERS)


def ensure_dirs():
    for path in [SEED_ROOT, DUP_ROOT, REPORTS_ROOT, PREVIEW_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def build_seed_pack(candidates_by_id):
    proposals_doc = load_json(PROPOSALS_PATH)
    evidence_doc = load_json(EVIDENCE_PATH)
    evidence_by_id = {entry["candidateId"]: entry for entry in evidence_doc.get("entries", [])}
    proposals = proposals_doc.get("tags", [])
    pack_entries = []
    for index, proposal in enumerate(sorted(proposals, key=lambda p: (p.get("tilesheetName", ""), p.get("localTileId", 0), p.get("candidateId", "")))):
        cid = proposal["candidateId"]
        candidate = candidates_by_id.get(cid, {})
        observed_layers = candidate.get("observedLayers") or {}
        layer, layer_count, layer_fraction = dominant_layer(observed_layers)
        evidence = evidence_by_id.get(cid, {})
        entry = {
            "candidateId": cid,
            "tilesheetName": proposal.get("tilesheetName"),
            "sourceCategory": proposal.get("sourceCategory"),
            "sourceMod": proposal.get("sourceMod"),
            "copiedImagePath": candidate.get("copiedImagePath"),
            "localTileId": proposal.get("localTileId"),
            "tileX": candidate.get("tileX"),
            "tileY": candidate.get("tileY"),
            "tileWidth": candidate.get("tileWidth", 16),
            "tileHeight": candidate.get("tileHeight", 16),
            "proposedUsageProfile": {
                "profileId": "ground_back",
                "proposedClass": proposal.get("proposedClass"),
                "proposedPurpose": "grass_base" if proposal.get("proposedClass") == "ground_base" else "grass_detail",
                "proposedAllowedLayers": proposal.get("allowedLayers", ["Back"]),
                "proposedCollision": proposal.get("collision", "walkable"),
                "layerRole": "ground",
                "approved": False,
            },
            "observedLayers": observed_layers,
            "observedDominantLayer": layer,
            "observedDominantFraction": round(layer_fraction, 4),
            "observedCountTotal": candidate.get("observedCountTotal", sum(observed_layers.values()) if observed_layers else 0),
            "sourceMapsUsedByCount": len(candidate.get("sourceMapsUsedBy") or []),
            "deepwoodsEvidence": {
                "evidenceType": proposal.get("evidenceType") or evidence.get("evidenceType"),
                "sourceFile": proposal.get("evidenceSourceFile") or evidence.get("evidenceSourceFile"),
                "summary": evidence.get("evidenceSummary") or proposal.get("reason"),
            },
            "moonvillageUsageEvidence": {
                "dominantLayer": layer,
                "dominantLayerCount": layer_count,
                "dominantLayerFraction": round(layer_fraction, 4),
                "mapCount": len(candidate.get("sourceMapsUsedBy") or []),
                "reason": proposal.get("reason"),
            },
            "confidence": proposal.get("confidence"),
            "approved": False,
            "needsHumanReview": True,
            "previewCoordinate": {
                "index": index,
                "column": index % 7,
                "row": index // 7,
            },
        }
        pack_entries.append(entry)
    pack = {
        "generatedAt": now_iso(),
        "reviewPackId": "grass_seed_approval_pack",
        "purpose": "Small human seed set for grass/ground approvals; nothing here is auto-approved.",
        "count": len(pack_entries),
        "usageProfileModel": {
            "supportsMultipleProfilesPerTile": True,
            "conflictRule": "Only conflicting definitions for the same profileId conflict; separate layer-role profiles may coexist.",
            "exampleProfiles": [
                {
                    "profileId": "ground_back",
                    "approvedClass": "ground_base",
                    "approvedPurpose": "grass_ground",
                    "allowedLayers": ["Back"],
                    "collision": "walkable",
                    "layerRole": "ground",
                    "evidence": [],
                    "notes": "",
                },
                {
                    "profileId": "canopy_alwaysfront",
                    "approvedClass": "tree_canopy",
                    "approvedPurpose": "overhead_forest_cover",
                    "allowedLayers": ["AlwaysFront"],
                    "collision": "decorative",
                    "layerRole": "overhead",
                    "evidence": [],
                    "notes": "",
                },
            ],
        },
        "tiles": pack_entries,
    }
    write_json(SEED_ROOT / "grass_seed_approval_pack.json", pack)
    decisions = {
        "reviewPack": "grass_seed_approval_pack",
        "reviewer": "Joel",
        "instructions": "Rename this file to grass_seed_manual_decisions.json after review. Leave decision as unsure unless you explicitly approve or reject the tile.",
        "decisions": [
            {
                "candidateId": entry["candidateId"],
                "decision": "unsure",
                "usageProfiles": [
                    {
                        "profileId": "ground_back",
                        "approvedClass": entry["proposedUsageProfile"]["proposedClass"],
                        "approvedPurpose": entry["proposedUsageProfile"]["proposedPurpose"],
                        "allowedLayers": entry["proposedUsageProfile"]["proposedAllowedLayers"],
                        "collision": entry["proposedUsageProfile"]["proposedCollision"],
                        "layerRole": "ground",
                        "evidence": [
                            "medium_confidence_grass_proposal",
                            "deepwoods_code_corroboration_non_authoritative",
                            "moonvillage_back_layer_usage",
                        ],
                        "notes": "",
                    }
                ],
                "notes": "",
            }
            for entry in pack_entries
        ],
    }
    write_json(SEED_ROOT / "grass_seed_manual_decisions.template.json", decisions)
    return pack


def build_seed_preview(pack):
    entries = pack["tiles"]
    cols = 7
    cell_w = 104
    cell_h = 114
    width = cols * cell_w
    rows = math.ceil(len(entries) / cols) or 1
    height = rows * cell_h
    canvas = bytearray([28, 30, 32, 255] * width * height)
    image_cache = {}
    for entry in entries:
        index = entry["previewCoordinate"]["index"]
        col = index % cols
        row = index // cols
        x0 = col * cell_w
        y0 = row * cell_h
        draw_rect(canvas, width, height, x0 + 2, y0 + 2, cell_w - 4, cell_h - 4, (48, 52, 56, 255))
        path = Path(entry["copiedImagePath"]) if entry.get("copiedImagePath") else None
        try:
            if path not in image_cache:
                image_cache[path] = decode_png_rgba(path)
            img_w, _img_h, rgba = image_cache[path]
            tile = crop_tile(img_w, rgba, int(entry["tileX"]), int(entry["tileY"]), int(entry.get("tileWidth", 16)), int(entry.get("tileHeight", 16)))
            paste_scaled(canvas, width, tile, 16, 16, x0 + 20, y0 + 8, 4)
        except Exception:
            draw_rect(canvas, width, height, x0 + 20, y0 + 8, 64, 64, (110, 45, 45, 255))
        layer = (entry.get("observedDominantLayer") or "UNK")[:4].upper()
        cid = candidate_short_id(entry["candidateId"])
        draw_text(canvas, width, height, x0 + 8, y0 + 76, f"ID{entry.get('localTileId')}", scale=2)
        draw_text(canvas, width, height, x0 + 8, y0 + 88, f"CID{cid}", scale=2)
        draw_text(canvas, width, height, x0 + 8, y0 + 100, layer, color=(160, 220, 170, 255), scale=2)
    write_png_rgba(PREVIEW_ROOT / "grass_seed_approval_preview.png", width, height, canvas)


def hash_tile(tile_rgba):
    exact = hashlib.sha256(tile_rgba).hexdigest()
    rgb = bytearray()
    for i in range(0, len(tile_rgba), 4):
        rgb.extend(tile_rgba[i : i + 3])
    return exact, hashlib.sha256(bytes(rgb)).hexdigest()


def build_hash_index(candidates):
    by_image = defaultdict(list)
    for candidate in candidates:
        if int(candidate.get("tileWidth") or 0) != 16 or int(candidate.get("tileHeight") or 0) != 16:
            continue
        path = candidate.get("copiedImagePath")
        if path:
            by_image[path].append(candidate)

    entries = []
    skipped = []
    hash_counts = Counter()
    images_processed = 0
    for image_index, (image_path, image_candidates) in enumerate(sorted(by_image.items()), start=1):
        path = Path(image_path)
        if not path.exists():
            skipped.append({"copiedImagePath": image_path, "count": len(image_candidates), "reason": "image_missing"})
            continue
        if path.suffix.lower() != ".png":
            skipped.append({"copiedImagePath": image_path, "count": len(image_candidates), "reason": "unsupported_image_format"})
            continue
        try:
            img_w, img_h, rgba = decode_png_rgba(path)
        except Exception as exc:
            skipped.append({"copiedImagePath": image_path, "count": len(image_candidates), "reason": f"png_decode_failed: {exc}"})
            continue
        images_processed += 1
        for candidate in image_candidates:
            tile_x = int(candidate.get("tileX") or 0)
            tile_y = int(candidate.get("tileY") or 0)
            if tile_x * 16 + 16 > img_w or tile_y * 16 + 16 > img_h:
                skipped.append({"candidateId": candidate.get("candidateId"), "copiedImagePath": image_path, "reason": "tile_out_of_bounds"})
                continue
            tile = crop_tile(img_w, rgba, tile_x, tile_y, 16, 16)
            exact, rgb = hash_tile(tile)
            hash_counts[exact] += 1
            entries.append(
                {
                    "hashExact": exact,
                    "hashRgbOnly": rgb,
                    "tilesheetName": candidate.get("tilesheetName"),
                    "copiedImagePath": candidate.get("copiedImagePath"),
                    "sourceCategory": candidate.get("sourceCategory"),
                    "sourceMod": candidate.get("sourceMod"),
                    "localTileId": candidate.get("localTileId"),
                    "candidateId": candidate.get("candidateId"),
                    "tileX": tile_x,
                    "tileY": tile_y,
                    "observedLayers": candidate.get("observedLayers") or {},
                    "observedCountTotal": candidate.get("observedCountTotal", 0),
                    "tilesheetFamily": tilesheet_family(candidate.get("tilesheetName")),
                    "restrictedDeepWoodsAsset": is_restricted_deepwoods_asset(candidate),
                }
            )
        if image_index % 100 == 0:
            print(f"hashed {image_index}/{len(by_image)} images; entries={len(entries)}")

    duplicate_groups = [
        {"hashExact": hash_value, "count": count}
        for hash_value, count in hash_counts.most_common()
        if count > 1
    ]
    doc = {
        "generatedAt": now_iso(),
        "tileSize": {"width": 16, "height": 16},
        "imagesConsidered": len(by_image),
        "imagesProcessed": images_processed,
        "entriesCount": len(entries),
        "skippedCount": len(skipped),
        "exactDuplicateGroupCount": len(duplicate_groups),
        "skipped": skipped[:2000],
        "entries": entries,
        "duplicateHashGroups": duplicate_groups[:5000],
    }
    write_json(DUP_ROOT / "tile_hash_index.json", doc, compact=True)
    return doc


def approved_profile_index(candidates_by_id):
    index = defaultdict(list)
    approved_tag_root = CLASS_ROOT / "approved_tags"
    if not approved_tag_root.exists():
        return index
    for path in sorted(approved_tag_root.glob("*.approved_tags.json")):
        try:
            doc = load_json(path)
        except Exception:
            continue
        tags = doc if isinstance(doc, list) else doc.get("tags", [])
        for tag in tags:
            profiles = tag.get("usageProfiles")
            if not profiles and tag.get("approvedClass"):
                profiles = [
                    {
                        "profileId": tag.get("profileId") or "legacy_default",
                        "approvedClass": tag.get("approvedClass"),
                        "approvedPurpose": tag.get("approvedPurpose"),
                        "allowedLayers": tag.get("allowedLayers") or [],
                        "collision": tag.get("collision", "unknown"),
                        "layerRole": tag.get("layerRole") or "legacy_single_profile",
                    }
                ]
            for cid in tag.get("candidateIds") or []:
                candidate = candidates_by_id.get(cid)
                if not candidate:
                    continue
                local_id = candidate.get("localTileId")
                for profile in profiles or []:
                    index[str(local_id)].append(profile)
    return index


def infer_stylepack_role_layer(group_name, stylepack):
    rules = stylepack.get("layerRules") or {}
    name = group_name.lower()
    if "ground" in name or "path" in name or "sand" in name or "shadow" in name:
        return rules.get("ground", "Back")
    if "body" in name or "blocker" in name:
        return rules.get("blockingBody", "Buildings")
    if "top" in name or "corner" in name or "edge" in name:
        return rules.get("tallOverlay") or rules.get("topEdge", "AlwaysFront")
    if "decoration" in name or "torch" in name:
        return "Front"
    if "filler" in name:
        return rules.get("tallOverlay", "AlwaysFront")
    return "unknown"


def iter_stylepack_tile_uses(stylepack):
    for group_name, values in (stylepack.get("groups") or {}).items():
        if not isinstance(values, list):
            continue
        layer = infer_stylepack_role_layer(group_name, stylepack)
        for value in values:
            if isinstance(value, dict):
                local_id = value.get("localTileId")
                gid = value.get("gid")
                source = value.get("source")
                weight = value.get("weight")
                notes = value.get("notes", "")
            else:
                local_id = None
                gid = value
                source = "semantic_key"
                weight = None
                notes = ""
            yield {
                "role": group_name,
                "layer": layer,
                "localTileId": local_id,
                "gid": gid,
                "source": source,
                "weight": weight,
                "notes": notes,
            }


def profile_supports_layer(profiles, layer):
    for profile in profiles:
        if layer in set(profile.get("allowedLayers") or []):
            return True
    return False


def build_stylepack_audit(candidates_by_id):
    approved_profiles = approved_profile_index(candidates_by_id)
    marker_gids_by_pack = {}
    risks = []
    suggestions = []
    variant_excesses = []
    multi_layer_tiles = []
    tile_layers_by_pack = defaultdict(lambda: defaultdict(set))

    for style_path in sorted(STYLEPACK_ROOT.glob("*.json")):
        stylepack = load_json(style_path)
        style_id = stylepack.get("stylePackId") or style_path.stem
        max_variants = int((stylepack.get("variantPolicy") or {}).get("maxActiveVariantsPerDesignRole", 4))
        marker_gids = set(int(v) for v in (stylepack.get("markerTiles") or {}).values() if isinstance(v, int))
        marker_gids_by_pack[style_id] = sorted(marker_gids)

        for group_name, values in {**(stylepack.get("groups") or {}), **(stylepack.get("semanticGroups") or {})}.items():
            if isinstance(values, list) and len(values) > max_variants:
                risk = {
                    "stylepack": style_path.name,
                    "stylePackId": style_id,
                    "role": group_name,
                    "risk": "design_role_exceeds_active_variant_limit",
                    "activeVariantCount": len(values),
                    "limit": max_variants,
                }
                risks.append(risk)
                variant_excesses.append(risk)
                suggestions.append(
                    {
                        "stylepackFile": style_path.name,
                        "tileId": None,
                        "currentRole": group_name,
                        "currentLayer": infer_stylepack_role_layer(group_name, stylepack),
                        "risk": risk["risk"],
                        "missingOrConflictingUsageProfile": None,
                        "suggestedAction": "reduce_active_variants_to_4",
                        "reason": f"{group_name} has {len(values)} active variants; variantPolicy allows {max_variants}.",
                    }
                )

        for use in iter_stylepack_tile_uses(stylepack):
            local_id = use.get("localTileId")
            gid = use.get("gid")
            role = use.get("role")
            layer = use.get("layer")
            tile_key = str(local_id if local_id is not None else gid)
            tile_layers_by_pack[style_path.name][tile_key].add(layer)
            profiles = approved_profiles.get(str(local_id), []) if local_id is not None else []
            is_marker = isinstance(gid, int) and gid in marker_gids
            risk_reasons = []
            actions = []
            if local_id == 946 or gid == 947:
                risk_reasons.append("tile_946_profile_specific_risk")
                actions.extend(["create_separate_usage_profile", "keep_as_prototype_only"])
            if not is_marker and not profiles and isinstance(gid, int):
                risk_reasons.append("stylepack_tile_without_approved_usage_profile")
                actions.append("require_human_review")
            if use.get("source") == "deepwoods_derived_reviewed" and not profiles:
                risk_reasons.append("deepwoods_derived_id_without_human_approved_database_support")
                actions.append("keep_as_prototype_only")
            if role and ("body" in role.lower() or "wall" in role.lower()) and layer == "Buildings":
                if not any(profile.get("collision") in {"blocked", "blocks", "blocks_movement"} for profile in profiles):
                    risk_reasons.append("collision_role_without_approved_collision_profile")
                    actions.append("require_human_review")
            if profiles and layer != "unknown" and not profile_supports_layer(profiles, layer):
                risk_reasons.append("stylepack_layer_not_covered_by_existing_usage_profile")
                actions.append("create_separate_usage_profile")
            for reason in sorted(set(risk_reasons)):
                risk = {
                    "stylepack": style_path.name,
                    "stylePackId": style_id,
                    "tileId": local_id,
                    "gid": gid,
                    "role": role,
                    "layer": layer,
                    "source": use.get("source"),
                    "risk": reason,
                    "profilesFound": profiles,
                    "notes": use.get("notes", ""),
                }
                risks.append(risk)
                suggestions.append(
                    {
                        "stylepackFile": style_path.name,
                        "tileId": local_id,
                        "gid": gid,
                        "currentRole": role,
                        "currentLayer": layer,
                        "risk": reason,
                        "missingOrConflictingUsageProfile": "No matching approved usage profile for this role/layer." if not profiles else "Existing profiles do not cover this layer/role.",
                        "suggestedAction": sorted(set(actions))[0] if actions else "require_human_review",
                        "allSuggestedActions": sorted(set(actions)) or ["require_human_review"],
                        "reason": (
                            "Tile 946 must be split into profile-specific AlwaysFront canopy and Buildings blocker candidates before production use."
                            if reason == "tile_946_profile_specific_risk"
                            else "Stylepack use is not backed by a human-approved usage profile yet."
                        ),
                    }
                )

    for style_name, tiles in tile_layers_by_pack.items():
        for tile_key, layers in tiles.items():
            if len(layers) > 1:
                multi_layer_tiles.append({"stylepack": style_name, "tileIdOrGid": tile_key, "layers": sorted(layers)})

    write_json(REVIEW_ROOT / "stylepack_tile_risks.json", {"generatedAt": now_iso(), "risks": risks})
    write_json(REVIEW_ROOT / "stylepack_suggested_fixes.json", {"generatedAt": now_iso(), "suggestedFixes": suggestions})

    lines = [
        "# Stylepack Tile Safety Audit",
        "",
        f"- Generated: {now_iso()}",
        f"- Stylepacks scanned: {len(list(STYLEPACK_ROOT.glob('*.json')))}",
        f"- Risks found: {len(risks)}",
        f"- Suggested fixes: {len(suggestions)}",
        f"- Design roles exceeding 4 active variants: {len(variant_excesses)}",
        f"- Multi-layer tile IDs detected: {len(multi_layer_tiles)}",
        "",
        "## Tile 946",
        "",
        "- Tile 946 is not globally banned.",
        "- It is profile-specific risk: Moonvillage usage suggests an AlwaysFront canopy/overlay profile, while the active stylepack currently uses it as a Buildings blocker/body tile.",
        "- Keep 946 as marker/prototype-only until Joel approves separate `canopy_alwaysfront` and/or `blocking_body_buildings` profiles.",
        "",
        "## Variant Cap",
        "",
        "- All stylepacks now declare `variantPolicy.maxActiveVariantsPerDesignRole = 4`.",
        "- The validator treats any role above that limit as an error.",
        "",
        "## Risk Summary",
    ]
    by_reason = Counter(risk["risk"] for risk in risks)
    lines.extend([f"- {reason}: {count}" for reason, count in sorted(by_reason.items())] or ["- None."])
    lines.extend(["", "## Suggested Fix File", "", "- `tools/tiled-map-assistant/review/stylepack_suggested_fixes.json`"])
    (REPORTS_ROOT / "stylepack_tile_safety_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "riskCount": len(risks),
        "suggestionCount": len(suggestions),
        "variantExcessCount": len(variant_excesses),
        "multiLayerTiles": multi_layer_tiles,
    }


def write_seed_instructions(pack, hash_index_doc, stylepack_audit):
    lines = [
        "# Grass Seed Approval Instructions",
        "",
        "This pack contains the 49 medium-confidence grass proposals only. None are approved.",
        "",
        "## How To Review",
        "",
        "1. Open `previews/seed_approval/grass_seed_approval_preview.png`.",
        "2. Use `review/seed_approval/grass_seed_approval_pack.json` for the full candidate IDs and evidence.",
        "3. Copy `grass_seed_manual_decisions.template.json` to `grass_seed_manual_decisions.json` when ready to record decisions.",
        "4. Change only tiles you are confident about from `unsure` to `approve` or `reject`.",
        "5. Keep approved profiles profile-specific. A tile can later receive another profile without invalidating the first.",
        "",
        "## Usage Profile Rules",
        "",
        "- Valid multi-use: `ground_back` as walkable Back ground plus `canopy_alwaysfront` as decorative AlwaysFront canopy.",
        "- Conflict: the same `profileId` claiming incompatible collision or layers.",
        "- Tile 946 must stay profile-specific and prototype-only until separately approved.",
        "",
        "## Current Counts",
        "",
        f"- Seed proposals prepared: {pack['count']}",
        f"- Hash index entries: {hash_index_doc['entriesCount']}",
        f"- Exact duplicate hash groups found: {hash_index_doc['exactDuplicateGroupCount']}",
        f"- Stylepack risks found: {stylepack_audit['riskCount']}",
    ]
    (REPORTS_ROOT / "grass_seed_approval_instructions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(pack, hash_index_doc, stylepack_audit):
    duplicate_matches_path = DUP_ROOT / "duplicate_tile_matches.json"
    duplicate_conflicts_path = DUP_ROOT / "duplicate_tile_conflicts.json"
    matches_count = 0
    conflicts_count = 0
    if duplicate_matches_path.exists():
        matches_count = len(load_json(duplicate_matches_path).get("matches", []))
    if duplicate_conflicts_path.exists():
        conflicts_count = len(load_json(duplicate_conflicts_path).get("conflicts", []))
    lines = [
        "# Seed Duplicate Expansion Summary",
        "",
        f"- Generated: {now_iso()}",
        f"- Seed proposals reviewed/prepared: {pack['count']}",
        "- Usage profile model changes: validators and merge scripts now support multiple `usageProfiles` per tile.",
        f"- Hash-index tile count: {hash_index_doc['entriesCount']}",
        f"- Exact duplicate groups found: {hash_index_doc['exactDuplicateGroupCount']}",
        f"- Duplicate candidates proposed: {matches_count}",
        f"- Duplicate conflicts found: {conflicts_count}",
        f"- Multi-layer tiles detected in stylepacks: {len(stylepack_audit['multiLayerTiles'])}",
        f"- Stylepack risks found: {stylepack_audit['riskCount']}",
        f"- Design roles exceeding 4 active variants: {stylepack_audit['variantExcessCount']}",
        "",
        "## Tile 946 Recommendation",
        "",
        "Do not globally ban tile 946. Treat it as profile-specific risk: keep the current Buildings blocker/body usage as prototype-only, and create separate review profiles for `canopy_alwaysfront` and `blocking_body_buildings` before production generation uses it.",
        "",
        "## Next Mission Recommendation",
        "",
        "Have Joel approve a tiny seed set from `grass_seed_manual_decisions.template.json`, then run `build_duplicate_tile_matches.py` and `validate_duplicate_tile_matches.py` again. Only after validation should duplicate proposals be considered for merge.",
    ]
    (REPORTS_ROOT / "seed_duplicate_expansion_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ensure_dirs()
    print("loading canonical candidates")
    candidates = load_json(CANONICAL_PATH)
    candidates_by_id = {candidate["candidateId"]: candidate for candidate in candidates if candidate.get("candidateId")}
    print(f"loaded {len(candidates)} canonical candidates")

    pack = build_seed_pack(candidates_by_id)
    build_seed_preview(pack)
    hash_index_doc = build_hash_index(candidates)
    stylepack_audit = build_stylepack_audit(candidates_by_id)
    write_seed_instructions(pack, hash_index_doc, stylepack_audit)
    write_summary(pack, hash_index_doc, stylepack_audit)
    print(f"seed proposals: {pack['count']}")
    print(f"hash entries: {hash_index_doc['entriesCount']}")
    print(f"stylepack risks: {stylepack_audit['riskCount']}")


if __name__ == "__main__":
    main()
