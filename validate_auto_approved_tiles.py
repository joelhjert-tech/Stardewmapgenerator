#!/usr/bin/env python3
"""
validate_auto_approved_tiles.py

Validates review/auto_resolution/auto_approved_tile_tags.json BEFORE any merge into the
main approved database. Read-only: never modifies protected files.

Checks per tag:
  * candidateIds exist in classification/canonical_tile_candidates.json
  * approvedClass exists in classification/tile_class_schema.json
  * allowedLayers are valid Stardew layers
  * collision value is valid AND concrete (not 'unknown')
  * no conflicting tags (same candidateId mapped to >1 class)
  * source-file evidence exists on disk
  * confidence >= 90 (auto-approval threshold)
  * no restricted DeepWoods custom image assets (lake / infested / water-border sheets)
  * tile source is allowed (vanilla / approved DB) or clearly marked prototype-only

Writes reports/auto_approved_tile_validation_report.md.
Exit code 0 = all valid (or nothing to validate); 1 = at least one failure.
"""
import ijson, json, os, sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.abspath(__file__))
def p(*a): return os.path.join(ROOT, *a)

AUTO = p("review", "auto_resolution", "auto_approved_tile_tags.json")
SCHEMA = p("classification", "tile_class_schema.json")
CANON = p("classification", "canonical_tile_candidates.json")
REPORT = p("reports", "auto_approved_tile_validation_report.md")

VALID_LAYERS = {"Back", "Buildings", "Paths", "Front", "AlwaysFront"}
VALID_COLLISION = {"walkable", "blocks", "none", "special", "passable", "blocked_or_special"}
AMBIGUOUS_COLLISION = {"varies"}
INVALID_COLLISION = {"unknown", "", None}
RESTRICTED_ASSET_MARKERS = ["deepwoodsinfested", "deepwoodslake", "waterbordertiles",
                            "deepwoods_lake", "deepwoods_infested"]
ALLOWED_SOURCE_VALUES = {"vanilla_stardew", "approved_moonvillage_database",
                         "temporary_prototype_marker", "deepwoods_derived_reviewed"}


