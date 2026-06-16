#!/usr/bin/env python3
"""Build tile/layer-stack combination groups for the exception review UI."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOL_ROOT = Path(__file__).resolve().parent
REVIEW_PACK_ROOT = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "actionable_review" / "review_packs"
EXCEPTION_ROOT = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps" / "exception_review"
COMBINATION_INDEX_PATH = EXCEPTION_ROOT / "combination_index.json"
STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
UNSAFE_946_DECISIONS = {"approve_audit_exception", "marker_only_pattern"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_suggestion(value: Any) -> str:
    mapping = {
        "approve_exception": "approve_audit_exception",
        "true_error": "mark_true_error",
        "mark_true_error": "mark_true_error",
        "marker_only": "marker_only_pattern",
        "marker_only_pattern": "marker_only_pattern",
        "needs_tile_approval": "needs_tile_approval",
        "unsure": "unsure",
    }
    return mapping.get(str(value or "").strip(), str(value or "unsure").strip() or "unsure")


def parse_tile(value: Any) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    sheet, local = text.rsplit(":", 1)
    sheet = sheet.strip()
    local = local.strip()
    if not sheet or not local:
        return None
    return sheet, local


def tile_id_is_946(value: Any) -> bool:
    parsed = parse_tile(value)
    return bool(parsed and parsed[1] == "946")


def is_unsafe_tile_946_case(entry: dict[str, Any]) -> bool:
    tiles = entry.get("tileIdsByLayer") or {}
    if not any(tile_id_is_946(value) for value in tiles.values()):
        return False
    if tile_id_is_946(tiles.get("Buildings")):
        return True
    text = " ".join(
        str(entry.get(key, ""))
        for key in ["layerStack", "currentClassification", "reasonNeedsReview", "suggestedDecision", "notes"]
    ).lower()
    return any(word in text for word in ["wall", "body", "blocking", "blocker", "collision"])


def combination_key_for_case(entry: dict[str, Any]) -> dict[str, str]:
    tiles = entry.get("tileIdsByLayer") or {}
    key: dict[str, str] = {}
    for layer in STANDARD_LAYERS:
        parsed = parse_tile(tiles.get(layer))
        key[layer] = f"{parsed[0]}:{parsed[1]}" if parsed else "empty"
    return key


def combination_hash_for_key(key: dict[str, str]) -> str:
    canonical = json.dumps({layer: key.get(layer, "empty") for layer in STANDARD_LAYERS}, sort_keys=True, separators=(",", ":"))
    return "combo_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def source_tilesheets_for_key(key: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for layer, tile in key.items():
        parsed = parse_tile(tile)
        out[layer] = parsed[0] if parsed else "empty"
    return out


def layer_stack_signature_for_key(key: dict[str, str]) -> str:
    return "+".join(layer for layer in STANDARD_LAYERS if key.get(layer) != "empty") or "empty"


def decision_status_for_cases(cases: list[dict[str, Any]]) -> tuple[str, str | None]:
    decisions = [case.get("humanDecision") for case in cases if case.get("humanDecision")]
    if not decisions:
        return "unreviewed", None
    counts = Counter(decisions)
    if len(counts) > 1:
        return "mixed", None
    decision = decisions[0]
    if len(decisions) == len(cases):
        return "reviewed", decision
    return "mixed", decision


def group_entries(entries: list[dict[str, Any]], review_pack_id: str = "", group_name: str = "") -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_pack_id = str(review_pack_id or entry.get("reviewPackId") or "")
        entry_group_name = str(group_name or entry.get("reviewGroup") or "")
        key = combination_key_for_case(entry)
        combination_hash = combination_hash_for_key(key)
        entry["combinationKey"] = key
        entry["combinationHash"] = combination_hash
        entry["layerStackSignature"] = layer_stack_signature_for_key(key)
        if combination_hash not in grouped:
            grouped[combination_hash] = {
                "combinationHash": combination_hash,
                "combinationKey": key,
                "layerStackSignature": entry["layerStackSignature"],
                "tileIdsByLayer": key,
                "sourceTilesheetsByLayer": source_tilesheets_for_key(key),
                "reviewPackIds": set(),
                "reviewGroups": set(),
                "cases": [],
                "caseIds": [],
                "mapsUsedIn": set(),
                "exampleCoordinates": [],
                "currentClassifications": Counter(),
                "reasonNeedsReviewCounts": Counter(),
                "suggestedDecisionCounts": Counter(),
                "containsTile946": False,
                "containsUnsafe946": False,
            }
        group = grouped[combination_hash]
        if entry_pack_id:
            group["reviewPackIds"].add(entry_pack_id)
        if entry_group_name:
            group["reviewGroups"].add(entry_group_name)
        group["cases"].append(entry)
        group["caseIds"].append(entry.get("caseId"))
        group["mapsUsedIn"].add(entry.get("mapName"))
        if len(group["exampleCoordinates"]) < 25:
            group["exampleCoordinates"].append(
                {
                    "caseId": entry.get("caseId"),
                    "mapName": entry.get("mapName"),
                    "x": entry.get("x"),
                    "y": entry.get("y"),
                    "layerStack": entry.get("layerStack"),
                    "reviewPackId": review_pack_id,
                }
            )
        if entry.get("currentClassification"):
            group["currentClassifications"][entry["currentClassification"]] += 1
        if entry.get("reasonNeedsReview"):
            group["reasonNeedsReviewCounts"][entry["reasonNeedsReview"]] += 1
        group["suggestedDecisionCounts"][normalize_suggestion(entry.get("suggestedDecision"))] += 1
        group["containsTile946"] = bool(group["containsTile946"] or any(tile_id_is_946(tile) for tile in key.values()))
        group["containsUnsafe946"] = bool(group["containsUnsafe946"] or is_unsafe_tile_946_case(entry))
    return grouped


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    cases = group.pop("cases")
    status, decision = decision_status_for_cases(cases)
    reason_counts = dict(group["reasonNeedsReviewCounts"])
    suggested_counts = dict(group["suggestedDecisionCounts"])
    classifications = dict(group["currentClassifications"])
    risk_flags = []
    if group["containsUnsafe946"]:
        risk_flags.append("unsafe_tile_946")
    elif group["containsTile946"]:
        risk_flags.append("tile_946_requires_manual_scope_check")
    if len(suggested_counts) > 1:
        risk_flags.append("mixed_suggested_decisions")
    if len(reason_counts) > 1:
        risk_flags.append("mixed_review_reasons")
    if len(group["mapsUsedIn"]) > 3:
        risk_flags.append("multi_map_group")
    return {
        **group,
        "reviewPackIds": sorted(group["reviewPackIds"]),
        "reviewGroups": sorted(group["reviewGroups"]),
        "occurrenceCount": len(group["caseIds"]),
        "mapsUsedIn": sorted(value for value in group["mapsUsedIn"] if value),
        "currentClassifications": classifications,
        "reasonNeedsReviewCounts": reason_counts,
        "suggestedDecisionCounts": suggested_counts,
        "containsTile946": bool(group["containsTile946"]),
        "containsUnsafe946": bool(group["containsUnsafe946"]),
        "riskFlags": risk_flags,
        "decisionStatus": status,
        "humanDecision": decision,
        "unsafeBlockedDecisions": sorted(UNSAFE_946_DECISIONS) if group["containsUnsafe946"] else [],
    }


def load_review_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(REVIEW_PACK_ROOT.glob("*.json")):
        data = load_json(path, {})
        review_pack_id = data.get("reviewPackId") or path.stem
        group_name = data.get("group") or ""
        for entry in data.get("entries", []):
            entries.append({**entry, "reviewPackId": review_pack_id, "reviewGroup": group_name})
    return entries


def build_combination_index(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    entries = entries if entries is not None else load_review_entries()
    grouped = group_entries(entries)
    groups = [finalize_group(group) for group in grouped.values()]
    groups.sort(key=lambda item: (-item["occurrenceCount"], item["layerStackSignature"], item["combinationHash"]))
    repeated_groups = [group for group in groups if group["occurrenceCount"] > 1]
    by_pack: dict[str, list[str]] = defaultdict(list)
    for group in groups:
        for pack_id in group["reviewPackIds"]:
            by_pack[pack_id].append(group["combinationHash"])
    return {
        "generatedAt": now_iso(),
        "source": "build_exception_review_combination_index.py",
        "combinationKeyLayers": STANDARD_LAYERS,
        "combinationHashAlgorithm": "sha256(json(sorted Back/Buildings/Front/AlwaysFront/Paths tile strings or empty))[0:16]",
        "totalCases": len(entries),
        "uniqueCombinationCount": len(groups),
        "repeatedCombinationCount": len(repeated_groups),
        "casesCoveredByRepeatedCombinations": sum(group["occurrenceCount"] for group in repeated_groups),
        "groupsByPack": dict(sorted((key, sorted(value)) for key, value in by_pack.items())),
        "groups": groups,
    }


def main() -> int:
    index = build_combination_index()
    write_json(COMBINATION_INDEX_PATH, index)
    print(
        json.dumps(
            {
                "cases": index["totalCases"],
                "uniqueCombinations": index["uniqueCombinationCount"],
                "repeatedCombinations": index["repeatedCombinationCount"],
                "casesCoveredByRepeatedCombinations": index["casesCoveredByRepeatedCombinations"],
                "path": str(COMBINATION_INDEX_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
