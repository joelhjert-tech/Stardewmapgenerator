import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ijson


TOOL_ROOT = Path(__file__).resolve().parent
CLASS_ROOT = TOOL_ROOT / "classification"
DB_ROOT = TOOL_ROOT / "database"
REPORTS_ROOT = TOOL_ROOT / "reports"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def tags_from_doc(doc):
    if isinstance(doc, list):
        return doc
    return doc.get("tags", [])


def normalized_profiles(tag):
    profiles = tag.get("usageProfiles")
    if profiles:
        return profiles
    evidence = []
    if tag.get("evidenceSummary"):
        evidence.append(tag.get("evidenceSummary"))
    if tag.get("reason"):
        evidence.append(tag.get("reason"))
    return [
        {
            "profileId": tag.get("profileId") or "legacy_default",
            "approvedClass": tag.get("approvedClass"),
            "approvedPurpose": tag.get("approvedPurpose"),
            "allowedLayers": tag.get("allowedLayers") or [],
            "collision": tag.get("collision", "unknown"),
            "layerRole": tag.get("layerRole") or "legacy_single_profile",
            "evidence": tag.get("evidence") or evidence,
            "notes": tag.get("notes") or tag.get("safetyNotes") or tag.get("reason", ""),
            "terrainSet": tag.get("terrainSet"),
            "terrainA": tag.get("terrainA"),
            "terrainB": tag.get("terrainB"),
            "edgeMask": tag.get("edgeMask") or [],
            "cornerMask": tag.get("cornerMask") or [],
            "transitionType": tag.get("transitionType"),
            "footprint": tag.get("footprint"),
            "allowedRooms": tag.get("allowedRooms") or [],
            "avoidNear": tag.get("avoidNear") or [],
            "weight": tag.get("weight", 1),
        }
    ]


def approval_source(tag):
    if tag.get("source") == "vanilla_tbin_intrinsic_metadata_and_byte_identical_tilesheet":
        return "vanilla_basegame_authoritative_metadata"
    if tag.get("approvedBy") == "human":
        return "manual_usage_profile_review"
    return tag.get("source") or "approved_tags"


def tag_approval_meta(tag, path):
    notes = tag.get("safetyNotes") or tag.get("evidenceSummary") or tag.get("reason") or tag.get("notes") or ""
    return {
        "approvedBy": tag.get("approvedBy"),
        "approvedAt": tag.get("approvedAt"),
        "approvalSource": approval_source(tag),
        "approvalConfidence": tag.get("confidence"),
        "approvalNotes": notes,
        "approvalEvidenceSourceFile": tag.get("evidenceSourceFile"),
        "approvalTagFile": path.name,
        "source": tag.get("source"),
    }


def combine_meta(metas):
    metas = [m for m in metas if m]
    if not metas:
        return {
            "approvedBy": None,
            "approvedAt": datetime.now(timezone.utc).isoformat(),
            "approvalSource": "approved_tags",
            "approvalConfidence": None,
            "approvalNotes": "",
            "approvalEvidenceSourceFile": None,
        }
    confidences = [m.get("approvalConfidence") for m in metas if isinstance(m.get("approvalConfidence"), (int, float))]
    sources = sorted({m.get("approvalSource") for m in metas if m.get("approvalSource")})
    approved_by = sorted({m.get("approvedBy") for m in metas if m.get("approvedBy")})
    evidence = sorted({m.get("approvalEvidenceSourceFile") for m in metas if m.get("approvalEvidenceSourceFile")})
    notes = []
    for m in metas:
        note = m.get("approvalNotes")
        if note and note not in notes:
            notes.append(note)
    return {
        "approvedBy": approved_by[0] if len(approved_by) == 1 else "mixed",
        "approvedAt": max([m.get("approvedAt") for m in metas if m.get("approvedAt")] or [datetime.now(timezone.utc).isoformat()]),
        "approvalSource": sources[0] if len(sources) == 1 else "mixed",
        "approvalConfidence": max(confidences) if confidences else None,
        "approvalNotes": " | ".join(notes),
        "approvalEvidenceSourceFile": evidence[0] if len(evidence) == 1 else evidence,
    }


def approved_profiles_by_candidate():
    profiles_by_candidate = {}
    conflicts = []
    for path in sorted((CLASS_ROOT / "approved_tags").glob("*.approved_tags.json")):
        doc = load_json(path)
        for tag in tags_from_doc(doc):
            profiles = normalized_profiles(tag)
            meta = tag_approval_meta(tag, path)
            for cid in tag.get("candidateIds") or []:
                record = profiles_by_candidate.setdefault(cid, {"profiles": {}, "metas": []})
                bucket = record["profiles"]
                record["metas"].append(meta)
                for profile in profiles:
                    profile_id = profile.get("profileId")
                    if not profile_id:
                        continue
                    existing = bucket.get(profile_id)
                    if existing and existing != profile:
                        conflicts.append(f"{cid}:{profile_id}")
                    bucket[profile_id] = profile
    if conflicts:
        raise RuntimeError(f"conflicting approved profiles for {len(set(conflicts))} candidate profiles")
    return {
        cid: {"profiles": list(record["profiles"].values()), "meta": combine_meta(record["metas"])}
        for cid, record in profiles_by_candidate.items()
    }


