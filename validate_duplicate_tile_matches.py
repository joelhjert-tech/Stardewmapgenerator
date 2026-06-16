import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
CLASS_ROOT = TOOL_ROOT / "classification"
SEED_ROOT = TOOL_ROOT / "review" / "seed_approval"
DUP_ROOT = TOOL_ROOT / "review" / "duplicate_resolution"
REPORTS_ROOT = TOOL_ROOT / "reports"
STYLEPACK_ROOT = TOOL_ROOT / "stylepacks"

HASH_INDEX_PATH = DUP_ROOT / "tile_hash_index.json"
PREVIEW_PATH = DUP_ROOT / "duplicate_auto_approval_preview.json"
SEED_DECISIONS_PATH = SEED_ROOT / "grass_seed_manual_decisions.json"
SCHEMA_PATH = CLASS_ROOT / "tile_class_schema.json"

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "AlwaysFront2", "Paths", "Objects", "Map"}
VALID_COLLISIONS = {"unknown", "walkable", "blocked", "blocks", "decorative", "front_only", "water", "custom", "profile_specific"}
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


def restricted(entry):
    haystack = " ".join(str(entry.get(key, "")) for key in ("copiedImagePath", "tilesheetName", "sourceMod", "sourceCategory")).lower()
    return any(marker in haystack for marker in RESTRICTED_DEEPWOODS_MARKERS)


def profile_signature(profile):
    fields = ["approvedClass", "approvedPurpose", "allowedLayers", "collision", "layerRole", "terrainSet", "terrainA", "terrainB", "transitionType", "footprint"]
    return json.dumps({field: profile.get(field) for field in fields}, sort_keys=True)


def load_seed_profile_index():
    index = defaultdict(dict)
    if not SEED_DECISIONS_PATH.exists():
        return index
    doc = load_json(SEED_DECISIONS_PATH)
    for decision in doc.get("decisions", []):
        if str(decision.get("decision", "")).lower() != "approve":
            continue
        cid = decision.get("candidateId")
        for profile in decision.get("usageProfiles") or []:
            profile_id = profile.get("profileId")
            if profile_id:
                index[cid][profile_id] = profile
    return index


def load_existing_approved_profiles():
    approved = defaultdict(dict)
    root = CLASS_ROOT / "approved_tags"
    if not root.exists():
        return approved
    for path in sorted(root.glob("*.approved_tags.json")):
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
                for profile in profiles or []:
                    profile_id = profile.get("profileId")
                    if profile_id:
                        approved[cid][profile_id] = profile
    return approved


def layer_profile_supported(entry, profile):
    observed = entry.get("observedLayers") or {}
    total = sum(int(v) for v in observed.values())
    allowed = set(profile.get("allowedLayers") or [])
    if total <= 0:
        return False, "no observed layer usage"
    if not allowed:
        return False, "profile has no allowedLayers"
    allowed_count = sum(int(v) for layer, v in observed.items() if layer in allowed)
    dominant = max(observed.items(), key=lambda kv: int(kv[1]))[0] if observed else None
    if dominant not in allowed:
        return False, f"dominant layer {dominant} is outside allowedLayers"
    if allowed_count / total < 0.8:
        return False, "allowed layer fraction below 0.80"
    return True, "layer usage supports profile"


def validate_stylepack_variant_limits(errors):
    for path in sorted(STYLEPACK_ROOT.glob("*.json")):
        try:
            doc = load_json(path)
        except Exception as exc:
            errors.append(f"- {path.name}: invalid JSON: {exc}")
            continue
        max_variants = int((doc.get("variantPolicy") or {}).get("maxActiveVariantsPerDesignRole", 4))
        groups = {}
        groups.update(doc.get("groups") or {})
        groups.update(doc.get("semanticGroups") or {})
        for role, values in groups.items():
            if isinstance(values, list) and len(values) > max_variants:
                errors.append(f"- {path.name} `{role}` has {len(values)} active variants; limit is {max_variants}.")


def main():
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    errors = []
    warnings = []
    if not HASH_INDEX_PATH.exists():
        errors.append(f"- Missing hash index: {HASH_INDEX_PATH}")
        hash_doc = {"entries": []}
    else:
        hash_doc = load_json(HASH_INDEX_PATH)
    if not PREVIEW_PATH.exists():
        errors.append(f"- Missing duplicate approval preview: {PREVIEW_PATH}")
        preview = {"proposedApprovals": []}
    else:
        preview = load_json(PREVIEW_PATH)
    schema = load_json(SCHEMA_PATH)
    valid_classes = set(schema.keys())
    entries = hash_doc.get("entries", [])
    by_candidate = {entry["candidateId"]: entry for entry in entries if entry.get("candidateId")}
    seed_profiles = load_seed_profile_index()
    existing_approved = load_existing_approved_profiles()

    for index, proposal in enumerate(preview.get("proposedApprovals", []), start=1):
        prefix = f"- proposal #{index} candidate {proposal.get('candidateId')}:"
        if proposal.get("approved") is not False:
            errors.append(f"{prefix} duplicate proposals must keep approved:false until Joel accepts the merge.")
        candidate = by_candidate.get(proposal.get("candidateId"))
        seed = by_candidate.get(proposal.get("matchedSeedCandidateId"))
        if not candidate:
            errors.append(f"{prefix} candidate is not present in tile_hash_index.")
            continue
        if not seed:
            errors.append(f"{prefix} matched seed is not present in tile_hash_index.")
            continue
        if seed.get("hashExact") != candidate.get("hashExact") or proposal.get("hashExact") != candidate.get("hashExact"):
            errors.append(f"{prefix} exact hash mismatch.")
        profile = proposal.get("inheritedUsageProfile") or {}
        profile_id = profile.get("profileId")
        seed_profile = seed_profiles.get(proposal.get("matchedSeedCandidateId"), {}).get(profile_id)
        if not seed_profile:
            errors.append(f"{prefix} inherited profile `{profile_id}` is not backed by a human-approved seed decision.")
        elif profile_signature(seed_profile) != profile_signature(profile):
            errors.append(f"{prefix} inherited profile does not match the approved seed profile.")
        if profile.get("approvedClass") not in valid_classes:
            errors.append(f"{prefix} approvedClass `{profile.get('approvedClass')}` is not in tile_class_schema.json.")
        for layer in profile.get("allowedLayers") or []:
            if layer not in VALID_LAYERS:
                errors.append(f"{prefix} invalid allowedLayer `{layer}`.")
        if profile.get("collision") not in VALID_COLLISIONS:
            errors.append(f"{prefix} invalid collision `{profile.get('collision')}`.")
        if restricted(candidate) or restricted(seed):
            errors.append(f"{prefix} restricted DeepWoods image dependency detected.")
        supported, reason = layer_profile_supported(candidate, profile)
        if not supported:
            errors.append(f"{prefix} layer conflict for inherited profile: {reason}.")
        existing = existing_approved.get(proposal.get("candidateId"), {}).get(profile_id)
        if existing and profile_signature(existing) != profile_signature(profile):
            errors.append(f"{prefix} conflicts with an existing approved profile.")

    validate_stylepack_variant_limits(errors)

    lines = [
        "# Duplicate Tile Validation Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Duplicate proposals scanned: {len(preview.get('proposedApprovals', []))}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Result: {'PASS' if not errors else 'FAIL'}",
        "",
        "## Errors",
        *(errors or ["- None."]),
        "",
        "## Warnings",
        *(warnings or ["- None."]),
    ]
    (REPORTS_ROOT / "duplicate_tile_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"duplicate validation: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