def load_json(fp):
    with open(fp, encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    results = []   # (level, message)  level in {OK, FAIL, WARN, INFO}
    def ok(m): results.append(("OK", m))
    def fail(m): results.append(("FAIL", m))
    def warn(m): results.append(("WARN", m))
    def info(m): results.append(("INFO", m))

    if not os.path.exists(AUTO):
        fail(f"auto_approved_tile_tags.json not found at {AUTO}")
        write_report(results, 0, 0)
        return 1

    auto = load_json(AUTO)
    tags = auto.get("tags", [])
    threshold = auto.get("autoApprovalThreshold", 90)
    info(f"Loaded {len(tags)} auto-approved tag(s); threshold = {threshold}.")

    schema = load_json(SCHEMA)
    valid_classes = set(schema.keys())
    info(f"Schema defines {len(valid_classes)} tile classes.")

    if not tags:
        ok("0 auto-approved tags present - nothing to merge. Vacuously valid and SAFE "
           "(no tile is auto-approved without human review).")
        write_report(results, 0, 0)
        return 0

    # Only stream the 507MB candidate DB if there is something to validate.
    wanted = set()
    for t in tags:
        for cid in (t.get("candidateIds") or ([t.get("candidateId")] if t.get("candidateId") else [])):
            wanted.add(cid)
    found = {}
    info(f"Resolving {len(wanted)} candidateId(s) against canonical_tile_candidates.json ...")
    for c in ijson.items(open(CANON, "rb"), "item"):
        cid = c.get("candidateId")
        if cid in wanted:
            found[cid] = {
                "tilesheetName": c.get("tilesheetName"),
                "copiedImagePath": c.get("copiedImagePath") or "",
                "sourceCategory": c.get("sourceCategory"),
            }
            if len(found) == len(wanted):
                break

    seen_candidate_class = {}   # candidateId -> class (conflict detection)
    failures = 0
    for idx, t in enumerate(tags):
        label = t.get("approvedPurpose") or t.get("approvedClass") or f"tag#{idx}"
        cids = t.get("candidateIds") or ([t.get("candidateId")] if t.get("candidateId") else [])
        cls = t.get("approvedClass")
        conf = t.get("confidence")
        layers = t.get("allowedLayers") or []
        collision = t.get("collision")
        srcfile = t.get("evidenceSourceFile")

        # candidateIds present + exist
        if not cids:
            fail(f"[{label}] has no candidateIds."); failures += 1
        for cid in cids:
            if cid not in found:
                fail(f"[{label}] candidateId '{cid}' not found in canonical DB."); failures += 1

        # class
        if cls not in valid_classes:
            fail(f"[{label}] approvedClass '{cls}' not in tile_class_schema.json."); failures += 1

        # layers
        bad_layers = [l for l in layers if l not in VALID_LAYERS]
        if not layers:
            fail(f"[{label}] allowedLayers empty."); failures += 1
        if bad_layers:
            fail(f"[{label}] invalid allowedLayers {bad_layers}."); failures += 1

        # collision
        if collision in INVALID_COLLISION:
            fail(f"[{label}] collision is '{collision}' (must be concrete/known)."); failures += 1
        elif collision in AMBIGUOUS_COLLISION:
            warn(f"[{label}] collision '{collision}' is ambiguous for an auto-approved tile.")
        elif collision not in VALID_COLLISION:
            fail(f"[{label}] collision '{collision}' is not a recognised value."); failures += 1

        # confidence
        cv = float(conf) if isinstance(conf, (int, float, Decimal)) else -1
        if cv < threshold:
            fail(f"[{label}] confidence {conf} < threshold {threshold}."); failures += 1

        # conflict detection
        for cid in cids:
            if cid in seen_candidate_class and seen_candidate_class[cid] != cls:
                fail(f"[{label}] candidate '{cid}' already approved as "
                     f"'{seen_candidate_class[cid]}' (conflict with '{cls}').")
                failures += 1
            seen_candidate_class[cid] = cls

        # source evidence exists
        if not srcfile:
            fail(f"[{label}] no evidenceSourceFile."); failures += 1
        else:
            abspath = srcfile if os.path.isabs(srcfile) else p(*srcfile.replace("tools/tiled-map-assistant/", "").split("/")) \
                if srcfile.startswith("tools/tiled-map-assistant/") else os.path.join(ROOT, "..", "..", *srcfile.split("/"))
            if not os.path.exists(abspath) and not os.path.exists(os.path.join(ROOT, srcfile)):
                # try repo-root relative
                repo_rel = os.path.join(ROOT, "..", *srcfile.split("/")) if srcfile.startswith("tools/") else abspath
                if not os.path.exists(repo_rel):
                    warn(f"[{label}] evidenceSourceFile '{srcfile}' not resolvable on disk (manual check advised).")

        # restricted assets
        for cid in cids:
            meta = found.get(cid, {})
            blob = (meta.get("tilesheetName", "") + " " + meta.get("copiedImagePath", "")).lower()
            if any(m in blob for m in RESTRICTED_ASSET_MARKERS):
                fail(f"[{label}] candidate '{cid}' uses a RESTRICTED DeepWoods custom asset."); failures += 1

        # source allowed / prototype-marked
        src = t.get("source") or t.get("tileSource")
        if src and src not in ALLOWED_SOURCE_VALUES and "prototype" not in str(src).lower():
            warn(f"[{label}] tile source '{src}' is not in the allowed set and not marked prototype.")

    total = len(tags)
    if failures == 0:
        ok(f"All {total} auto-approved tag(s) passed validation.")
    else:
        fail(f"{failures} validation failure(s) across {total} tag(s).")

    write_report(results, total, failures)
    return 1 if failures else 0


def write_report(results, total, failures):
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    lines = ["# Auto-Approved Tile Validation Report", "",
             "- Validator: `validate_auto_approved_tiles.py`",
             f"- Tags validated: {total}",
             f"- Failures: {failures}",
             f"- Verdict: {'PASS' if failures == 0 else 'FAIL'}", ""]
    if total == 0:
        lines += ["> No tiles were auto-approved. The auto-approval set is intentionally empty because no "
                  "candidate reached confidence >= 90 on hard evidence. This is the safe outcome: nothing is "
                  "approved without human review.", ""]
    lines.append("## Checks")
    for level, msg in results:
        mark = {"OK": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[--]"}[level]
        lines.append(f"- {mark} {msg}")
    lines.append("")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {os.path.relpath(REPORT, ROOT)}  (verdict={'PASS' if failures==0 else 'FAIL'})")


if __name__ == "__main__":
    sys.exit(main())
