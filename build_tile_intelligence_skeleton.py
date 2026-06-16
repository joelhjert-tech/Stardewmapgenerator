import base64
import csv
import hashlib
import json
import re
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


TOOL_ROOT = Path(__file__).resolve().parent
MISSION_ROOT = TOOL_ROOT / "mission_assets"
DATABASE_ROOT = TOOL_ROOT / "database"
REPORTS_ROOT = TOOL_ROOT / "reports"
PREVIEWS_ROOT = TOOL_ROOT / "previews"
WORKING_ROOT = TOOL_ROOT / "working"

IMAGE_EXTS = {".png", ".ase", ".aseprite", ".bmp", ".jpg", ".jpeg"}
GID_MASK = 0x1FFFFFFF


def ensure_dirs():
    for path in [
        DATABASE_ROOT,
        REPORTS_ROOT,
        PREVIEWS_ROOT,
        PREVIEWS_ROOT / "tilesheets",
        WORKING_ROOT,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def short_hash(value):
    return hashlib.sha1(str(value).encode("utf-8", errors="ignore")).hexdigest()[:12]


def norm_path(value):
    return str(value or "").replace("/", "\\").strip().lower()


def path_leaf(value):
    return Path(str(value).replace("\\", "/")).name.lower()


def safe_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except Exception:
        return default


def properties_from_xml(node):
    props = {}
    props_node = node.find("properties") if node is not None else None
    if props_node is None:
        return props
    for prop in props_node.findall("property"):
        name = prop.get("name")
        if not name:
            continue
        props[name] = prop.get("value") if prop.get("value") is not None else (prop.text or "")
    return props


def has_warp_props(props):
    pattern = re.compile(r"warp|door|destination|exit|location", re.I)
    return any(pattern.search(str(k)) or pattern.search(str(v)) for k, v in props.items())


def decode_data(data_node):
    if data_node is None:
        return []
    encoding = data_node.get("encoding")
    compression = data_node.get("compression")
    text = "".join(data_node.itertext()).strip()
    if not text:
        return []
    if encoding == "csv":
        return [int(x) for x in re.split(r"[,\s]+", text) if x.isdigit()]
    if encoding == "base64":
        raw = base64.b64decode(re.sub(r"\s+", "", text))
        if compression == "zlib":
            raw = zlib.decompress(raw)
        elif compression == "gzip":
            raw = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
        elif compression:
            raise ValueError(f"unsupported compression {compression}")
        return list(struct.unpack("<" + "I" * (len(raw) // 4), raw))
    raise ValueError(f"unsupported encoding {encoding}")


def get_image_size(path):
    try:
        with open(path, "rb") as f:
            header = f.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return struct.unpack(">II", header[16:24])
        if header[:2] == b"BM":
            return struct.unpack("<II", header[18:26])
    except Exception:
        pass
    return None, None


def evidence_label(layer_counts):
    total = sum(layer_counts.values())
    if total <= 0:
        return "unknown", 0.0, "No non-empty layer observations."
    groups = {
        "likely_ground_or_floor": ["back", "paths", "path", "floor", "ground"],
        "likely_wall_or_blocker": ["buildings", "building", "walls", "wall", "collision"],
        "likely_front_decoration": ["front", "alwaysfront", "always front", "foreground"],
        "likely_object_or_furniture": ["furniture", "objects", "object", "decor", "interior"],
        "likely_transition_candidate": ["paths", "path", "water", "bridge", "edge", "transition"],
    }
    best_label, best_count = "unknown", 0
    for label, words in groups.items():
        count = 0
        for layer, value in layer_counts.items():
            lower = layer.lower()
            if any(word == lower or word in lower for word in words):
                count += value
        if count > best_count:
            best_label, best_count = label, count
    if best_count == 0:
        return "unknown", 0.2, "Layer usage is mixed or does not match known Stardew layer naming conventions."
    ratio = best_count / total
    return best_label, round(min(0.85, 0.35 + ratio * 0.45), 3), f"Most observations are on layer names associated with {best_label}."


def vanilla_reference(ref):
    leaf = path_leaf(ref)
    vanilla = {
        "paths.png",
        "springobjects.png",
        "towninterior.png",
        "towninterior_2.png",
        "walls_and_floors.png",
        "cave.png",
        "mine.png",
        "mine_dark.png",
        "mine_dangerous.png",
        "volcano_dungeon.png",
        "volcano_caldera.png",
        "island_tilesheet_1.png",
        "outdoors.png",
        "outdoors2.png",
        "deserttiles.png",
        "festivals.png",
        "bathhouse_tiles.png",
    }
    return leaf in vanilla or norm_path(ref).startswith(("mines\\", "maps\\"))


def dependency_status(original_path, plan_by_file):
    entries = plan_by_file.get(original_path.lower(), [])
    classes = {entry.get("classification") for entry in entries}
    if "true_missing" in classes:
        return "has_true_missing_refs"
    if "likely_path_error" in classes:
        return "ambiguous_refs"
    if "external_mod_asset" in classes:
        return "needs_external_mod_assets"
    if "external_vanilla_asset" in classes:
        return "needs_vanilla_assets"
    return "fully_local"


def learning_priority(source_category, parse_status, dep_status, true_missing_count, ambiguous_count):
    if parse_status != "parsed" or true_missing_count > 5 or dep_status == "has_true_missing_refs":
        return "exclude"
    if source_category == "moonvillage" and dep_status in {"fully_local", "needs_vanilla_assets"}:
        return "high"
    if dep_status == "fully_local":
        return "high"
    if dep_status == "needs_vanilla_assets":
        return "medium"
    if dep_status == "ambiguous_refs" or ambiguous_count:
        return "low"
    return "low"


def resolve_image(ref, map_file, by_filename):
    leaf = path_leaf(ref)
    if not leaf:
        return None
    candidates = [
        item
        for item in by_filename.get(leaf, [])
        if item.get("fileType") == "tilesheet"
        and item.get("sourceCategory") == map_file.get("sourceCategory")
        and item.get("sourceMod") == map_file.get("sourceMod")
    ]
    if not candidates:
        candidates = [item for item in by_filename.get(leaf, []) if item.get("fileType") == "tilesheet"]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ref_key = norm_path(ref)
        suffix = [c for c in candidates if norm_path(c.get("normalizedRelativePath", "")).endswith(ref_key)]
        return suffix[0] if len(suffix) == 1 else candidates[0]
    return None


def resolve_gid(gid, tilesets):
    clean = gid & GID_MASK
    if clean == 0:
        return None, 0, 0
    match = None
    for ts in tilesets:
        if ts["firstgid"] <= clean:
            match = ts
        else:
            break
    if not match:
        return None, clean, clean
    return match, clean - match["firstgid"], clean


def add_tile_obs(tile_usage, tile_key, obs):
    entry = tile_usage.setdefault(
        tile_key,
        {
            "tileKey": tile_key,
            "sourceCategory": obs["sourceCategory"],
            "sourceMod": obs["sourceMod"],
            "tilesetName": obs["tilesetName"],
            "imageName": obs["imageName"],
            "localTileId": obs["localTileId"],
            "globalTileIdsUsed": Counter(),
            "copiedImagePath": obs["copiedImagePath"],
            "sourceMapsUsedBy": Counter(),
            "observedLayers": Counter(),
            "observedCount": 0,
            "coordinateExamples": [],
            "nearEdgeCount": 0,
            "nearWarpLayerCount": 0,
            "neighborCounts": Counter(),
            "existingProperties": {},
            "existingTerrainData": [],
            "existingWangData": [],
        },
    )
    entry["observedCount"] += 1
    entry["globalTileIdsUsed"][str(obs["globalTileId"])] += 1
    entry["sourceMapsUsedBy"][obs["mapId"]] += 1
    entry["observedLayers"][obs["layerName"]] += 1
    if len(entry["coordinateExamples"]) < 12:
        entry["coordinateExamples"].append({"mapId": obs["mapId"], "layer": obs["layerName"], "x": obs["x"], "y": obs["y"]})
    if obs["nearEdge"]:
        entry["nearEdgeCount"] += 1
    if obs["nearWarpLayer"]:
        entry["nearWarpLayerCount"] += 1


def add_neighbors(tile_usage, cell_keys, width, height):
    for idx, tile_key in enumerate(cell_keys):
        if not tile_key:
            continue
        x, y = idx % width, idx // width
        entry = tile_usage.get(tile_key)
        if not entry:
            continue
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                neighbor = cell_keys[ny * width + nx]
                if neighbor:
                    entry["neighborCounts"][neighbor] += 1


def parse_tmx(map_file, by_filename, tile_usage, tilesheet_usage):
    tree = ET.parse(map_file["copiedPath"])
    root = tree.getroot()
    map_width = safe_int(root.get("width"))
    map_height = safe_int(root.get("height"))
    tile_width = safe_int(root.get("tilewidth"))
    tile_height = safe_int(root.get("tileheight"))
    props = properties_from_xml(root)
    warp_props = props.copy() if has_warp_props(props) else {}
    tilesets = []
    tilesets_referenced = []
    for ts in root.findall("tileset"):
        image_node = ts.find("image")
        image_source = image_node.get("source") if image_node is not None else None
        image_entry = resolve_image(image_source, map_file, by_filename) if image_source else None
        ts_obj = {
            "firstgid": safe_int(ts.get("firstgid"), 1),
            "name": ts.get("name") or Path(str(ts.get("source") or "")).stem,
            "source": ts.get("source"),
            "imageSource": image_source,
            "imagePath": image_entry.get("copiedPath") if image_entry else None,
            "tileWidth": safe_int(ts.get("tilewidth"), tile_width),
            "tileHeight": safe_int(ts.get("tileheight"), tile_height),
            "tileCount": safe_int(ts.get("tilecount")),
            "columns": safe_int(ts.get("columns")),
            "imageWidth": safe_int(image_node.get("width")) if image_node is not None else None,
            "imageHeight": safe_int(image_node.get("height")) if image_node is not None else None,
        }
        tilesets.append(ts_obj)
        tilesets_referenced.append(ts_obj)
    tilesets.sort(key=lambda x: x["firstgid"])
    layer_names, layer_types, object_layers, image_layers, layer_summaries = [], [], [], [], []
    map_id = f"{short_hash(map_file['copiedPath'])}_{Path(map_file['fileName']).stem}"
    for image_layer in root.findall("imagelayer"):
        layer_names.append(image_layer.get("name"))
        layer_types.append("imagelayer")
        img_node = image_layer.find("image")
        image_layers.append({"name": image_layer.get("name"), "source": img_node.get("source") if img_node is not None else None})
    for object_group in root.findall("objectgroup"):
        name = object_group.get("name")
        layer_names.append(name)
        layer_types.append("objectgroup")
        object_layers.append(name)
    for layer in root.findall("layer"):
        name = layer.get("name") or ""
        layer_names.append(name)
        layer_types.append("tilelayer")
        layer_props = properties_from_xml(layer)
        if has_warp_props(layer_props):
            warp_props[name] = layer_props
        gids = decode_data(layer.find("data"))
        width = safe_int(layer.get("width"), map_width) or map_width or 0
        height = safe_int(layer.get("height"), map_height) or map_height or 0
        non_zero = 0
        unique = set()
        cell_keys = [None] * len(gids)
        for i, gid in enumerate(gids):
            clean = gid & GID_MASK
            if clean == 0:
                continue
            non_zero += 1
            x, y = i % width, i // width
            ts, local_id, clean_gid = resolve_gid(clean, tilesets)
            image_name = Path(ts["imageSource"]).name if ts and ts.get("imageSource") else (ts["name"] if ts else "unresolved_gid")
            image_path = ts.get("imagePath") if ts else None
            tile_key = f"{image_path.lower()}#{local_id}" if image_path else f"{map_file['sourceCategory']}|{map_file['sourceMod']}|{image_name}#{local_id}"
            cell_keys[i] = tile_key
            unique.add(tile_key)
            if image_path:
                tilesheet_usage[image_path] += 1
            add_tile_obs(
                tile_usage,
                tile_key,
                {
                    "sourceCategory": map_file["sourceCategory"],
                    "sourceMod": map_file["sourceMod"],
                    "tilesetName": ts["name"] if ts else "unresolved",
                    "imageName": image_name,
                    "localTileId": local_id,
                    "globalTileId": clean_gid,
                    "copiedImagePath": image_path,
                    "mapId": map_id,
                    "layerName": name,
                    "x": x,
                    "y": y,
                    "nearEdge": x <= 1 or y <= 1 or x >= width - 2 or y >= height - 2,
                    "nearWarpLayer": bool(re.search(r"warp|door|path", name, re.I)),
                },
            )
        add_neighbors(tile_usage, cell_keys, width, height)
        layer_summaries.append({"layerName": name, "nonZeroTiles": non_zero, "uniqueTiles": len(unique)})
    return {
        "mapWidth": map_width,
        "mapHeight": map_height,
        "tileWidth": tile_width,
        "tileHeight": tile_height,
        "layerNames": layer_names,
        "layerTypes": layer_types,
        "objectLayerNames": object_layers,
        "tilesetsReferenced": tilesets_referenced,
        "imageLayers": image_layers,
        "mapProperties": props,
        "warpRelatedProperties": warp_props,
        "customProperties": props,
        "layerSummaries": layer_summaries,
    }


def main():
    ensure_dirs()
    inventory = load_json(MISSION_ROOT / "reports" / "asset_inventory.json")
    reference_index = load_json(DATABASE_ROOT / "asset_reference_index.json")
    repair_plan = load_json(REPORTS_ROOT / "reference_repair_plan.json")
    (REPORTS_ROOT / "reference_audit_summary.md").read_text(encoding="utf-8")
    (REPORTS_ROOT / "unresolved_references.md").read_text(encoding="utf-8")

    files = inventory["files"]
    index_files = reference_index["files"]
    by_filename = defaultdict(list)
    for item in index_files:
        by_filename[item["fileName"].lower()].append(item)
    plan_by_file = defaultdict(list)
    for entry in repair_plan["entries"]:
        plan_by_file[entry["referencingFile"].lower()].append(entry)

    map_files = [f for f in files if f.get("fileType") == "map" and f.get("extension") in {".tmx", ".tmj"}]
    image_files = [f for f in files if f.get("fileType") == "tilesheet" and f.get("extension") in IMAGE_EXTS]
    tsx_files = [f for f in files if f.get("fileType") == "tileset"]

    map_catalog = []
    tile_usage = {}
    tilesheet_usage = Counter()
    layer_usage_by_map = {}

    for map_file in map_files:
        map_id = f"{short_hash(map_file['copiedPath'])}_{Path(map_file['fileName']).stem}"
        plan_items = plan_by_file.get(map_file["originalPath"].lower(), [])
        true_missing = sum(1 for p in plan_items if p.get("classification") == "true_missing")
        ambiguous = sum(1 for p in plan_items if p.get("classification") == "likely_path_error")
        dep = dependency_status(map_file["originalPath"], plan_by_file)
        record = {
            "mapId": map_id,
            "sourceCategory": map_file["sourceCategory"],
            "sourceMod": map_file["sourceMod"],
            "originalPath": map_file["originalPath"],
            "copiedPath": map_file["copiedPath"],
            "mapFormat": map_file["extension"].lstrip("."),
            "mapWidth": None,
            "mapHeight": None,
            "tileWidth": None,
            "tileHeight": None,
            "layerNames": [],
            "layerTypes": [],
            "objectLayerNames": [],
            "tilesetsReferenced": [],
            "imageLayers": [],
            "mapProperties": {},
            "warpRelatedProperties": {},
            "customProperties": {},
            "parseStatus": "failed",
            "dependencyStatus": dep,
            "learningPriority": "exclude",
            "notes": "",
        }
        try:
            if map_file["extension"] == ".tmx":
                parsed = parse_tmx(map_file, by_filename, tile_usage, tilesheet_usage)
            else:
                raise ValueError("TMJ parser not needed for current copied set")
            for key, value in parsed.items():
                if key != "layerSummaries":
                    record[key] = value
            record["parseStatus"] = "parsed"
            record["learningPriority"] = learning_priority(record["sourceCategory"], "parsed", dep, true_missing, ambiguous)
            record["notes"] = "Parsed; dependency status from Mission 2 repair plan. Layer usage extracted without visual classification."
            layer_usage_by_map[map_id] = parsed["layerSummaries"]
        except Exception as exc:
            record["notes"] = f"Parse failed: {exc}"
            record["learningPriority"] = "exclude"
        map_catalog.append(record)

    tileset_catalog = []
    for tsx in tsx_files:
        entry = {
            "tilesetId": f"{short_hash(tsx['copiedPath'])}_{Path(tsx['fileName']).stem}",
            "sourceCategory": tsx["sourceCategory"],
            "sourceMod": tsx["sourceMod"],
            "originalPath": tsx["originalPath"],
            "copiedPath": tsx["copiedPath"],
            "imagePath": None,
            "tileWidth": None,
            "tileHeight": None,
            "imageWidth": None,
            "imageHeight": None,
            "columns": None,
            "tileCount": None,
            "hasTSXMetadata": True,
            "hasTileProperties": False,
            "hasObjectGroups": False,
            "hasTerrainSets": False,
            "hasWangSets": False,
            "usedByMaps": 0,
            "commonLayerUsage": {},
            "dependencyStatus": "fully_local",
            "classificationStatus": "unclassified",
            "notes": "External TSX metadata found.",
        }
        try:
            root = ET.parse(tsx["copiedPath"]).getroot()
            entry["tileWidth"] = safe_int(root.get("tilewidth"))
            entry["tileHeight"] = safe_int(root.get("tileheight"))
            entry["columns"] = safe_int(root.get("columns"))
            entry["tileCount"] = safe_int(root.get("tilecount"))
            image = root.find("image")
            if image is not None:
                img = resolve_image(image.get("source"), tsx, by_filename)
                entry["imagePath"] = img.get("copiedPath") if img else None
                entry["imageWidth"] = safe_int(image.get("width"))
                entry["imageHeight"] = safe_int(image.get("height"))
            entry["hasTileProperties"] = root.find("tile/properties") is not None
            entry["hasObjectGroups"] = root.find("tile/objectgroup") is not None
            entry["hasTerrainSets"] = root.find("terraintypes") is not None
            entry["hasWangSets"] = root.find("wangsets") is not None
            entry["usedByMaps"] = tilesheet_usage.get(entry["imagePath"], 0) if entry["imagePath"] else 0
        except Exception:
            pass
        tileset_catalog.append(entry)

    for img in image_files:
        width, height = get_image_size(img["copiedPath"])
        columns = width // 16 if width else None
        tile_count = columns * (height // 16) if columns and height else None
        layer_counts = Counter()
        for usage in tile_usage.values():
            if usage["copiedImagePath"] == img["copiedPath"]:
                layer_counts.update(usage["observedLayers"])
        used = tilesheet_usage.get(img["copiedPath"], 0)
        tileset_catalog.append(
            {
                "tilesetId": f"{short_hash(img['copiedPath'])}_{Path(img['fileName']).stem}",
                "sourceCategory": img["sourceCategory"],
                "sourceMod": img["sourceMod"],
                "originalPath": img["originalPath"],
                "copiedPath": img["copiedPath"],
                "imagePath": img["copiedPath"],
                "tileWidth": 16,
                "tileHeight": 16,
                "imageWidth": width,
                "imageHeight": height,
                "columns": columns,
                "tileCount": tile_count,
                "hasTSXMetadata": False,
                "hasTileProperties": False,
                "hasObjectGroups": False,
                "hasTerrainSets": False,
                "hasWangSets": False,
                "usedByMaps": used,
                "commonLayerUsage": dict(layer_counts),
                "dependencyStatus": "observed_local" if used else "not_observed_in_parseable_maps",
                "classificationStatus": "unclassified",
                "notes": "Image-only tilesheet; no TSX metadata invented.",
            }
        )

    layer_usage_index = []
    tile_database = []
    for usage in tile_usage.values():
        label, confidence, reason = evidence_label(usage["observedLayers"])
        neighbors = [{"tileKey": k, "count": v} for k, v in usage["neighborCounts"].most_common(20)]
        layer_usage_index.append(
            {
                "tileKey": usage["tileKey"],
                "copiedImagePath": usage["copiedImagePath"],
                "sourceCategory": usage["sourceCategory"],
                "sourceMod": usage["sourceMod"],
                "tilesetName": usage["tilesetName"],
                "imageName": usage["imageName"],
                "localTileId": usage["localTileId"],
                "observedLayers": dict(usage["observedLayers"]),
                "observedCount": usage["observedCount"],
                "coordinateExamples": usage["coordinateExamples"],
                "nearMapEdgeCount": usage["nearEdgeCount"],
                "nearDoorOrWarpLayerCount": usage["nearWarpLayerCount"],
                "commonNeighbors": neighbors,
                "evidenceLabel": label,
                "confidence": confidence,
                "reason": reason,
            }
        )
        tile_database.append(
            {
                "sourceCategory": usage["sourceCategory"],
                "sourceMod": usage["sourceMod"],
                "tilesetName": usage["tilesetName"],
                "imageName": usage["imageName"],
                "localTileId": usage["localTileId"],
                "globalTileIdsUsed": dict(usage["globalTileIdsUsed"]),
                "copiedImagePath": usage["copiedImagePath"],
                "sourceMapsUsedBy": list(usage["sourceMapsUsedBy"].keys()),
                "observedLayers": dict(usage["observedLayers"]),
                "observedCount": usage["observedCount"],
                "neighborEvidence": neighbors,
                "existingProperties": usage["existingProperties"],
                "existingTerrainData": usage["existingTerrainData"],
                "existingWangData": usage["existingWangData"],
                "evidenceLabel": label,
                "confidence": confidence,
                "approved": False,
                "needsHumanReview": True,
                "finalClass": None,
                "allowedLayers": [],
                "collision": "unknown",
                "purpose": "unknown",
                "notes": "Skeleton entry from parsed map layer usage only; no visual classification.",
            }
        )

    write_json(DATABASE_ROOT / "map_catalog.json", map_catalog)
    write_json(DATABASE_ROOT / "tileset_catalog.json", tileset_catalog)
    write_json(DATABASE_ROOT / "layer_usage_index.json", layer_usage_index)
    write_json(DATABASE_ROOT / "tile_database_skeleton.json", tile_database)

    preview_candidates = sorted(
        [t for t in tileset_catalog if t.get("imagePath") and Path(t["imagePath"]).exists()],
        key=lambda t: (0 if t["sourceCategory"] == "moonvillage" else 1, -int(t.get("usedByMaps") or 0)),
    )[:40]
    write_json(WORKING_ROOT / "preview_candidates.json", preview_candidates)

    def count_by(items, key):
        c = Counter(item.get(key) for item in items)
        return c

    parsed_count = sum(1 for m in map_catalog if m["parseStatus"] == "parsed")
    summary = [
        "# Mission 3 Tile Intelligence Summary",
        "",
        f"- Total maps scanned: {len(map_catalog)}",
        f"- Total maps parsed successfully: {parsed_count}",
        f"- Failed maps: {len(map_catalog) - parsed_count}",
        "",
        "## Maps By Dependency Status",
    ]
    summary += [f"- {k}: {v}" for k, v in sorted(count_by(map_catalog, "dependencyStatus").items())]
    summary += ["", "## Maps By Learning Priority"]
    summary += [f"- {k}: {v}" for k, v in sorted(count_by(map_catalog, "learningPriority").items())]
    summary += [
        "",
        f"- Total tilesheets/images cataloged: {len(tileset_catalog)}",
        f"- Tilesets with TSX metadata: {sum(1 for t in tileset_catalog if t.get('hasTSXMetadata'))}",
        f"- Tilesheets without TSX metadata: {sum(1 for t in tileset_catalog if not t.get('hasTSXMetadata'))}",
        f"- Total unique tile IDs observed: {len(tile_database)}",
        "",
        "## Recommended Next Mission",
        "Review high- and medium-priority maps, then manually approve a small set of tilesheet previews before assigning final tile purposes.",
    ]
    (REPORTS_ROOT / "mission_3_tile_intelligence_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    usable = ["# Usable Maps Report", ""]
    for priority in ["high", "medium", "low", "exclude"]:
        subset = [m for m in map_catalog if m["learningPriority"] == priority]
        usable += [f"## {priority}"]
        for m in subset[:250]:
            usable.append(f"- {m['sourceCategory']} / {m['sourceMod']} / {m['mapId']}: {m['dependencyStatus']} - {m['notes']}")
            usable.append(f"  - {m['copiedPath']}")
        if len(subset) > 250:
            usable.append(f"- ... {len(subset) - 250} more omitted from Markdown; see map_catalog.json.")
        usable.append("")
    (REPORTS_ROOT / "usable_maps_report.md").write_text("\n".join(usable), encoding="utf-8")

    priority = ["# Tilesheet Priority Report", "", "## Most-Used Tilesheets"]
    for t in sorted([t for t in tileset_catalog if t.get("imagePath")], key=lambda x: -(x.get("usedByMaps") or 0))[:50]:
        priority.append(f"- {t.get('usedByMaps', 0)} uses: {t['sourceCategory']} / {t['sourceMod']} / {Path(t['imagePath']).name}")
        priority.append(f"  - {t['imagePath']}")
    priority += ["", "## Moon Village Tilesheets"]
    for t in sorted([t for t in tileset_catalog if t["sourceCategory"] == "moonvillage"], key=lambda x: -(x.get("usedByMaps") or 0))[:80]:
        priority.append(f"- {t.get('usedByMaps', 0)} uses: {Path(str(t.get('imagePath') or t.get('copiedPath'))).name} - {t['notes']}")
    priority += ["", "## Reference Tilesheets With Strong Map Usage"]
    for t in sorted([t for t in tileset_catalog if t["sourceCategory"] == "reference_mods" and (t.get("usedByMaps") or 0) > 0], key=lambda x: -x["usedByMaps"])[:80]:
        priority.append(f"- {t['usedByMaps']} uses: {t['sourceMod']} / {Path(t['imagePath']).name}")
    priority += ["", "## Tilesheets That Need Manual Tagging First"]
    for t in sorted([t for t in tileset_catalog if (t.get("usedByMaps") or 0) > 0 and not t.get("hasTSXMetadata")], key=lambda x: -x["usedByMaps"])[:80]:
        priority.append(f"- {t['usedByMaps']} uses, no TSX metadata: {t['sourceCategory']} / {t['sourceMod']} / {Path(t['imagePath']).name}")
    priority += ["", "## Tilesheets That Appear Unused"]
    unused = [t for t in tileset_catalog if not t.get("usedByMaps")]
    for t in unused[:120]:
        priority.append(f"- {t['sourceCategory']} / {t['sourceMod']}: {t['copiedPath']}")
    if len(unused) > 120:
        priority.append(f"- ... {len(unused) - 120} more unused entries omitted from Markdown; see tileset_catalog.json.")
    (REPORTS_ROOT / "tilesheet_priority_report.md").write_text("\n".join(priority), encoding="utf-8")

    print(f"Maps scanned: {len(map_catalog)}; parsed: {parsed_count}; failed: {len(map_catalog) - parsed_count}")
    print(f"Tilesheets cataloged: {len(tileset_catalog)}; unique tile entries: {len(tile_database)}")
    print(f"Preview candidates: {len(preview_candidates)}")


if __name__ == "__main__":
    main()
