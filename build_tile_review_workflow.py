import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
DB_ROOT = TOOL_ROOT / "database"
REPORTS_ROOT = TOOL_ROOT / "reports"
CLASS_ROOT = TOOL_ROOT / "classification"
REVIEW_PACK_ROOT = CLASS_ROOT / "review_packs"
MANUAL_TAGS_ROOT = CLASS_ROOT / "manual_tags"
PROPOSED_TAGS_ROOT = CLASS_ROOT / "proposed_tags"
APPROVED_TAGS_ROOT = CLASS_ROOT / "approved_tags"
PREVIEW_REVIEW_ROOT = TOOL_ROOT / "previews" / "review_packs"
WORKING_ROOT = TOOL_ROOT / "working"


def ensure_dirs():
    for path in [
        CLASS_ROOT,
        REVIEW_PACK_ROOT,
        MANUAL_TAGS_ROOT,
        PROPOSED_TAGS_ROOT,
        APPROVED_TAGS_ROOT,
        REPORTS_ROOT,
        PREVIEW_REVIEW_ROOT,
        WORKING_ROOT,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def clear_generated_outputs():
    for folder in [REVIEW_PACK_ROOT, PROPOSED_TAGS_ROOT]:
        for path in folder.glob("*.json"):
            path.unlink()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def short_id(value):
    import hashlib

    return hashlib.sha1(str(value).encode("utf-8", errors="ignore")).hexdigest()[:12]


def safe_name(value, limit=100):
    safe = re.sub(r'[<>:"/\\|?*\s]+', "_", str(value)).strip("_")
    return safe[:limit] or "unnamed"


def image_name(path):
    return Path(str(path or "").replace("\\", "/")).name


def candidate_id(image_path, local_tile_id):
    return f"tile_{short_id(str(image_path).lower() + '#' + str(local_tile_id))}_{local_tile_id}"


def review_pack_id(source_category, source_mod, image_path):
    return f"pack_{short_id(str(image_path).lower())}_{safe_name(source_category)}_{safe_name(source_mod, 36)}_{safe_name(image_name(image_path), 48)}"


def tile_xy(local_tile_id, columns):
    if local_tile_id is None or columns in (None, 0):
        return None, None
    return int(local_tile_id) % int(columns), int(local_tile_id) // int(columns)


def evidence_to_review_mode(layer_counts, tilesheet_name):
    lower_name = tilesheet_name.lower()
    layer_text = " ".join(layer_counts.keys()).lower()
    if any(x in lower_name for x in ["interior", "towninterior", "walls_and_floors", "floor"]):
        return "interior_first"
    if any(x in lower_name for x in ["building", "town", "roof"]):
        return "exterior_first"
    if any(x in lower_name for x in ["shadow", "marker", "warp", "collision"]):
        return "technical_only"
    if any(x in lower_name for x in ["outdoors", "beach", "mine", "cave", "island", "water"]):
        return "terrain_first"
    if any(x in layer_text for x in ["front", "alwaysfront", "furniture", "object"]):
        return "decoration_first"
    return "mixed"


def proposed_class_from_evidence(label):
    mapping = {
        "likely_ground_or_floor": "ground_base",
        "likely_wall_or_blocker": "collision_blocker",
        "likely_front_decoration": "overlay",
        "likely_transition_candidate": "ground_transition",
        "likely_object_or_furniture": "decoration",
    }
    return mapping.get(label)


def make_schema():
    classes = {
        "ground_base": ("Base outdoor terrain tile.", ["Back"], "walkable", True, False, False),
        "ground_transition": ("Outdoor terrain transition or edge tile.", ["Back"], "walkable", True, False, False),
        "path_base": ("Base path tile.", ["Paths", "Back"], "walkable", True, False, False),
        "path_transition": ("Path transition or edge tile.", ["Paths", "Back"], "walkable", True, False, False),
        "water_base": ("Base water tile.", ["Back"], "blocked_or_special", False, True, False),
        "water_transition": ("Water edge or shoreline transition tile.", ["Back"], "blocked_or_special", False, True, False),
        "cliff_base": ("Base cliff/ledge tile.", ["Buildings", "Back"], "blocks", False, True, False),
        "cliff_transition": ("Cliff transition, edge, or corner tile.", ["Buildings", "Back"], "blocks", False, True, False),
        "bridge": ("Bridge tile or bridge part.", ["Buildings", "Back", "Front"], "varies", True, False, False),
        "floor_base": ("Interior floor base tile.", ["Back"], "walkable", True, False, False),
        "floor_trim": ("Interior floor trim or border tile.", ["Back"], "walkable", True, False, True),
        "wall_top": ("Interior wall top tile.", ["Buildings"], "blocks", False, True, False),
        "wall_front": ("Interior wall front tile.", ["Buildings"], "blocks", False, True, False),
        "wall_side": ("Interior wall side tile.", ["Buildings"], "blocks", False, True, False),
        "wall_corner": ("Interior wall corner tile.", ["Buildings"], "blocks", False, True, False),
        "wall_shadow": ("Interior wall shadow tile.", ["Front", "AlwaysFront"], "none", True, False, True),
        "stairs": ("Stairs or step tile.", ["Buildings", "Back"], "varies", True, False, False),
        "rug": ("Rug or mat tile.", ["Back", "Front"], "walkable", True, False, True),
        "interior_decoration": ("Decorative interior tile.", ["Front", "AlwaysFront", "Buildings"], "varies", True, False, True),
        "roof": ("Roof body tile.", ["Buildings", "Front"], "blocks", False, True, False),
        "roof_edge": ("Roof edge or trim tile.", ["Buildings", "Front"], "blocks", False, True, False),
        "exterior_wall": ("Exterior wall tile.", ["Buildings"], "blocks", False, True, False),
        "door": ("Door tile.", ["Buildings", "Front"], "varies", True, False, False),
        "window": ("Window tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "sign": ("Sign tile.", ["Front", "Buildings"], "blocks", False, True, True),
        "chimney": ("Chimney tile.", ["Front", "AlwaysFront"], "blocks", False, True, True),
        "exterior_decoration": ("Exterior decoration tile.", ["Front", "AlwaysFront", "Buildings"], "varies", True, False, True),
        "furniture": ("Furniture tile.", ["Buildings", "Front"], "varies", True, True, True),
        "counter": ("Counter tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "shelf": ("Shelf tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "table": ("Table tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "chair": ("Chair tile.", ["Buildings", "Front"], "varies", True, True, True),
        "bed": ("Bed tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "fireplace": ("Fireplace tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "machine": ("Machine tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "container": ("Container or chest-like tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "lamp": ("Lamp or light fixture tile.", ["Front", "AlwaysFront", "Buildings"], "varies", True, False, True),
        "decoration": ("Generic decoration tile.", ["Front", "AlwaysFront", "Buildings"], "varies", True, False, True),
        "tree_trunk": ("Tree trunk tile.", ["Buildings"], "blocks", False, True, False),
        "tree_canopy": ("Tree canopy tile.", ["Front", "AlwaysFront"], "varies", True, False, True),
        "bush": ("Bush tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "flower": ("Flower tile.", ["Front", "Back"], "walkable", True, False, True),
        "crop": ("Crop tile.", ["Front", "Back"], "varies", True, False, True),
        "grass_detail": ("Grass detail or overlay tile.", ["Front", "Back"], "walkable", True, False, True),
        "rock": ("Rock tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "stump": ("Stump tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "log": ("Log tile.", ["Buildings", "Front"], "blocks", False, True, True),
        "mushroom": ("Mushroom tile.", ["Front", "Buildings"], "varies", True, False, True),
        "collision_blocker": ("Technical or inferred blocker tile.", ["Buildings"], "blocks", False, True, False),
        "warp_marker": ("Warp marker or warp-related tile.", ["Paths", "Back"], "special", True, False, False),
        "npc_marker": ("NPC placement marker.", ["Paths", "Back"], "special", True, False, False),
        "event_marker": ("Event marker tile.", ["Paths", "Back"], "special", True, False, False),
        "light_marker": ("Light marker tile.", ["Front", "AlwaysFront"], "special", True, False, False),
        "shadow": ("Shadow tile.", ["Front", "AlwaysFront"], "none", True, False, True),
        "overlay": ("Generic overlay tile.", ["Front", "AlwaysFront"], "none", True, False, True),
        "unknown": ("Unknown tile class.", [], "unknown", True, True, True),
        "do_not_use": ("Tile should not be used in generated maps.", [], "unknown", False, False, False),
    }
    return {
        name: {
            "description": desc,
            "commonAllowedLayers": layers,
            "commonCollision": collision,
            "canBeWalkable": walkable,
            "canBlockMovement": blocks,
            "canBeDecorative": decorative,
            "requiresHumanApproval": True,
        }
        for name, (desc, layers, collision, walkable, blocks, decorative) in classes.items()
    }


def main():
    ensure_dirs()
    clear_generated_outputs()
    tile_db = load_json(DB_ROOT / "tile_database_skeleton.json")
    tilesets = load_json(DB_ROOT / "tileset_catalog.json")
    maps = load_json(DB_ROOT / "map_catalog.json")
    # Required previous reports are read to keep the workflow tied to prior missions.
    for report in [
        REPORTS_ROOT / "mission_3_tile_intelligence_summary.md",
        REPORTS_ROOT / "usable_maps_report.md",
        REPORTS_ROOT / "tilesheet_priority_report.md",
    ]:
        report.read_text(encoding="utf-8")

    canonical_image_path = {}
    for t in tilesets:
        if t.get("imagePath"):
            canonical_image_path.setdefault(str(t["imagePath"]).lower(), t["imagePath"])
    tileset_by_image = {t.get("imagePath"): t for t in tilesets if t.get("imagePath")}
    high_maps = {m["mapId"] for m in maps if m.get("learningPriority") == "high"}

    grouped = {}
    for tile in tile_db:
        image_path = tile.get("copiedImagePath")
        if not image_path:
            continue
        image_path = canonical_image_path.get(str(image_path).lower(), image_path)
        ts = tileset_by_image.get(image_path, {})
        owner_category = ts.get("sourceCategory") or tile.get("sourceCategory")
        owner_mod = ts.get("sourceMod") or tile.get("sourceMod")
        local_id = tile.get("localTileId")
        key = (owner_category, owner_mod, image_path, local_id)
        columns = ts.get("columns")
        tile_x, tile_y = tile_xy(local_id, columns)
        candidate = grouped.setdefault(
            key,
            {
                "candidateId": candidate_id(image_path, local_id),
                "sourceCategory": owner_category,
                "sourceMod": owner_mod,
                "tilesheetName": image_name(image_path),
                "copiedImagePath": image_path,
                "localTileId": local_id,
                "tileX": tile_x,
                "tileY": tile_y,
                "tileWidth": ts.get("tileWidth") or 16,
                "tileHeight": ts.get("tileHeight") or 16,
                "observedGlobalIds": Counter(),
                "observedCountTotal": 0,
                "observedLayers": Counter(),
                "sourceMapsUsedBy": set(),
                "strongestEvidenceLabel": tile.get("evidenceLabel") or "unknown",
                "evidenceLabels": Counter(),
                "confidenceFromUsage": 0.0,
                "existingProperties": tile.get("existingProperties") or {},
                "existingTerrainData": tile.get("existingTerrainData") or [],
                "existingWangData": tile.get("existingWangData") or [],
                "approved": False,
                "needsHumanReview": True,
                "finalClass": None,
                "finalPurpose": None,
                "allowedLayers": [],
                "collision": "unknown",
                "notes": "Canonical candidate collapsed from usage observations; not approved.",
            },
        )
        candidate["observedCountTotal"] += int(tile.get("observedCount") or 0)
        candidate["observedLayers"].update(tile.get("observedLayers") or {})
        candidate["sourceMapsUsedBy"].update(tile.get("sourceMapsUsedBy") or [])
        candidate["observedGlobalIds"].update(tile.get("globalTileIdsUsed") or {})
        label = tile.get("evidenceLabel") or "unknown"
        candidate["evidenceLabels"][label] += int(tile.get("observedCount") or 0)
        candidate["confidenceFromUsage"] = max(float(candidate["confidenceFromUsage"]), float(tile.get("confidence") or 0.0))

    canonical = []
    by_image = defaultdict(list)
    for c in grouped.values():
        if c["evidenceLabels"]:
            c["strongestEvidenceLabel"] = c["evidenceLabels"].most_common(1)[0][0]
        c["observedLayers"] = dict(c["observedLayers"])
        c["sourceMapsUsedBy"] = sorted(c["sourceMapsUsedBy"])
        c["observedGlobalIds"] = dict(c["observedGlobalIds"])
        c["evidenceLabels"] = dict(c["evidenceLabels"])
        canonical.append(c)
        by_image[c["copiedImagePath"]].append(c)
    canonical.sort(key=lambda x: (x["sourceCategory"], x["sourceMod"], x["tilesheetName"], x["localTileId"] or -1))

    write_json(CLASS_ROOT / "canonical_tile_candidates.json", canonical)
    write_json(CLASS_ROOT / "tile_class_schema.json", make_schema())
    write_json(
        CLASS_ROOT / "manual_tile_tags_template.json",
        {
            "reviewPackId": "",
            "tilesheetName": "",
            "sourceMod": "",
            "tags": [
                {
                    "candidateId": "",
                    "tileRange": "",
                    "approvedClass": "",
                    "approvedPurpose": "",
                    "allowedLayers": [],
                    "collision": "unknown",
                    "terrainSet": None,
                    "terrainA": None,
                    "terrainB": None,
                    "edgeMask": [],
                    "cornerMask": [],
                    "transitionType": None,
                    "footprint": None,
                    "allowedRooms": [],
                    "avoidNear": [],
                    "weight": 1,
                    "notes": "",
                }
            ],
        },
    )

    queue = []
    all_images = {t.get("imagePath") for t in tilesets if t.get("imagePath")}
    all_images.update(by_image.keys())
    all_images.discard(None)

    for image_path in all_images:
        candidates = by_image.get(image_path, [])
        ts = tileset_by_image.get(image_path, {})
        map_counter = Counter()
        layer_counts = Counter()
        high_map_count = 0
        for c in candidates:
            map_counter.update(c["sourceMapsUsedBy"])
            layer_counts.update(c["observedLayers"])
            high_map_count += sum(1 for m in c["sourceMapsUsedBy"] if m in high_maps)
        source_category = candidates[0]["sourceCategory"] if candidates else ts.get("sourceCategory")
        source_mod = candidates[0]["sourceMod"] if candidates else ts.get("sourceMod")
        used = sum(c["observedCountTotal"] for c in candidates)
        candidate_count = len(candidates)
        used_by_map_count = len(map_counter)
        if source_category == "moonvillage" and used > 0:
            priority = "critical"
        elif source_category == "moonvillage":
            priority = "medium"
        elif high_map_count > 500 or used >= 10000 or used_by_map_count >= 10:
            priority = "high"
        elif used > 0:
            priority = "medium"
        else:
            priority = "low"
        if source_category == "moonvillage":
            reason = "Moon Village tilesheet; required for first-pass manual classification even if not yet observed in parsed maps."
        elif high_map_count:
            reason = "Used by high-priority learning maps."
        elif used >= 10000:
            reason = "High observed usage count across parsed maps."
        else:
            reason = "Included for later review based on observed parsed-map usage."
        queue.append(
            {
                "reviewPackId": review_pack_id(source_category, source_mod, image_path),
                "sourceCategory": source_category,
                "sourceMod": source_mod,
                "tilesheetName": image_name(image_path),
                "copiedImagePath": image_path,
                "candidateCount": candidate_count,
                "observedUseCount": used,
                "usedByMapCount": used_by_map_count,
                "priority": priority,
                "reason": reason,
                "suggestedReviewMode": evidence_to_review_mode(layer_counts, image_name(image_path)),
            }
        )
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    queue.sort(key=lambda q: (priority_rank[q["priority"]], 0 if q["sourceCategory"] == "moonvillage" else 1, -q["observedUseCount"]))
    write_json(CLASS_ROOT / "tile_review_queue.json", queue)

    required_images = set()
    required_images.update(t["imagePath"] for t in tilesets if t.get("sourceCategory") == "moonvillage" and t.get("imagePath"))
    ref_queue = [q for q in queue if q["sourceCategory"] == "reference_mods"]
    required_images.update(q["copiedImagePath"] for q in ref_queue[:20])
    required_images.update(q["copiedImagePath"] for q in queue if q["priority"] in {"critical", "high"} and q["observedUseCount"] >= 10000)

    pack_records = []
    proposed_count = 0
    approved_count = 0
    for q in queue:
        image_path = q["copiedImagePath"]
        if image_path not in required_images:
            continue
        pack_candidates = sorted(by_image.get(image_path, []), key=lambda c: (c["localTileId"] is None, c["localTileId"] or 0))
        proposed_groups = Counter(c["strongestEvidenceLabel"] for c in pack_candidates)
        pack = {
            "reviewPackId": q["reviewPackId"],
            "sourceCategory": q["sourceCategory"],
            "sourceMod": q["sourceMod"],
            "tilesheetName": q["tilesheetName"],
            "copiedImagePath": image_path,
            "contactSheetPath": str(PREVIEW_REVIEW_ROOT / (q["reviewPackId"] + ".png")),
            "candidateCount": len(pack_candidates),
            "priority": q["priority"],
            "suggestedReviewMode": q["suggestedReviewMode"],
            "proposedGroups": dict(proposed_groups),
            "candidates": [
                {
                    "candidateId": c["candidateId"],
                    "localTileId": c["localTileId"],
                    "tileX": c["tileX"],
                    "tileY": c["tileY"],
                    "observedLayers": c["observedLayers"],
                    "observedCountTotal": c["observedCountTotal"],
                    "evidenceLabel": c["strongestEvidenceLabel"],
                    "confidenceFromUsage": c["confidenceFromUsage"],
                    "proposedClass": proposed_class_from_evidence(c["strongestEvidenceLabel"]) if c["confidenceFromUsage"] >= 0.75 and c["observedCountTotal"] >= 100 else None,
                    "approvedClass": None,
                    "approvedPurpose": None,
                    "notes": "Usage-evidence suggestion only; requires human approval.",
                }
                for c in pack_candidates
            ],
        }
        write_json(REVIEW_PACK_ROOT / f"{q['reviewPackId']}.json", pack)
        pack_records.append({**q, "contactSheetPath": pack["contactSheetPath"], "packPath": str(REVIEW_PACK_ROOT / f"{q['reviewPackId']}.json")})

        proposed = []
        for c in pack["candidates"]:
            if c["proposedClass"]:
                proposed.append(
                    {
                        "candidateId": c["candidateId"],
                        "localTileId": c["localTileId"],
                        "proposedClass": c["proposedClass"],
                        "approved": False,
                        "source": "usage_evidence",
                        "confidence": c["confidenceFromUsage"],
                        "reason": f"{c['evidenceLabel']} from repeated layer usage; not visually verified.",
                    }
                )
        if proposed:
            proposed_count += len(proposed)
            write_json(PROPOSED_TAGS_ROOT / f"{q['reviewPackId']}_proposed_tags.json", {"reviewPackId": q["reviewPackId"], "approved": False, "tags": proposed})

    write_json(WORKING_ROOT / "review_pack_preview_manifest.json", pack_records)

    html_rows = []
    for p in pack_records:
        rel = Path(p["contactSheetPath"]).name
        html_rows.append(
            f"<tr><td>{html.escape(p['reviewPackId'])}</td><td>{html.escape(p['sourceMod'])}</td><td>{html.escape(p['tilesheetName'])}</td><td>{p['candidateCount']}</td><td>{p['priority']}</td><td><a href=\"{html.escape(rel)}\">preview</a></td></tr>"
        )
    (PREVIEW_REVIEW_ROOT / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Tile Review Packs</title><table border='1'><tr><th>Pack</th><th>Mod</th><th>Tilesheet</th><th>Candidates</th><th>Priority</th><th>Preview</th></tr>"
        + "\n".join(html_rows)
        + "</table>\n",
        encoding="utf-8",
    )

    def report_pack_line(p):
        maps_sample = []
        for c in by_image[p["copiedImagePath"]][:20]:
            maps_sample.extend(c["sourceMapsUsedBy"][:3])
        maps_sample = sorted(set(maps_sample))[:8]
        return [
            f"- {p['reviewPackId']} - {p['sourceCategory']} / {p['sourceMod']} / {p['tilesheetName']}",
            f"  - Candidates: {p['candidateCount']}; uses: {p['observedUseCount']}; maps: {p['usedByMapCount']}; mode: {p['suggestedReviewMode']}",
            f"  - Reason: {p['reason']}",
            f"  - Map sample: {', '.join(maps_sample) if maps_sample else 'none observed'}",
        ]

    summary = [
        "# Mission 4 Tile Review Summary",
        "",
        f"- Total canonical tile candidates created: {len(canonical)}",
        f"- Total tilesheets queued for review: {len(queue)}",
        f"- Total review packs created: {len(pack_records)}",
        f"- Moon Village review packs created: {sum(1 for p in pack_records if p['sourceCategory'] == 'moonvillage')}",
        f"- Reference mod review packs created: {sum(1 for p in pack_records if p['sourceCategory'] == 'reference_mods')}",
        f"- Stardew mod review packs created: {sum(1 for p in pack_records if p['sourceCategory'] == 'stardew_mods')}",
        f"- Proposed tags created: {proposed_count}",
        f"- Approved tags created: {approved_count}",
        "",
        "## Recommended Next Mission",
        "Review critical Moon Village packs in the HTML index and fill manual tag files for a small tilesheet set before importing approved tags.",
    ]
    (REPORTS_ROOT / "mission_4_tile_review_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    top = ["# Top Tilesheets For Classification", "", "## Critical Priority Tilesheets"]
    for p in [x for x in queue if x["priority"] == "critical"][:120]:
        top.extend(report_pack_line(p))
    top += ["", "## High Priority Tilesheets"]
    for p in [x for x in queue if x["priority"] == "high"][:120]:
        top.extend(report_pack_line(p))
    (REPORTS_ROOT / "top_tilesheets_for_classification.md").write_text("\n".join(top) + "\n", encoding="utf-8")

    index = ["# Tile Review Pack Index", ""]
    for p in pack_records:
        index.append(f"- {p['reviewPackId']} | {p['sourceMod']} | {p['tilesheetName']} | {p['candidateCount']} candidates | {p['priority']} | {p['suggestedReviewMode']}")
        index.append(f"  - Preview: {p['contactSheetPath']}")
        index.append(f"  - Pack: {p['packPath']}")
    (REPORTS_ROOT / "tile_review_pack_index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    print(f"Canonical candidates: {len(canonical)}")
    print(f"Queue items: {len(queue)}")
    print(f"Review packs: {len(pack_records)}")
    print(f"Proposed tags: {proposed_count}; approved tags: {approved_count}")


if __name__ == "__main__":
    main()