def skeleton_keys_by_candidate(wanted):
    mapping = {}
    wanted = set(wanted)
    if not wanted:
        return mapping
    with (CLASS_ROOT / "canonical_tile_candidates.json").open("rb") as handle:
        for candidate in ijson.items(handle, "item"):
            cid = candidate.get("candidateId")
            if cid in wanted:
                mapping[cid] = (str(candidate.get("copiedImagePath") or "").lower(), str(candidate.get("localTileId")))
                if len(mapping) == len(wanted):
                    break
    return mapping


def main():
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    validator = subprocess.run([sys.executable, str(TOOL_ROOT / "validate_approved_tags.py")], cwd=str(TOOL_ROOT.parent.parent), text=True)
    if validator.returncode != 0:
        raise SystemExit("Validation failed; merge aborted. See reports/approved_tag_validation_report.md.")

    out_path = DB_ROOT / "tile_database_v1_human_approved.json"
    source_path = out_path if out_path.exists() else DB_ROOT / "tile_database_skeleton.json"
    approvals_by_candidate = approved_profiles_by_candidate()
    if not approvals_by_candidate:
        report = [
            "# Approved Tag Merge Report",
            "",
            f"- Generated: {datetime.now(timezone.utc).isoformat()}",
            f"- Source database: {source_path}",
            f"- Output database: {out_path}",
            "- Approved candidate tags applied: 0",
            "- Unapproved candidates preserved: all existing database entries",
            "- Notes: no approved tag files were present, so the approved database was left unchanged.",
        ]
        (REPORTS_ROOT / "approved_tag_merge_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print("No approved tags found; database left unchanged.")
        return
    key_by_candidate = skeleton_keys_by_candidate(approvals_by_candidate.keys())
    tags_by_skeleton_key = {}
    skipped_candidates = []
    for cid, approval in approvals_by_candidate.items():
        key = key_by_candidate.get(cid)
        if key:
            tags_by_skeleton_key[key] = approval
        else:
            skipped_candidates.append(cid)
    approved_count = 0
    class_breakdown = {}
    collision_breakdown = {}

    data = load_json(source_path)
    for tile in data:
        key = (str(tile.get("copiedImagePath") or "").lower(), str(tile.get("localTileId")))
        approval = tags_by_skeleton_key.get(key)
        if not approval:
            continue
        profiles = approval["profiles"]
        meta = approval["meta"]
        approved_count += 1
        tile["approved"] = True
        tile["needsHumanReview"] = False
        tile["usageProfiles"] = profiles
        if len(profiles) == 1:
            profile = profiles[0]
            tile["finalClass"] = profile.get("approvedClass")
            tile["finalPurpose"] = profile.get("approvedPurpose")
            tile["purpose"] = profile.get("approvedPurpose")
            tile["allowedLayers"] = profile.get("allowedLayers") or []
            tile["collision"] = profile.get("collision", "unknown")
            tile["terrainSet"] = profile.get("terrainSet")
            tile["terrainA"] = profile.get("terrainA")
            tile["terrainB"] = profile.get("terrainB")
            tile["edgeMask"] = profile.get("edgeMask") or []
            tile["cornerMask"] = profile.get("cornerMask") or []
            tile["transitionType"] = profile.get("transitionType")
            tile["footprint"] = profile.get("footprint")
            tile["allowedRooms"] = profile.get("allowedRooms") or []
            tile["avoidNear"] = profile.get("avoidNear") or []
            tile["weight"] = profile.get("weight", 1)
            class_breakdown[tile["finalClass"]] = class_breakdown.get(tile["finalClass"], 0) + 1
            collision_breakdown[tile["collision"]] = collision_breakdown.get(tile["collision"], 0) + 1
        else:
            tile["finalClass"] = None
            tile["finalPurpose"] = None
            tile["purpose"] = "multi_profile"
            tile["allowedLayers"] = sorted({layer for profile in profiles for layer in profile.get("allowedLayers", [])})
            tile["collision"] = "profile_specific"
            class_breakdown["multi_profile"] = class_breakdown.get("multi_profile", 0) + 1
            collision_breakdown["profile_specific"] = collision_breakdown.get("profile_specific", 0) + 1
        tile["approvalModel"] = "usageProfiles"
        tile["approvalSource"] = meta.get("approvalSource")
        tile["approvalConfidence"] = meta.get("approvalConfidence")
        tile["approvalNotes"] = meta.get("approvalNotes")
        tile["approvalEvidenceSourceFile"] = meta.get("approvalEvidenceSourceFile")
        tile["approvedBy"] = meta.get("approvedBy")
        tile["approvedAt"] = meta.get("approvedAt") or datetime.now(timezone.utc).isoformat()

    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    report = [
        "# Approved Tag Merge Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Source database: {source_path}",
        f"- Output database: {out_path}",
        f"- Approved candidate tags applied: {approved_count}",
        f"- Unapproved candidates preserved unchanged: {len(data) - approved_count}",
        f"- Skipped candidateIds without database key: {len(skipped_candidates)}",
        "",
        "## Class Breakdown",
        *[f"- {key}: {value}" for key, value in sorted(class_breakdown.items())],
        "",
        "## Collision Breakdown",
        *[f"- {key}: {value}" for key, value in sorted(collision_breakdown.items())],
    ]
    (REPORTS_ROOT / "approved_tag_merge_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Merged {approved_count} approved candidates into {out_path}.")


if __name__ == "__main__":
    main()
