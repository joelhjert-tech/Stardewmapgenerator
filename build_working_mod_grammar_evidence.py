#!/usr/bin/env python3
"""Build working-mod grammar evidence for the tile grammar template system.

This reads local reference repos and previously mined evidence only. It does not
copy assets or approve production tiles.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
OUT_ROOT = ROOT / "pattern_learning" / "tile_grammar_templates"
REF_OUT = OUT_ROOT / "reference_mod_patterns"
REPORTS = ROOT / "reports"
EVIDENCE = ROOT / "working_mod_mining" / "evidence"
PROPOSED = ROOT / "working_mod_mining" / "proposed"
REF_REPOS = ROOT / "working_mod_mining" / "reference_repos"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE.resolve()))
    except Exception:
        return str(path.resolve())


def safe_load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def iter_files(path: Path, suffixes: Iterable[str]) -> List[Path]:
    if not path.exists():
        return []
    suffixes = tuple(s.lower() for s in suffixes)
    out = []
    for p in path.rglob("*"):
        if p.is_file() and p.suffix.lower() in suffixes:
            out.append(p)
    return out


def detect_reference_roots() -> Dict[str, Path]:
    candidates = {
        "DeepWoods": WORKSPACE / "tools" / "DeepWoodsMod-main",
        "HedgeMaze": WORKSPACE / "tools" / "HedgeMaze",
        "SpaceCore": REF_REPOS / "SpaceCore",
        "StardewValleyMods": REF_REPOS / "StardewValleyMods",
        "Pathoschild_StardewMods": REF_REPOS / "StardewMods",
    }
    # Soft search for similarly named local folders.
    for name in ("HedgeMaze", "SpaceCore"):
        if candidates[name].exists():
            continue
        for root in [WORKSPACE / "tools", ROOT / "working_mod_mining" / "reference_repos"]:
            if root.exists():
                found = next((p for p in root.iterdir() if p.is_dir() and name.lower() in p.name.lower()), None)
                if found:
                    candidates[name] = found
                    break
    return candidates


def inventory_working_mods() -> List[dict]:
    inventory = []
    relevant = {
        "DeepWoods": ["procedural map generation", "forest border grammar", "exit placement", "placement safety"],
        "HedgeMaze": ["maze/path wall logic"],
        "SpaceCore": ["dungeon registry", "floor pools", "ladders/elevators/mineshafts"],
        "StardewValleyMods": ["BiggerMineFloors", "AdditionalMineMaps", "UndergroundSecrets", "MapEdit", "DynamicMapTilesExtended", "IndoorOutdoor"],
        "Pathoschild_StardewMods": ["Content Patcher map patching", "Data Layers overlays"],
    }
    for name, path in detect_reference_roots().items():
        exists = path.exists()
        code_files = iter_files(path, [".cs", ".ts", ".js", ".py"]) if exists else []
        map_files = iter_files(path, [".tmx", ".tmj", ".tbin"]) if exists else []
        config_files = iter_files(path, [".json", ".json5", ".yaml", ".yml"]) if exists else []
        inventory.append({
            "modOrRepoName": name,
            "sourcePath": rel(path),
            "exists": exists,
            "filesAnalyzed": len(code_files) + len(map_files) + len(config_files),
            "mapFilesFound": len(map_files),
            "codeFilesFound": len(code_files),
            "configContentFilesFound": len(config_files),
            "relevantSystemsFound": relevant.get(name, []),
            "assetsRestrictedOrCustom": name not in ("Pathoschild_StardewMods",) and exists,
            "codeUsableAsGrammarEvidence": exists,
            "mapsUsableAsGrammarEvidence": exists and name not in ("DeepWoods",),
            "riskFlags": ([] if exists else ["not_available_locally"]) + (["do_not_copy_assets"] if exists else []),
        })
    return inventory


def evidence_from_existing_files() -> List[dict]:
    patterns = []
    # BiggerMineFloors expansion matrices.
    bmf = safe_load_json(EVIDENCE / "biggerminefloors_expansion_matrix_index.json", {})
    for case in bmf.get("cases", [])[:300]:
        patterns.append({
            "sourceMod": "BiggerMineFloors",
            "sourceFile": case.get("sourceFile", ""),
            "lineNumber": case.get("lineNumber"),
            "evidenceKind": "code_matrix",
            "tilesheetBinding": "unknown_or_runtime_mine_sheet",
            "tileIds": [case.get("baseTileIndex")] if case.get("baseTileIndex") is not None else [],
            "layers": [],
            "inferredRole": case.get("roleLabelFromComments") or "tile-aware expansion case",
            "patternShape": case.get("matrixShape", "expansion_matrix"),
            "confidence": 70 if case.get("riskFlags") else 85,
            "riskFlags": case.get("riskFlags", []) + ["prototype_evidence_only"],
            "safeForPrototype": True,
            "safeForProduction": False,
            "recommendedAction": "propose_for_review",
        })
    # AdditionalMineMaps floor registry.
    amm = safe_load_json(EVIDENCE / "additional_mine_maps_floor_registry_evidence.json", {})
    for entry in amm.get("entries", amm.get("floorRegistry", []))[:200]:
        patterns.append({
            "sourceMod": "AdditionalMineMaps",
            "sourceFile": entry.get("sourceFile", ""),
            "lineNumber": entry.get("lineNumber"),
            "evidenceKind": "floor_registry",
            "tilesheetBinding": "",
            "tileIds": [],
            "layers": [],
            "inferredRole": "mine floor pool / forced floor category",
            "patternShape": "floor_registry_template",
            "confidence": 82,
            "riskFlags": ["registry_logic_only", "not_tile_approval"],
            "safeForPrototype": True,
            "safeForProduction": False,
            "recommendedAction": "use_as_template_evidence",
        })
    # UndergroundSecrets placement rules.
    us = safe_load_json(EVIDENCE / "underground_secrets_placement_evidence.json", {})
    if us:
        patterns.append({
            "sourceMod": "UndergroundSecrets",
            "sourceFile": us.get("sourceFile", ""),
            "lineNumber": None,
            "evidenceKind": "placement_rule",
            "tilesheetBinding": "",
            "tileIds": [],
            "layers": ["Back", "Buildings", "Front"],
            "inferredRole": "clear-space placement scanner and entrance/ladder protection",
            "patternShape": "placement_rule_template",
            "confidence": 88,
            "riskFlags": ["logic_only", "not_tile_approval"],
            "safeForPrototype": True,
            "safeForProduction": False,
            "recommendedAction": "use_as_template_evidence",
        })
    # MapEdit tile-stack/delta format.
    me = safe_load_json(EVIDENCE / "mapedit_tile_stack_format_evidence.json", {})
    if me:
        patterns.append({
            "sourceMod": "MapEdit",
            "sourceFile": me.get("sourceFile", ""),
            "lineNumber": None,
            "evidenceKind": "map_delta_format",
            "tilesheetBinding": "",
            "tileIds": [],
            "layers": ["Back", "Buildings", "Front", "AlwaysFront", "Paths"],
            "inferredRole": "tile stack and map edit delta storage",
            "patternShape": "map_patch_template",
            "confidence": 86,
            "riskFlags": ["format_evidence_only"],
            "safeForPrototype": True,
            "safeForProduction": False,
            "recommendedAction": "use_as_template_evidence",
        })
    # Dynamic tiles actions.
    dmt = safe_load_json(EVIDENCE / "dynamic_tile_action_key_index.json", {})
    if dmt:
        patterns.append({
            "sourceMod": "DynamicMapTilesExtended",
            "sourceFile": dmt.get("sourceFile", ""),
            "lineNumber": None,
            "evidenceKind": "tile_action_schema",
            "tilesheetBinding": "",
            "tileIds": [],
            "layers": [],
            "inferredRole": "interactive tile action/trigger metadata",
            "patternShape": "interactive_tile_rule",
            "confidence": 80,
            "riskFlags": ["interactive_schema_only"],
            "safeForPrototype": True,
            "safeForProduction": False,
            "recommendedAction": "propose_for_review",
        })
    for filename, mod, kind, role in [
        ("content_patcher_map_patch_model_evidence.json", "ContentPatcher", "content_patch", "safe map patch/export validation"),
        ("data_layers_overlay_model_evidence.json", "DataLayers", "overlay_rule", "reviewer validation overlay groups"),
    ]:
        data = safe_load_json(EVIDENCE / filename, {})
        if data:
            patterns.append({
                "sourceMod": mod,
                "sourceFile": data.get("sourceFile", ""),
                "lineNumber": None,
                "evidenceKind": kind,
                "tilesheetBinding": "",
                "tileIds": [],
                "layers": [],
                "inferredRole": role,
                "patternShape": "overlay_template" if kind == "overlay_rule" else "map_patch_template",
                "confidence": 88,
                "riskFlags": ["logic_only", "not_tile_approval"],
                "safeForPrototype": True,
                "safeForProduction": False,
                "recommendedAction": "use_as_template_evidence",
            })
    # Existing proposed safe patterns.
    safe_patterns = safe_load_json(PROPOSED / "working_mod_safe_pattern_candidates.json", {})
    for pattern in safe_patterns.get("patterns", [])[:300]:
        patterns.append({
            "sourceMod": pattern.get("sourceMod", "working_mod_mining"),
            "sourceFile": "",
            "lineNumber": None,
            "evidenceKind": pattern.get("patternType", "safe_pattern_candidate"),
            "tilesheetBinding": "",
            "tileIds": pattern.get("tiles", []),
            "layers": pattern.get("layerStack", []),
            "inferredRole": pattern.get("patternName", "working mod safe pattern candidate"),
            "patternShape": pattern.get("patternType", "unknown"),
            "confidence": pattern.get("confidenceScore", 75),
            "riskFlags": [] if not pattern.get("requiresHumanReview", True) else ["requires_human_review"],
            "safeForPrototype": True,
            "safeForProduction": bool(pattern.get("productionReady", False)),
            "recommendedAction": pattern.get("recommendedAction", "propose_for_review"),
        })
    return patterns


def scan_code_for_grammar_hints(inventory: List[dict]) -> List[dict]:
    patterns = []
    interesting = re.compile(r"(wall|corner|floor|ladder|shaft|mine|dungeon|clear|warp|map|patch|tile|overlay|registry)", re.I)
    id_pattern = re.compile(r"\b(?:tile(?:Index|Id)?|TileIndex|index)\b[^;\n]{0,80}?(-?\d{1,4})")
    for item in inventory:
        path = WORKSPACE / item["sourcePath"] if not Path(item["sourcePath"]).is_absolute() else Path(item["sourcePath"])
        if not path.exists():
            continue
        for code in iter_files(path, [".cs"])[:800]:
            try:
                lines = code.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for number, line in enumerate(lines, start=1):
                if not interesting.search(line):
                    continue
                ids = [int(m.group(1)) for m in id_pattern.finditer(line)]
                if ids or any(k in line for k in ("Before", "After", "Patch", "LoadMap", "clearSpots", "MapTiles")):
                    patterns.append({
                        "sourceMod": item["modOrRepoName"],
                        "sourceFile": rel(code),
                        "lineNumber": number,
                        "evidenceKind": "code_hint",
                        "tilesheetBinding": "unknown",
                        "tileIds": ids[:20],
                        "layers": [],
                        "inferredRole": line.strip()[:220],
                        "patternShape": "code_reference",
                        "confidence": 45 if ids else 35,
                        "riskFlags": ["code_hint_only", "not_safe_for_auto_approval"],
                        "safeForPrototype": False,
                        "safeForProduction": False,
                        "recommendedAction": "quarantine" if ids else "propose_for_review",
                    })
                    if len(patterns) > 1500:
                        return patterns
    return patterns


def write_reports(inventory: List[dict], patterns: List[dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = ["# Tile Grammar Working Mod Inventory", ""]
    for item in inventory:
        lines += [
            f"## {item['modOrRepoName']}",
            f"- Path: `{item['sourcePath']}`",
            f"- Exists: {item['exists']}",
            f"- Code files: {item['codeFilesFound']}",
            f"- Map files: {item['mapFilesFound']}",
            f"- Config/content files: {item['configContentFilesFound']}",
            f"- Relevant systems: {', '.join(item['relevantSystemsFound']) or 'none detected'}",
            f"- Risk flags: {', '.join(item['riskFlags']) or 'none'}",
            "",
        ]
    (REPORTS / "tile_grammar_working_mod_inventory.md").write_text("\n".join(lines), encoding="utf-8")

    counts = {}
    for pattern in patterns:
        counts[pattern["sourceMod"]] = counts.get(pattern["sourceMod"], 0) + 1
    ev = [
        "# Working Mod Tile Grammar Evidence",
        "",
        f"- Pattern evidence entries: {len(patterns)}",
        "- No source code or assets were copied into Moonvillage.",
        "- Entries with unclear tilesheet/layer/collision are evidence only and not production approvals.",
        "",
        "## Counts By Source",
    ]
    for name, count in sorted(counts.items()):
        ev.append(f"- {name}: {count}")
    (REPORTS / "working_mod_tile_grammar_evidence.md").write_text("\n".join(ev) + "\n", encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    REF_OUT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    inventory = inventory_working_mods()
    patterns = evidence_from_existing_files()
    patterns += scan_code_for_grammar_hints(inventory)
    inventory_doc = {
        "generatedAt": now_iso(),
        "workingMods": inventory,
    }
    pattern_doc = {
        "generatedAt": now_iso(),
        "source": "local_reference_mods_and_existing_working_mod_mining_outputs",
        "patterns": patterns,
    }
    (OUT_ROOT / "working_mod_grammar_inventory.json").write_text(json.dumps(inventory_doc, indent=2), encoding="utf-8")
    (REF_OUT / "working_mod_structure_patterns.json").write_text(json.dumps(pattern_doc, indent=2), encoding="utf-8")
    write_reports(inventory, patterns)
    print(json.dumps({"status": "PASS", "workingMods": len(inventory), "patterns": len(patterns)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
