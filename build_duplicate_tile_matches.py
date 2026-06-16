import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
SEED_ROOT = TOOL_ROOT / "review" / "seed_approval"
DUP_ROOT = TOOL_ROOT / "review" / "duplicate_resolution"

HASH_INDEX_PATH = DUP_ROOT / "tile_hash_index.json"
SEED_DECISIONS_PATH = SEED_ROOT / "grass_seed_manual_decisions.json"

RESTRICTED_DEEPWOODS_MARKERS = {
    "deepwoodslaketilesheet",
    "deepwoodsinfestedoutdoorstilesheet",
    "deepwoodsmod-main",
    "deepwoodsmod\\src\\deepwoods\\assets",
    "deepwoodsmod/src/deepwoods/assets",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_family(name):
    stem = Path(str(name)).stem.lower()
    stem = re.sub(r"^(spring|summer|fall|winter)_", "", stem)
    stem = stem.replace("-copy", "").replace("_copy", "")
    return stem


def restricted(entry):
    haystack = " ".join(str(entry.get(key, "")) for key in ("copiedImagePath", "tilesheetName", "sourceMod", "sourceCategory")).lower()
    return any(marker in haystack for marker in RESTRICTED_DEEPWOODS_MARKERS)


def load_seed_approvals():
    if not SEED_DECISIONS_PATH.exists():
        return [], "No `grass_seed_manual_decisions.json` file exists yet; duplicate proposal is waiting for human seed approvals."
    doc = load_json(SEED_DECISIONS_PATH)
    approvals = []
    reviewer = doc.get("reviewer")
    for decision in doc.get("decisions", []):
        if str(decision.get("decision", "")).lower() != "approve":
            continue
        profiles = decision.get("usageProfiles") or []
        if not profiles:
            continue
        approvals.append(
            {
                "candidateId": decision.get("candidateId"),
                "reviewer": reviewer,
                "usageProfiles": profiles,
                "notes": decision.get("notes", ""),
            }
        )
    if not approvals:
        return [], "`grass_seed_manual_decisions.json` exists, but contains no approved seed decisions."
    return approvals, None


def layer_profile_supported(entry, profile):
    observed = entry.get("observedLayers") or {}
    total = sum(int(v) for v in observed.values())
    allowed = set(profile.get("allowedLayers") or [])
    if not allowed:
        return False, "profile has no allowed layers"
    if total <= 0:
        return False, "duplicate has no observed layer usage"
    allowed_count = sum(int(count) for layer, count in observed.items() if layer in allowed)
    allowed_fraction = allowed_count / total
    dominant_layer = max(observed.items(), key=lambda kv: int(kv[1]))[0] if observed else None
    if dominant_layer not in allowed:
        return False, f"dominant layer `{dominant_layer}` is outside inherited profile layers {sorted(allowed)}"
    if allowed_fraction < 0.8:
        return False, f"allowed layer fraction {allowed_fraction:.2f} is below 0.80"
    collision = profile.get("collision")
    if collision == "walkable" and int(observed.get("Buildings", 0)) / total > 0.2:
        return False, "walkable profile conflicts with substantial Buildings-layer usage"
    return True, f"dominant layer `{dominant_layer}` and allowed fraction {allowed_fraction:.2f} support profile"


def compatible_family(seed, candidate):
    seed_family = seed.get("tilesheetFamily") or normalize_family(seed.get("tilesheetName"))
    candidate_family = candidate.get("tilesheetFamily") or normalize_family(candidate.get("tilesheetName"))
    if seed_family == candidate_family:
        return True
    if "outdoorstilesheet" in seed_family and "outdoorstilesheet" in candidate_family:
        return True
    return False


def main():
    DUP_ROOT.mkdir(parents=True, exist_ok=True)
    if not HASH_INDEX_PATH.exists():
        raise SystemExit(f"Missing hash index: {HASH_INDEX_PATH}")
    hash_doc = load_json(HASH_INDEX_PATH)
    entries = hash_doc.get("entries", [])
    by_candidate = {entry["candidateId"]: entry for entry in entries if entry.get("candidateId")}
    by_hash = defaultdict(list)
    for entry in entries:
        by_hash[entry.get("hashExact")].append(entry)

    seed_approvals, waiting_reason = load_seed_approvals()
    matches = []
    conflicts = []
    if waiting_reason:
        metadata = {
            "generatedAt": now_iso(),
            "status": "waiting_for_human_seed_approvals",
            "reason": waiting_reason,
            "matchesCount": 0,
            "conflictsCount": 0,
        }
        write_json(DUP_ROOT / "duplicate_tile_matches.json", {**metadata, "matches": []})
        write_json(DUP_ROOT / "duplicate_tile_conflicts.json", {**metadata, "conflicts": []})
        write_json(DUP_ROOT / "duplicate_auto_approval_preview.json", {**metadata, "proposedApprovals": []})
        print(waiting_reason)
        return

    for seed in seed_approvals:
        seed_entry = by_candidate.get(seed.get("candidateId"))
        if not seed_entry:
            conflicts.append({"seedCandidateId": seed.get("candidateId"), "reason": "approved seed candidate is not present in tile_hash_index"})
            continue
        if restricted(seed_entry):
            conflicts.append({"seedCandidateId": seed.get("candidateId"), "reason": "approved seed candidate is a restricted DeepWoods asset"})
            continue
        for duplicate in by_hash.get(seed_entry.get("hashExact"), []):
            if duplicate.get("candidateId") == seed_entry.get("candidateId"):
                continue
            if restricted(duplicate):
                conflicts.append(
                    {
                        "seedCandidateId": seed_entry.get("candidateId"),
                        "candidateId": duplicate.get("candidateId"),
                        "hashExact": seed_entry.get("hashExact"),
                        "reason": "duplicate candidate uses restricted DeepWoods asset",
                    }
                )
                continue
            if not compatible_family(seed_entry, duplicate):
                conflicts.append(
                    {
                        "seedCandidateId": seed_entry.get("candidateId"),
                        "candidateId": duplicate.get("candidateId"),
                        "hashExact": seed_entry.get("hashExact"),
                        "reason": "tilesheet family differs from approved seed",
                        "seedFamily": seed_entry.get("tilesheetFamily"),
                        "candidateFamily": duplicate.get("tilesheetFamily"),
                    }
                )
                continue
            for profile in seed.get("usageProfiles", []):
                supported, reason = layer_profile_supported(duplicate, profile)
                if not supported:
                    conflicts.append(
                        {
                            "seedCandidateId": seed_entry.get("candidateId"),
                            "candidateId": duplicate.get("candidateId"),
                            "hashExact": seed_entry.get("hashExact"),
                            "profileId": profile.get("profileId"),
                            "reason": reason,
                        }
                    )
                    continue
                match = {
                    "candidateId": duplicate.get("candidateId"),
                    "matchedSeedCandidateId": seed_entry.get("candidateId"),
                    "hashExact": seed_entry.get("hashExact"),
                    "inheritedUsageProfile": profile,
                    "approvedClass": profile.get("approvedClass"),
                    "approvedPurpose": profile.get("approvedPurpose"),
                    "allowedLayers": profile.get("allowedLayers") or [],
                    "collision": profile.get("collision"),
                    "confidence": 90,
                    "reason": "exact_duplicate_of_human_approved_seed_with_matching_layer_usage_profile",
                    "approvedBy": "codex_duplicate_evidence_pending_validation",
                    "approved": False,
                    "tilesheetName": duplicate.get("tilesheetName"),
                    "copiedImagePath": duplicate.get("copiedImagePath"),
                    "localTileId": duplicate.get("localTileId"),
                    "observedLayers": duplicate.get("observedLayers") or {},
                    "observedCountTotal": duplicate.get("observedCountTotal", 0),
                }
                matches.append(match)

    metadata = {
        "generatedAt": now_iso(),
        "status": "proposals_created_pending_validation",
        "seedApprovalsRead": len(seed_approvals),
        "matchesCount": len(matches),
        "conflictsCount": len(conflicts),
    }
    write_json(DUP_ROOT / "duplicate_tile_matches.json", {**metadata, "matches": matches})
    write_json(DUP_ROOT / "duplicate_tile_conflicts.json", {**metadata, "conflicts": conflicts})
    write_json(DUP_ROOT / "duplicate_auto_approval_preview.json", {**metadata, "proposedApprovals": matches})
    print(f"duplicate matches: {len(matches)}; conflicts: {len(conflicts)}")


if __name__ == "__main__":
    main()
