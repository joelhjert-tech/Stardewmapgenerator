#!/usr/bin/env python3
"""Mine structural tile candidates from vanilla layer grammar.

This is a review-preparation tool only. It mines evidence from vanilla maps and
metadata, creates role-focused candidate packs, and never approves tiles.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ijson
from PIL import Image, ImageDraw, ImageFont

import tbin_reader as T
from tma_path_helpers import resolve_vanilla_authoritative_index


TOOL_ROOT = Path(__file__).resolve().parent
UNPACKED_BASEGAME = TOOL_ROOT / "mission_assets" / "unpacked_basegame"
STRUCTURAL_ROOT = TOOL_ROOT / "structural_learning"
CANDIDATE_DIR = STRUCTURAL_ROOT / "candidates"
PACK_DIR = STRUCTURAL_ROOT / "review_packs"
PREVIEW_DIR = STRUCTURAL_ROOT / "previews"
EVIDENCE_DIR = STRUCTURAL_ROOT / "evidence"
REPORT_DIR = TOOL_ROOT / "reports"
DATABASE_ROOT = TOOL_ROOT / "database"
CLASS_ROOT = TOOL_ROOT / "classification"
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"

APPROVED_DB = DATABASE_ROOT / "tile_database_v1_human_approved.json"
CANONICAL_CANDIDATES = CLASS_ROOT / "canonical_tile_candidates.json"
READINESS_MATRIX = REPORT_DIR / "production_tile_readiness_matrix.json"

STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
MISSING_ROLES = [
    "path_transition",
    "wall_body",
    "wall_top",
    "wall_corner",
    "wall_edge",
    "canopy_overlay",
    "water_edge",
    "shadow",
]
ROLE_LIMITS = {
    "wall_body": 100,
    "wall_top": 100,
    "wall_corner": 80,
    "wall_edge": 80,
    "canopy_overlay": 80,
    "water_edge": 80,
    "path_transition": 100,
    "shadow": 60,
}
ROLE_CLASS_DEFAULTS = {
    "wall_body": ("wall_body", "structural wall/body blocker", ["Buildings"], "blocked"),
    "wall_top": ("wall_top", "wall top/front overlay", ["Front"], "decorative_front"),
    "wall_corner": ("wall_corner", "wall/corner structural transition", ["Buildings", "Front"], "blocked"),
    "wall_edge": ("wall_side", "wall/edge structural transition", ["Buildings", "Front"], "blocked"),
    "canopy_overlay": ("tree_canopy", "overhead canopy overlay", ["AlwaysFront"], "overlay_only"),
    "water_edge": ("water_transition", "water edge transition", ["Back"], "water_blocked"),
    "path_transition": ("path_transition", "path/ground transition", ["Back"], "walkable"),
    "shadow": ("shadow", "shadow/edge overlay", ["Back", "Front"], "decorative_front"),
}
MARKER_FALLBACKS = {
    "wall_body": "marker_wall_body",
    "wall_top": "marker_wall_top",
    "wall_corner": "marker_corner",
    "wall_edge": "marker_edge",
    "canopy_overlay": "marker_overlay",
    "water_edge": "marker_water",
    "path_transition": "marker_transition",
    "shadow": "marker_transition",
}
WATER_PROP = "Water"
MAX_EXAMPLES = 12


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for path in [STRUCTURAL_ROOT, CANDIDATE_DIR, PACK_DIR, PREVIEW_DIR, EVIDENCE_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def base_key(name: Any) -> str:
    if name is None:
        return "unknown"
    n = str(name).replace("\\", "/").split("/")[-1].lower()
    for suffix in [".png", ".tsx", ".json", ".tbin"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def structural_id(sheet: str, local_id: int) -> str:
    safe = re.sub(r"[^a-z0-9_]+", "_", base_key(sheet))
    return f"structural_vanilla_{safe}_{local_id}"


def tile_key(sheet: str, local_id: int) -> str:
    return f"{base_key(sheet)}:{int(local_id)}"


def add_example(examples: list[dict[str, Any]], item: dict[str, Any], limit: int = MAX_EXAMPLES) -> None:
    if len(examples) < limit:
        examples.append(item)


def top_counter(counter: Counter, limit: int = 20) -> list[dict[str, Any]]:
    return [{"key": str(k), "count": int(v)} for k, v in counter.most_common(limit)]


def load_vanilla_index() -> dict[str, Any]:
    resolved = resolve_vanilla_authoritative_index(TOOL_ROOT)
    if not resolved.get("actualPath"):
        return {"sheets": {}}
    return load_json(Path(resolved["actualPath"]))


def props_for(vanilla_index: dict[str, Any], sheet: str, local_id: int) -> dict[str, Any]:
    return vanilla_index.get("sheets", {}).get(base_key(sheet), {}).get(str(int(local_id)), {}).get("props", {})


def is_water(vanilla_index: dict[str, Any], sheet: str, local_id: int) -> bool:
    props = props_for(vanilla_index, sheet, local_id)
    return WATER_PROP in props and any(str(value).upper() == "T" for value in props.get(WATER_PROP, []))


def infer_map_category(map_name: str) -> str:
    n = map_name.lower()
    if any(word in n for word in ["festival", "fair", "halloween", "christmas", "luau", "jellies", "eggfestival", "flowerfestival", "icefestival", "squidfest", "nightmarket"]):
        return "festival"
    if re.fullmatch(r"\d+", Path(n).stem) or any(word in n for word in ["mine", "skullcave", "volcano", "caldera", "cave"]):
        return "mine"
    if "beach" in n:
        return "beach exterior"
    if any(word in n for word in ["mountain", "railroad", "backwoods", "summit"]):
        return "mountain exterior"
    if any(word in n for word in ["forest", "woods", "witchswamp"]):
        return "forest exterior"
    if any(word in n for word in ["town", "busstop", "desert", "farm", "island_"]):
        if "farmhouse" not in n and "farmcave" not in n:
            return "town exterior"
    if any(word in n for word in ["house", "room", "hut", "barn", "coop", "shed", "shop", "saloon", "cellar", "communitycenter"]):
        return "interior"
    return "unknown"


def neighbors4(x: int, y: int, width: int, height: int):
    for direction, dx, dy in [("N", 0, -1), ("E", 1, 0), ("S", 0, 1), ("W", -1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield direction, nx, ny


def neighbor_mask(coords: set[tuple[int, int]], x: int, y: int, width: int, height: int) -> str:
    parts = [direction for direction, nx, ny in neighbors4(x, y, width, height) if (nx, ny) in coords]
    return "".join(parts) or "none"


def mask_role(mask: str) -> str:
    count = 0 if mask == "none" else len(mask)
    if count == 0:
        return "isolated"
    if count == 1:
        return "cap_or_endpoint"
    if count == 2:
        if mask in {"NS", "EW"} or set(mask) in [{"N", "S"}, {"E", "W"}]:
            return "line_segment"
        return "corner_or_turn"
    if count == 3:
        return "edge_or_t_junction"
    if count == 4:
        return "interior_or_repeated_fill"
    return "unknown"


def stack_id(present: set[str]) -> str:
    ordered = [layer for layer in STANDARD_LAYERS if layer in present]
    return "+".join(ordered) if ordered else "empty"


def make_candidate(role: str, sheet: str, local_id: int, layer: str) -> dict[str, Any]:
    proposed_class, purpose, allowed_layers, collision = ROLE_CLASS_DEFAULTS[role]
    return {
        "structuralCandidateId": structural_id(sheet, local_id),
        "candidateId": None,
        "mappedCandidateIds": [],
        "roleName": role,
        "vanillaMapName": None,
        "sourceTilesheet": base_key(sheet),
        "localTileId": int(local_id),
        "layer": layer,
        "xYExamples": [],
        "exampleMaps": Counter(),
        "observedLayers": Counter(),
        "observedStackPatterns": Counter(),
        "neighborMasks": Counter(),
        "nearbyApprovedClasses": Counter(),
        "intrinsicProperties": {},
        "inferredRole": role,
        "evidenceScoreRaw": 0.0,
        "evidenceReasons": Counter(),
        "autoApprovalAllowed": False,
        "needsHumanReview": True,
        "riskFlags": set(),
        "proposedClass": proposed_class,
        "proposedPurpose": purpose,
        "proposedAllowedLayers": allowed_layers,
        "proposedCollision": collision,
    }


def add_candidate(
    candidates: dict[str, dict[tuple[str, int], dict[str, Any]]],
    role: str,
    sheet: str,
    local_id: int,
    layer: str,
    map_name: str,
    x: int,
    y: int,
    stack: str,
    mask: str,
    props: dict[str, Any],
    score: float,
    reason: str,
    risk_flags: list[str] | None = None,
) -> None:
    key = (base_key(sheet), int(local_id))
    entry = candidates[role].setdefault(key, make_candidate(role, sheet, int(local_id), layer))
    if entry["vanillaMapName"] is None:
        entry["vanillaMapName"] = map_name
    entry["observedLayers"][layer] += 1
    entry["observedStackPatterns"][stack] += 1
    entry["neighborMasks"][mask] += 1
    entry["exampleMaps"][map_name] += 1
    entry["intrinsicProperties"].update(props or {})
    entry["evidenceScoreRaw"] += score
    entry["evidenceReasons"][reason] += 1
    for flag in risk_flags or []:
        entry["riskFlags"].add(flag)
    add_example(
        entry["xYExamples"],
        {"mapName": map_name, "x": x, "y": y, "layer": layer, "observedStackPattern": stack, "neighborMask": mask},
    )


def parse_vanilla_map(path: Path, vanilla_index: dict[str, Any]) -> dict[str, Any]:
    parsed = T.parse(path.read_bytes())
    id_to_sheet = {ts["id"]: base_key(ts.get("imageSource") or ts.get("id")) for ts in parsed.get("tilesheets", [])}
    sheet_infos = {}
    for ts in parsed.get("tilesheets", []):
        sheet = id_to_sheet.get(ts["id"], base_key(ts.get("id")))
        sheet_infos[sheet] = {
            "sheetSize": list(ts.get("sheetSize") or []),
            "tileSize": list(ts.get("tileSize") or [16, 16]),
            "imageSource": ts.get("imageSource"),
        }
    layers = {}
    width = height = 0
    for layer in parsed.get("layers", []):
        name = str(layer.get("id"))
        if name not in STANDARD_LAYERS:
            continue
        w, h = layer.get("layerSize", (0, 0))
        width = max(width, int(w))
        height = max(height, int(h))
        tiles = {}
        for coord, payload in layer.get("tiles", {}).items():
            sheet_id, local_id = payload
            sheet = id_to_sheet.get(sheet_id, base_key(sheet_id))
            tiles[coord] = (sheet, int(local_id))
        layers[name] = {"width": int(w), "height": int(h), "tiles": tiles}
    return {"mapName": path.name, "width": width, "height": height, "layers": layers, "sheetInfos": sheet_infos, "category": infer_map_category(path.name)}


def mine_maps() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    vanilla_index = load_vanilla_index()
    candidates: dict[str, dict[tuple[str, int], dict[str, Any]]] = {role: {} for role in MISSING_ROLES}
    sheet_infos: dict[str, dict[str, Any]] = {}
    maps_parsed = 0
    parse_failures = []

    for path in sorted(UNPACKED_BASEGAME.glob("*.tbin")):
        try:
            map_data = parse_vanilla_map(path, vanilla_index)
        except Exception as exc:
            parse_failures.append({"mapName": path.name, "error": str(exc)})
            continue
        maps_parsed += 1
        sheet_infos.update(map_data["sheetInfos"])
        layers = map_data["layers"]
        width, height = map_data["width"], map_data["height"]
        map_name = map_data["mapName"]
        back = layers.get("Back", {}).get("tiles", {})
        buildings = layers.get("Buildings", {}).get("tiles", {})
        front = layers.get("Front", {}).get("tiles", {})
        always = layers.get("AlwaysFront", {}).get("tiles", {})
        paths = layers.get("Paths", {}).get("tiles", {})
        building_coords = set(buildings)
        front_coords = set(front)
        water_coords = {(x, y) for (x, y), (sheet, local) in back.items() if is_water(vanilla_index, sheet, local)}
        path_coords = set(paths)

        all_coords = set(back) | set(buildings) | set(front) | set(always) | set(paths)
        for x, y in all_coords:
            present = {layer for layer, tiles in [("Back", back), ("Buildings", buildings), ("Front", front), ("AlwaysFront", always), ("Paths", paths)] if (x, y) in tiles}
            stack = stack_id(present)
            nearby_building = (x, y) in buildings or any((nx, ny) in buildings for _, nx, ny in neighbors4(x, y, width, height))
            nearby_front = (x, y) in front or any((nx, ny) in front for _, nx, ny in neighbors4(x, y, width, height))
            nearby_water = any((nx, ny) in water_coords for _, nx, ny in neighbors4(x, y, width, height))
            nearby_path = (x, y) in paths or any((nx, ny) in path_coords for _, nx, ny in neighbors4(x, y, width, height))

            if (x, y) in buildings:
                sheet, local = buildings[(x, y)]
                props = props_for(vanilla_index, sheet, local)
                mask = neighbor_mask(building_coords, x, y, width, height)
                role = mask_role(mask)
                risks = []
                if local == 946:
                    risks.append("tile_946_quarantined_from_wall_body")
                if local != 946:
                    score = 4 + (3 if (x, y) in back else 0) + (2 if nearby_front else 0) + (1 if role != "isolated" else 0)
                    add_candidate(candidates, "wall_body", sheet, local, "Buildings", map_name, x, y, stack, mask, props, score, "Buildings tile in blocking structure stack", risks)
                    if role == "corner_or_turn":
                        add_candidate(candidates, "wall_corner", sheet, local, "Buildings", map_name, x, y, stack, mask, props, score + 2, "Buildings neighbor mask suggests corner/turn", risks)
                    elif role in {"line_segment", "cap_or_endpoint", "edge_or_t_junction"}:
                        add_candidate(candidates, "wall_edge", sheet, local, "Buildings", map_name, x, y, stack, mask, props, score + 1, "Buildings neighbor mask suggests edge/cap/run", risks)

            if (x, y) in front:
                sheet, local = front[(x, y)]
                props = props_for(vanilla_index, sheet, local)
                mask = neighbor_mask(front_coords, x, y, width, height)
                role = mask_role(mask)
                if nearby_building:
                    score = 4 + (3 if "Buildings" in stack else 0) + (2 if role != "isolated" else 0)
                    add_candidate(candidates, "wall_top", sheet, local, "Front", map_name, x, y, stack, mask, props, score, "Front tile paired with nearby Buildings structure")
                    if role == "corner_or_turn":
                        add_candidate(candidates, "wall_corner", sheet, local, "Front", map_name, x, y, stack, mask, props, score + 2, "Front neighbor mask suggests wall corner")
                    elif role in {"line_segment", "cap_or_endpoint", "edge_or_t_junction"}:
                        add_candidate(candidates, "wall_edge", sheet, local, "Front", map_name, x, y, stack, mask, props, score + 1, "Front neighbor mask suggests wall edge/cap/run")
                if nearby_building and local != 946:
                    add_candidate(candidates, "shadow", sheet, local, "Front", map_name, x, y, stack, mask, props, 2.5, "Front tile near Buildings may be shadow/overlay", ["shadow_role_requires_visual_review"])

            if (x, y) in always:
                sheet, local = always[(x, y)]
                props = props_for(vanilla_index, sheet, local)
                mask = neighbor_mask(set(always), x, y, width, height)
                risks = []
                if local == 946:
                    risks.append("tile_946_risky_canopy_candidate_not_blocker")
                if "Buildings" in stack:
                    risks.append("overlay_has_buildings_same_coordinate_check_collision_profile")
                score = 5 + (3 if (x, y) in back else 0) + (1 if "Buildings" not in stack else 0)
                add_candidate(candidates, "canopy_overlay", sheet, local, "AlwaysFront", map_name, x, y, stack, mask, props, score, "AlwaysFront overlay candidate with lower-layer support", risks)

            if (x, y) in back:
                sheet, local = back[(x, y)]
                props = props_for(vanilla_index, sheet, local)
                water_self = (x, y) in water_coords
                mask = neighbor_mask(set(back), x, y, width, height)
                if nearby_water and not water_self:
                    add_candidate(candidates, "water_edge", sheet, local, "Back", map_name, x, y, stack, mask, props, 5, "Back tile adjacent to Water=T tile", ["water_edge_requires_human_orientation_review"])
                if water_self:
                    non_water_neighbor = any((nx, ny) in back and (nx, ny) not in water_coords for _, nx, ny in neighbors4(x, y, width, height))
                    if non_water_neighbor:
                        add_candidate(candidates, "water_edge", sheet, local, "Back", map_name, x, y, stack, mask, props, 3.5, "Water=T tile at edge of water region", ["water_base_or_edge_needs_review"])
                if nearby_path:
                    add_candidate(candidates, "path_transition", sheet, local, "Back", map_name, x, y, stack, mask, props, 4 + (2 if (x, y) in paths else 0), "Back tile at or adjacent to Paths layer", ["path_transition_orientation_requires_review"])
                if nearby_building and not water_self:
                    add_candidate(candidates, "shadow", sheet, local, "Back", map_name, x, y, stack, mask, props, 2, "Back tile near Buildings may serve as shadow/dark ground", ["shadow_role_requires_visual_review"])

    role_lists: dict[str, list[dict[str, Any]]] = {}
    for role, items in candidates.items():
        out = []
        for entry in items.values():
            if int(entry["localTileId"]) == 946 and role != "canopy_overlay":
                continue
            count = sum(entry["observedLayers"].values())
            score = round(entry["evidenceScoreRaw"] + math.log(count + 1, 2), 3)
            risk_flags = sorted(entry["riskFlags"])
            if entry["localTileId"] == 946 and role in {"wall_body", "wall_corner", "wall_edge"}:
                risk_flags.append("tile_946_forbidden_for_blocking_role")
            out.append({
                **{k: v for k, v in entry.items() if k not in {"exampleMaps", "observedLayers", "observedStackPatterns", "neighborMasks", "nearbyApprovedClasses", "evidenceReasons", "riskFlags", "evidenceScoreRaw"}},
                "exampleMaps": dict(entry["exampleMaps"].most_common(12)),
                "observedLayers": dict(entry["observedLayers"]),
                "observedStackPattern": entry["observedStackPatterns"].most_common(1)[0][0] if entry["observedStackPatterns"] else None,
                "stackPatternSummary": dict(entry["observedStackPatterns"].most_common(10)),
                "neighborMask": entry["neighborMasks"].most_common(1)[0][0] if entry["neighborMasks"] else "none",
                "neighborPatternSummary": dict(entry["neighborMasks"].most_common(10)),
                "nearbyApprovedClasses": dict(entry["nearbyApprovedClasses"].most_common(10)),
                "evidenceScore": score,
                "evidenceReasons": dict(entry["evidenceReasons"].most_common(10)),
                "riskFlags": risk_flags,
            })
        role_lists[role] = sorted(out, key=lambda item: (item["evidenceScore"], sum(item["observedLayers"].values())), reverse=True)
    return role_lists, {"mapsParsed": maps_parsed, "parseFailures": parse_failures, "sheetInfos": sheet_infos}


def build_sheet_image_index() -> dict[str, Path]:
    candidates = {}
    for path in UNPACKED_BASEGAME.glob("*.png"):
        name = path.name
        key = base_key(name)
        current = candidates.get(key)
        if current is None:
            candidates[key] = path
            continue
        # Prefer non-localized base files when duplicates exist.
        if re.search(r"\.[a-z]{2}-[A-Z]{2}\.png$", current.name) and not re.search(r"\.[a-z]{2}-[A-Z]{2}\.png$", name):
            candidates[key] = path
    return candidates


def map_to_canonical_candidates(role_lists: dict[str, list[dict[str, Any]]]) -> None:
    needed = {(item["sourceTilesheet"], int(item["localTileId"])) for items in role_lists.values() for item in items}
    if not needed or not CANONICAL_CANDIDATES.exists():
        return
    mapping: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    with CANONICAL_CANDIDATES.open("rb") as handle:
        for cand in ijson.items(handle, "item"):
            local = cand.get("localTileId")
            if local is None:
                continue
            try:
                local = int(local)
            except Exception:
                continue
            keys = {
                base_key(cand.get("tilesheetName")),
                base_key(cand.get("imageName")),
                base_key(cand.get("copiedImagePath")),
            }
            for sheet in keys:
                key = (sheet, local)
                if key in needed:
                    mapping[key].append({
                        "candidateId": cand.get("candidateId"),
                        "sourceCategory": cand.get("sourceCategory"),
                        "sourceMod": cand.get("sourceMod"),
                        "copiedImagePath": cand.get("copiedImagePath"),
                    })
    for items in role_lists.values():
        for item in items:
            mapped = mapping.get((item["sourceTilesheet"], int(item["localTileId"])), [])
            item["mappedCandidateIds"] = [m["candidateId"] for m in mapped if m.get("candidateId")]
            item["mappedCandidates"] = mapped[:12]
            item["candidateId"] = item["mappedCandidateIds"][0] if item["mappedCandidateIds"] else None


def write_missing_roles(role_lists: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    readiness = load_json(READINESS_MATRIX) if READINESS_MATRIX.exists() else {"roles": []}
    roles_by_name = {r.get("roleName"): r for r in readiness.get("roles", [])}
    stylepack_ids = []
    for path in sorted(STYLEPACK_DIR.glob("*.json")):
        if path.name in {"stylepack_schema.json", "collision_schema.json"}:
            continue
        try:
            stylepack_ids.append(load_json(path).get("stylePackId", path.stem))
        except Exception:
            stylepack_ids.append(path.stem)
    generator_rules = load_json(TOOL_ROOT / "pattern_learning" / "layer_combinations" / "generator_layer_rules_from_vanilla.json")
    blocked_rules = defaultdict(list)
    semantic_to_missing_role = {
        "terrain_transition": "path_transition",
        "corner": "wall_corner",
        "edge": "wall_edge",
        "water": "water_edge",
        "wall_body": "wall_body",
        "wall_top": "wall_top",
        "canopy_overlay": "canopy_overlay",
    }
    for rule in generator_rules.get("rules", []):
        role = semantic_to_missing_role.get(rule.get("semanticMarkerInput"), rule.get("semanticMarkerInput"))
        if role in MISSING_ROLES:
            blocked_rules[role].append(rule.get("derivedFromGrammarRule"))
    records = []
    for role in MISSING_ROLES:
        ready = roles_by_name.get(role, {})
        records.append({
            "roleName": role,
            "requiredLayerStack": ready.get("requiredLayerStack") or [],
            "requiredApprovedClasses": ready.get("requiredApprovedTileClasses") or [ROLE_CLASS_DEFAULTS[role][0]],
            "stylepacksBlocked": stylepack_ids,
            "generatorRulesBlocked": sorted(set(blocked_rules.get(role, []))),
            "markerFallback": MARKER_FALLBACKS[role],
            "productionAllowedNow": False,
            "reasonBlocked": ready.get("blockerReason") or "Missing approved structural tile profiles.",
            "candidateCountMined": len(role_lists.get(role, [])),
        })
    doc = {"generatedAt": now_iso(), "roles": records}
    write_json(STRUCTURAL_ROOT / "missing_structural_roles.json", doc)
    return doc


def write_evidence_files(role_lists: dict[str, list[dict[str, Any]]]) -> None:
    for role, candidates in role_lists.items():
        maps = Counter()
        sheets = Counter()
        stacks = Counter()
        masks = Counter()
        risks = Counter()
        for item in candidates:
            sheets[item["sourceTilesheet"]] += 1
            stacks.update(item.get("stackPatternSummary") or {})
            masks.update(item.get("neighborPatternSummary") or {})
            risks.update(item.get("riskFlags") or [])
            maps.update(item.get("exampleMaps") or {})
        doc = {
            "generatedAt": now_iso(),
            "roleName": role,
            "totalCandidates": len(candidates),
            "topCandidates": candidates[: min(25, len(candidates))],
            "strongestMaps": top_counter(maps, 20),
            "commonTilesheets": top_counter(sheets, 20),
            "commonLayerStacks": top_counter(stacks, 20),
            "commonNeighborMasks": top_counter(masks, 20),
            "riskSummary": top_counter(risks, 20),
            "recommendedReviewStrategy": review_strategy(role, len(candidates), risks),
        }
        write_json(EVIDENCE_DIR / f"{role}_evidence.json", doc)


def review_strategy(role: str, count: int, risks: Counter) -> str:
    if role == "canopy_overlay":
        return "Review AlwaysFront candidates as overlay-only profiles. Tile 946 may be inspected as risky canopy evidence but must not become a blocker."
    if role in {"wall_body", "wall_corner", "wall_edge"}:
        return "Approve only tiles that clearly belong on Buildings/Front structural stacks. Reject tile 946 for any blocking role."
    if role == "water_edge":
        return "Use Water=T adjacency as evidence, but approve edge orientation manually."
    if role == "path_transition":
        return "Prefer candidates repeatedly used on Back at or near vanilla Paths layer routes."
    if role == "shadow":
        return "Approve only non-blocking Back/Front shadow profiles; avoid collision-bearing tiles."
    return "Review top evidence-score candidates first and approve only role-specific profiles."


def write_review_packs(role_lists: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    index = {"generatedAt": now_iso(), "reviewPacks": []}
    for role, candidates in role_lists.items():
        limit = ROLE_LIMITS[role]
        pack_candidates = []
        for item in candidates[:limit]:
            pack_candidates.append({
                "candidateId": item.get("candidateId"),
                "structuralCandidateId": item.get("structuralCandidateId"),
                "mappedCandidateIds": item.get("mappedCandidateIds", []),
                "roleName": role,
                "localTileId": item["localTileId"],
                "sourceTilesheet": item["sourceTilesheet"],
                "layer": item["layer"],
                "exampleMaps": item.get("exampleMaps", {}),
                "exampleCoordinates": item.get("xYExamples", []),
                "neighborPatternSummary": item.get("neighborPatternSummary", {}),
                "stackPatternSummary": item.get("stackPatternSummary", {}),
                "evidenceScore": item.get("evidenceScore"),
                "proposedClass": item.get("proposedClass"),
                "proposedPurpose": item.get("proposedPurpose"),
                "proposedAllowedLayers": item.get("proposedAllowedLayers"),
                "proposedCollision": item.get("proposedCollision"),
                "riskFlags": item.get("riskFlags", []),
                "humanDecision": None,
            })
        pack = {
            "reviewPackId": f"{role}_review_pack",
            "roleName": role,
            "generatedAt": now_iso(),
            "candidateLimit": limit,
            "candidateCount": len(pack_candidates),
            "totalCandidatesFound": len(candidates),
            "autoApprovalAllowed": False,
            "needsHumanReview": True,
            "candidates": pack_candidates,
        }
        path = PACK_DIR / f"{role}_review_pack.json"
        write_json(path, pack)
        index["reviewPacks"].append({"roleName": role, "path": str(path), "candidateCount": len(pack_candidates), "totalCandidatesFound": len(candidates)})
    write_json(STRUCTURAL_ROOT / "review_pack_index.json", index)
    return index


def tile_geometry(sheet_infos: dict[str, dict[str, Any]], sheet: str, image: Image.Image) -> tuple[int, int, int]:
    info = sheet_infos.get(base_key(sheet), {})
    tile_size = info.get("tileSize") or [16, 16]
    tile_w = int(tile_size[0] or 16)
    tile_h = int(tile_size[1] or 16)
    sheet_size = info.get("sheetSize") or []
    columns = int(sheet_size[0]) if sheet_size else max(1, image.width // tile_w)
    return tile_w, tile_h, columns


def crop_tile(image: Image.Image, local_id: int, columns: int, tile_w: int, tile_h: int) -> Image.Image:
    x = (local_id % columns) * tile_w
    y = (local_id // columns) * tile_h
    return image.crop((x, y, x + tile_w, y + tile_h))


def crop_context(image: Image.Image, local_id: int, columns: int, tile_w: int, tile_h: int, radius: int = 1) -> Image.Image:
    tx = local_id % columns
    ty = local_id // columns
    left = max(0, (tx - radius) * tile_w)
    top = max(0, (ty - radius) * tile_h)
    right = min(image.width, (tx + radius + 1) * tile_w)
    bottom = min(image.height, (ty + radius + 1) * tile_h)
    return image.crop((left, top, right, bottom))


def make_previews(role_lists: dict[str, list[dict[str, Any]]], sheet_infos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    sheet_images = build_sheet_image_index()
    font = ImageFont.load_default()
    created = []
    for role, candidates in role_lists.items():
        items = candidates[: min(ROLE_LIMITS[role], 80)]
        if not items:
            continue
        cell_w, cell_h = 112, 84
        cols = 5
        rows = math.ceil(len(items) / cols)
        labeled = Image.new("RGBA", (cols * cell_w, rows * cell_h), (28, 28, 32, 255))
        clean = Image.new("RGBA", (cols * cell_w, rows * cell_h), (28, 28, 32, 255))
        dl = ImageDraw.Draw(labeled)
        dc = ImageDraw.Draw(clean)
        for idx, item in enumerate(items):
            sheet = item["sourceTilesheet"]
            img_path = sheet_images.get(base_key(sheet))
            cx = (idx % cols) * cell_w
            cy = (idx // cols) * cell_h
            if img_path and img_path.exists():
                with Image.open(img_path).convert("RGBA") as source:
                    tile_w, tile_h, columns = tile_geometry(sheet_infos, sheet, source)
                    tile = crop_tile(source, int(item["localTileId"]), columns, tile_w, tile_h).resize((32, 32), Image.Resampling.NEAREST)
                    context = crop_context(source, int(item["localTileId"]), columns, tile_w, tile_h).resize((48, 48), Image.Resampling.NEAREST)
                    for canvas in [labeled, clean]:
                        canvas.alpha_composite(context, (cx + 4, cy + 4))
                        canvas.alpha_composite(tile, (cx + 60, cy + 10))
            else:
                for draw in [dl, dc]:
                    draw.rectangle((cx + 4, cy + 4, cx + 52, cy + 52), outline=(180, 80, 80), width=1)
            dc.rectangle((cx, cy, cx + cell_w - 1, cy + cell_h - 1), outline=(55, 55, 60))
            dl.rectangle((cx, cy, cx + cell_w - 1, cy + cell_h - 1), outline=(95, 95, 105))
            dl.text((cx + 4, cy + 56), f"{item['sourceTilesheet']}:{item['localTileId']}", fill=(235, 235, 235), font=font)
            dl.text((cx + 4, cy + 68), f"{role} {item['layer']} s={item['evidenceScore']}", fill=(180, 220, 255), font=font)
            if item.get("riskFlags"):
                dl.rectangle((cx + 58, cy + 6, cx + 96, cy + 20), outline=(255, 180, 60), width=1)
                dl.text((cx + 61, cy + 8), "RISK", fill=(255, 210, 80), font=font)
        labeled_path = PREVIEW_DIR / f"{role}_review_labeled.png"
        clean_path = PREVIEW_DIR / f"{role}_review_clean.png"
        labeled.save(labeled_path)
        clean.save(clean_path)
        created.append({"roleName": role, "labeledPreview": str(labeled_path), "cleanPreview": str(clean_path), "candidateCount": len(items)})
    write_json(PREVIEW_DIR / "preview_index.json", {"generatedAt": now_iso(), "previews": created})
    return created


def write_manual_template(role_lists: dict[str, list[dict[str, Any]]]) -> None:
    roles = {}
    for role in MISSING_ROLES:
        proposed_class, purpose, layers, collision = ROLE_CLASS_DEFAULTS[role]
        example = (role_lists.get(role) or [{}])[0]
        roles[role] = [
            {
                "candidateId": example.get("candidateId") or example.get("structuralCandidateId") or "",
                "structuralCandidateId": example.get("structuralCandidateId") or "",
                "decision": "approve / reject / unsure",
                "approvedClass": proposed_class,
                "approvedPurpose": purpose,
                "allowedLayers": layers,
                "collision": collision,
                "notes": "",
            }
        ]
    template = {"reviewType": "structural_tile_roles", "reviewer": "Joel", "roles": roles}
    write_json(STRUCTURAL_ROOT / "structural_manual_decisions.template.json", template)


def write_candidate_outputs(role_lists: dict[str, list[dict[str, Any]]], meta: dict[str, Any]) -> None:
    doc = {
        "generatedAt": now_iso(),
        "source": "vanilla_layer_grammar_and_tbin_maps",
        "mapsParsed": meta["mapsParsed"],
        "parseFailures": meta["parseFailures"],
        "autoApprovalAllowed": False,
        "tile946Policy": "Tile 946 remains quarantined from wall/body/blocking/collision roles. It may appear only as risky canopy evidence.",
        "roles": role_lists,
    }
    write_json(CANDIDATE_DIR / "structural_tile_candidates_by_role.json", doc)


def write_readiness_reports(role_lists: dict[str, list[dict[str, Any]]]) -> None:
    current = load_json(READINESS_MATRIX) if READINESS_MATRIX.exists() else {"roles": []}
    role_readiness = {r["roleName"]: r for r in current.get("roles", [])}
    lines = [
        "# Production Readiness After Structural Candidates",
        "",
        f"- Generated: {now_iso()}",
        "- Production output remains blocked until manual approvals are imported and validated.",
        "",
        "| Role | Current Approved Count | Candidate Count | Human Approvals Needed | Blocker |",
        "|---|---:|---:|---:|---|",
    ]
    doc_roles = []
    for role in MISSING_ROLES:
        current_role = role_readiness.get(role, {})
        candidate_count = len(role_lists.get(role, []))
        minimum_needed = min_required_count(role)
        approved_count = current_role.get("approvedCount", 0)
        lines.append(f"| {role} | {approved_count} | {candidate_count} | {minimum_needed} | {current_role.get('blockerReason', 'missing approved profiles')} |")
        doc_roles.append({
            "roleName": role,
            "currentApprovedCount": approved_count,
            "candidateCount": candidate_count,
            "minimumHumanApprovalsNeeded": minimum_needed,
            "stylepacksAffected": ["cursed_hedge_maze", "fairy_forest", "moonvillage_forest_ruins", "void_dungeon"],
            "blockerReason": current_role.get("blockerReason", "missing approved profiles"),
        })
    lines.extend([
        "",
        "## Minimum First Visual Test",
        "",
        "- Approve one coherent wall/body group.",
        "- Approve one compatible wall-top group.",
        "- Approve four corner roles and four edge/cap roles.",
        "- Approve one path transition group.",
        "- Add shadow/canopy/water-edge approvals only if the test style requires those structures.",
    ])
    write_text(REPORT_DIR / "production_readiness_after_structural_candidates.md", "\n".join(lines))
    write_json(REPORT_DIR / "production_readiness_after_structural_candidates.json", {"generatedAt": now_iso(), "roles": doc_roles})


def min_required_count(role: str) -> int:
    return {
        "wall_body": 1,
        "wall_top": 1,
        "wall_corner": 4,
        "wall_edge": 4,
        "path_transition": 1,
        "shadow": 1,
        "canopy_overlay": 1,
        "water_edge": 1,
    }.get(role, 1)


def write_minimum_set_report(role_lists: dict[str, list[dict[str, Any]]]) -> None:
    lines = [
        "# Minimum Structural Approval Set",
        "",
        f"- Generated: {now_iso()}",
        "- Scope: smallest role-based approval set for the first visual production test.",
        "",
        "## Recommended First Pass",
        "",
        "- `wall_body`: approve 1 coherent blocker/body group on `Buildings`.",
        "- `wall_top`: approve 1 compatible top/front group on `Front`.",
        "- `wall_corner`: approve 4 corner orientations.",
        "- `wall_edge`: approve 4 edge/cap orientations.",
        "- `path_transition`: approve 1 path/ground transition group.",
        "- `shadow`: approve 1 non-blocking shadow group if the style uses wall grounding.",
        "- `canopy_overlay`: approve 1 overlay-only group only for forest/canopy tests.",
        "- `water_edge`: approve 1 edge group only if the test map includes water.",
        "",
        "## Suggested Top Candidates",
        "",
        "These are evidence-ranked review starting points, not automatic approval recommendations. Approve only after checking the clean/labeled previews and role-specific context.",
        "",
    ]
    for role in MISSING_ROLES:
        lines.append(f"### {role}")
        for item in role_lists.get(role, [])[: min_required_count(role)]:
            lines.append(f"- `{item.get('structuralCandidateId')}` / mapped `{item.get('candidateId')}`: {item['sourceTilesheet']} tile {item['localTileId']} score {item['evidenceScore']} risks {item.get('riskFlags', [])}")
        lines.append("")
    write_text(REPORT_DIR / "minimum_structural_approval_set.md", "\n".join(lines))


def write_summary(role_lists: dict[str, list[dict[str, Any]]], previews: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    lines = [
        "# Structural Tile Candidate Mining Summary",
        "",
        f"- Generated: {now_iso()}",
        f"- Vanilla maps parsed: {meta['mapsParsed']}",
        f"- Parse failures: {len(meta['parseFailures'])}",
        "- Auto approvals created: 0",
        "- Production maps generated: 0",
        "- Tile 946 status: quarantined from wall/body/blocking/collision roles; listed only as risky canopy evidence if observed.",
        "- Candidate ranking is evidence-based and review-only. High score means frequent vanilla layer/neighbor support, not automatic visual correctness.",
        "",
        "## Candidates Found",
        "",
    ]
    for role in MISSING_ROLES:
        top = role_lists.get(role, [])[:3]
        lines.append(f"- {role}: {len(role_lists.get(role, []))} candidates; top examples: " + ", ".join(f"{x['sourceTilesheet']}:{x['localTileId']}" for x in top))
    lines.extend([
        "",
        "## Outputs",
        "",
        f"- Review packs created: {len(MISSING_ROLES)}",
        f"- Preview pairs created: {len(previews)}",
        "- Evidence files created: one per role.",
        "",
        "## Next Recommended Mission",
        "",
        "Use the role review packs to make manual decisions, then run `import_structural_manual_decisions.py` and `validate_structural_approved_tags.py` before merging approvals.",
    ])
    write_text(REPORT_DIR / "structural_tile_candidate_mining_summary.md", "\n".join(lines))


def main() -> int:
    ensure_dirs()
    role_lists, meta = mine_maps()
    map_to_canonical_candidates(role_lists)
    write_candidate_outputs(role_lists, meta)
    write_missing_roles(role_lists)
    write_evidence_files(role_lists)
    write_review_packs(role_lists)
    previews = make_previews(role_lists, meta["sheetInfos"])
    write_manual_template(role_lists)
    write_readiness_reports(role_lists)
    write_minimum_set_report(role_lists)
    write_summary(role_lists, previews, meta)
    print("Structural candidate mining complete")
    for role in MISSING_ROLES:
        print(f"{role}: {len(role_lists.get(role, []))} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
