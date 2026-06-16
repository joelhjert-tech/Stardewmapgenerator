#!/usr/bin/env python3
"""
build_auto_resolution.py

Mission: REVIEW + EVIDENCE GATHERING + SAFE AUTO-RESOLUTION (no human visual approval).

Reads the tile intelligence database and classification artifacts, searches for
*hard* evidence (TSX metadata, DeepWoods/HedgeMaze code, exact-duplicate-of-approved,
map usage), scores confidence, and emits review artifacts WITHOUT modifying any
protected file (skeleton DB, human-approved DB, approved_tags/, mission_assets, mod files).

Confidence rubric (0-100):
  100 - explicit TSX/Wang/terrain metadata gives class + layer/collision
   95 - exact tile id in NAMED DeepWoods/HedgeMaze code, clear purpose, allowed tilesheet
   90 - exact duplicate of an already-approved tile, matching layer usage
   85 - repeated stable layer role + neighbor pattern (PROPOSED ONLY)
   75 - strong usage but collision/purpose partly uncertain
  <75 - manual review required

Auto-approval threshold: >= 90 (placed in auto_approved_tile_tags.json).
85: proposed only.  <85: manual_required.

This script is read-only with respect to inputs; it only writes into review/ and
review/auto_resolution/ and review/manual_required/.
"""
import ijson, json, os, collections
from decimal import Decimal

def _dec(o):
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(f"not serializable: {type(o).__name__}")

ROOT = os.path.dirname(os.path.abspath(__file__))
def p(*a): return os.path.join(ROOT, *a)

CANON = p("classification", "canonical_tile_candidates.json")
TILESET_CAT = p("database", "tileset_catalog.json")
STYLEPACK = p("stylepacks", "moonvillage_forest_ruins.json")
GENERATED_AT = "2026-06-14T00:00:00Z"  # static; runtime clock intentionally not used

# ----------------------------------------------------------------------------
# 1. DeepWoods code evidence map (parsed from DeepWoodsTileDefinitions.cs +
#    DeepWoods.cs tilesheet binding).
#
#    Tilesheet binding (DeepWoods.cs:622-624):
#      DefaultOutdoor  -> "<season>_outdoorsTileSheet"  Size(25,79)   == ALLOWED (vanilla)
#      InfestedOutdoor -> "deepWoodsInfestedOutdoorsTileSheet"        == RESTRICTED custom
#      WaterBorder     -> "deepWoodsLakeTilesheet"      Size(8,5)     == RESTRICTED custom
#
#    Only ids that index the vanilla 25-wide outdoors sheet can possibly map to a
#    Moonvillage candidate (the seasonal outdoors sheets are 25x79 = identical layout).
# ----------------------------------------------------------------------------
DW_GRASS_NORMAL   = {351, 300, 304, 305, 329}                       # GrassTiles.NORMAL  -> ground_base, Back, walkable
DW_GRASS_DARK     = {380, 156}                                      # GrassTiles.DARK    -> grass_detail, Back, walkable
DW_GRASS_BRIGHT   = {175, 275, 402, 400, 401, 150, 254, 255, 256}  # GrassTiles.BRIGHT  -> grass_detail, Back, walkable
DW_GRASS_BLACK    = {1094}                                          # GrassTiles.BLACK
DW_FOREST_WALL    = {946, 971, 996}                                 # FOREST_BACKGROUND  -> Buildings body in DW (CONFLICTS w/ MV usage)
# Forest tree-wall row/corner matrices (directional edges/corners/canopy)
DW_FOREST_MATRIX  = {940,941,942,943,944,945,965,966,967,968,969,970,990,991,992,993,994,995,
                     1015,1016,1017,1018,1019,1040,1041,1042,1043,1044,1045,1065,1066,1068,1069,1070,
                     1092,1093,1095,1096,1119,1120,1121}
# Bright/dark grass transition matrix (directional terrain transitions)
DW_GRASS_TRANS    = {326,350,352,376,403,375,377,378,353,325,327,328,302,277,286,306,261,276,278,281,
                     301,303,311,331,355,356,357,379,381,382,404,405,406,407,332,354}
DW_WATER_LILY     = {1293,1294,1295,1296,1318,1319,1320,1321,1299}  # outdoor sheet, animated water deco (out of scope)
DW_DEBUG          = {68, 115, 226, 292}                             # DeepWoods-INTERNAL debug picks (NOT authoritative)
DW_TREESTUMP      = {1144, 1145}
# Restricted (custom DeepWoods lake/infested sheets) - listed for the risk report only.
DW_WATER_RESTRICTED = {1246,1271,1274,1247,1248,1249,1272,1273,1324,1322,1323}

DW_CATEGORY = {}
def _tag(ids, cat):
    for i in ids: DW_CATEGORY.setdefault(i, []).append(cat)
_tag(DW_GRASS_NORMAL, "grass_normal")
_tag(DW_GRASS_DARK, "grass_dark")
_tag(DW_GRASS_BRIGHT, "grass_bright")
_tag(DW_GRASS_BLACK, "grass_black")
_tag(DW_FOREST_WALL, "forest_wall")
_tag(DW_FOREST_MATRIX, "forest_matrix")
_tag(DW_GRASS_TRANS, "grass_transition")
_tag(DW_WATER_LILY, "water_lily")
_tag(DW_DEBUG, "debug")
_tag(DW_TREESTUMP, "treestump")

# Grass ground/detail ids are the only ones whose DeepWoods role is a single,
# non-directional, walkable-Back semantic that can be CORROBORATED by map usage.
DW_GRASS_CLEAN = DW_GRASS_NORMAL | DW_GRASS_DARK | DW_GRASS_BRIGHT  # excludes black (rare) + multi-cat
DW_OUTDOORS_NAMED = set(DW_CATEGORY.keys())

DW_SRC = "tools/DeepWoodsMod-main/src/DeepWoods/Data/DeepWoodsTileDefinitions.cs"
DW_SHEET_SRC = "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs:622"

# ----------------------------------------------------------------------------
# 2. Active style-pack referenced tiles (generator priority).
# ----------------------------------------------------------------------------
with open(STYLEPACK, encoding="utf-8-sig") as f:
    sp = json.load(f)
SP_SHEET = sp["tilesheet"]["name"]  # spring_outdoorsTileSheet
sp_ids = set()
sp_id_group = {}
for grp, items in sp.get("groups", {}).items():
    for it in items:
        lid = it.get("localTileId")
        if lid is not None:
            sp_ids.add(lid)
            sp_id_group.setdefault(lid, []).append(grp)

# ----------------------------------------------------------------------------
# 3. Helpers
# ----------------------------------------------------------------------------
def is_outdoors25(name):
    n = (name or "").lower()
    return n.endswith("outdoorstilesheet.png") or (".outdoorstilesheet." in n and n.endswith(".png"))

def dom_layer(layers):
    if not layers: return (None, 0.0)
    tot = sum(layers.values()) or 1
    k = max(layers, key=layers.get)
    return (k, layers[k] / tot)

# ----------------------------------------------------------------------------
# 4. Single streaming pass over canonical candidates.
# ----------------------------------------------------------------------------
total = 0
by_cat = collections.Counter()
n_props = n_terr = n_wang = 0
maxconf = 0.0
priority = []   # full records for evidence-relevant / generator-priority candidates

for c in ijson.items(open(CANON, "rb"), "item"):
    total += 1
    by_cat[c.get("sourceCategory")] += 1
    if c.get("existingProperties"): n_props += 1
    if c.get("existingTerrainData"): n_terr += 1
    if c.get("existingWangData"): n_wang += 1
    cf = c.get("confidenceFromUsage") or 0
    if cf > maxconf: maxconf = cf

    nm = c.get("tilesheetName", "")
    lid = c.get("localTileId")
    out25 = is_outdoors25(nm)
    is_dw = out25 and lid in DW_OUTDOORS_NAMED
    is_sp = (nm.lower().startswith(SP_SHEET.lower())) and (lid in sp_ids)
    if not (is_dw or is_sp):
        continue
    smu = c.get("sourceMapsUsedBy") or []
    rec = {
        "candidateId": c.get("candidateId"),
        "tilesheetName": nm,
        "copiedImagePath": c.get("copiedImagePath"),
        "sourceCategory": c.get("sourceCategory"),
        "sourceMod": c.get("sourceMod"),
        "localTileId": lid,
        "tileX": c.get("tileX"),
        "tileY": c.get("tileY"),
        "observedLayers": c.get("observedLayers") or {},
        "observedCountTotal": c.get("observedCountTotal", 0),
        "sourceMapsUsedByCount": len(smu),
        "sourceMapsUsedBySample": smu[:15],
        "currentEvidenceLabels": c.get("evidenceLabels") or {},
        "currentConfidence": cf,
        "deepwoodsCategories": DW_CATEGORY.get(lid, []) if is_dw else [],
        "stylePackGroups": sp_id_group.get(lid, []) if is_sp else [],
    }
    priority.append(rec)

full_stats = {
    "totalCandidates": total,
    "allApprovedFalse": True,
    "allNeedsHumanReviewTrue": True,
    "allFinalClassNull": True,
    "bySourceCategory": dict(by_cat),
    "candidatesWithExistingTSXProperties": n_props,
    "candidatesWithExistingTerrainData": n_terr,
    "candidatesWithExistingWangData": n_wang,
    "maxConfidenceFromUsage": maxconf,
    "priorityCandidatesEnumerated": len(priority),
}

# ----------------------------------------------------------------------------
# 5. Evidence index + tier assignment.
# ----------------------------------------------------------------------------
evidence_index = []
auto_approved = []        # confidence >= 90
medium_proposed = []      # 75-89
manual_priority = []      # priority candidates that stay manual

GRASS_BACK_FRAC_MIN = 0.85
GRASS_COUNT_MIN = 50

for rec in priority:
    lid = rec["localTileId"]
    cats = rec["deepwoodsCategories"]
    dl, df = dom_layer(rec["observedLayers"])
    cid = rec["candidateId"]

    # --- DeepWoods grass corroboration (two independent sources) ---
    if lid in DW_GRASS_CLEAN and dl == "Back" and df >= GRASS_BACK_FRAC_MIN and rec["observedCountTotal"] >= GRASS_COUNT_MIN:
        proposed_class = "ground_base" if lid in DW_GRASS_NORMAL else "grass_detail"
        ev = {
            "candidateId": cid,
            "evidenceType": "deepwoods_code+map_usage_corroboration",
            "evidenceSourceFile": DW_SRC,
            "evidenceSourceLine": None,
            "evidenceSummary": (
                f"localTileId {lid} on vanilla outdoors sheet is named in DeepWoods GrassTiles "
                f"({'/'.join(cats)}); Moonvillage maps independently use it dominantly on Back "
                f"({df:.0%} of {rec['observedCountTotal']} placements). Two independent sources agree on a "
                f"walkable Back ground/grass role."
            ),
            "proposedClass": proposed_class,
            "proposedPurpose": "outdoor walkable grass/ground (seasonal outdoors vanilla tile)",
            "proposedAllowedLayers": ["Back"],
            "proposedCollision": "walkable",
            "proposedTerrainData": None,
            "confidence": 85,
            "reason": (
                "DeepWoods variable name corroborated by stable single-layer map usage, BUT the DeepWoods "
                "name reflects DeepWoods-internal use (not authoritative metadata) and no TSX class/collision "
                "metadata exists. Capped at 85 (proposed only) per rubric."
            ),
        }
        evidence_index.append(ev)
        medium_proposed.append({
            "candidateId": cid,
            "localTileId": lid,
            "tilesheetName": rec["tilesheetName"],
            "sourceCategory": rec["sourceCategory"],
            "sourceMod": rec["sourceMod"],
            "proposedClass": proposed_class,
            "proposedPurpose": ev["proposedPurpose"],
            "allowedLayers": ["Back"],
            "collision": "walkable",
            "confidence": 85,
            "approved": False,
            "needsHumanReview": True,
            "source": "codex_evidence_proposal",
            "evidenceType": ev["evidenceType"],
            "evidenceSourceFile": DW_SRC,
            "reason": ev["reason"],
        })
        continue

    # --- everything else among priority: record evidence + why it's manual ---
    if lid in DW_FOREST_WALL or lid in DW_FOREST_MATRIX:
        reason = (
            f"DeepWoods places id {lid} as a forest Buildings-body/canopy tile, but Moonvillage uses it "
            f"dominantly on '{dl}' ({df:.0%}). Layer/role CONFLICT between code intent and observed usage; "
            f"collision unknown. Disqualified from auto-approval."
        )
        etype = "deepwoods_code_layer_conflict"
    elif lid in DW_GRASS_TRANS:
        reason = (
            f"DeepWoods id {lid} is a directional grass/terrain TRANSITION (edge/corner). Direction-specific "
            f"role cannot be assigned from a single tile id without neighbor-resolved terrain context; "
            f"requires visual terrain matching. Manual."
        )
        etype = "deepwoods_code_directional_transition"
    elif lid in DW_DEBUG:
        reason = (
            f"DeepWoods id {lid} is a DeepWoods-INTERNAL debug colour pick, not an intrinsic purpose "
            f"(e.g. id 226 is a normal heavily-used Back ground tile in Moonvillage). Non-authoritative. Manual."
        )
        etype = "deepwoods_code_non_authoritative_name"
    elif lid in DW_WATER_LILY:
        reason = (f"DeepWoods id {lid} is an animated water-lily tile; water generation is out of scope and "
                  f"animation/collision context is DeepWoods-specific. Manual.")
        etype = "deepwoods_code_out_of_scope"
    elif lid in DW_GRASS_CLEAN:
        reason = (f"DeepWoods names id {lid} as grass, but this candidate's observed usage is not a clean "
                  f"single Back role (dominant '{dl}' {df:.0%}); possible second role / layer conflict. Manual.")
        etype = "deepwoods_code+usage_inconsistent"
    else:
        reason = (f"Style-pack-referenced prototype tile (groups={rec['stylePackGroups']}) with only "
                  f"usage-evidence (max 0.80). Collision/purpose not established by hard evidence. Manual.")
        etype = "stylepack_prototype_usage_only"

    evidence_index.append({
        "candidateId": cid,
        "evidenceType": etype,
        "evidenceSourceFile": DW_SRC if cats else STYLEPACK.replace(ROOT + os.sep, "").replace("\\", "/"),
        "evidenceSourceLine": None,
        "evidenceSummary": (
            f"id {lid} cats={cats or rec['stylePackGroups']}; observed dominant layer '{dl}' ({df:.0%}) "
            f"over {rec['observedCountTotal']} placements in {rec['sourceMapsUsedByCount']} maps."
        ),
        "proposedClass": None,
        "proposedPurpose": None,
        "proposedAllowedLayers": [],
        "proposedCollision": "unknown",
        "proposedTerrainData": None,
        "confidence": min(int(round(rec["currentConfidence"] * 100)), 80),
        "reason": reason,
    })
    manual_priority.append({
        "candidateId": cid,
        "localTileId": lid,
        "tilesheetName": rec["tilesheetName"],
        "sourceCategory": rec["sourceCategory"],
        "sourceMod": rec["sourceMod"],
        "observedDominantLayer": dl,
        "observedDominantFraction": round(df, 3),
        "observedCountTotal": rec["observedCountTotal"],
        "deepwoodsCategories": cats,
        "stylePackGroups": rec["stylePackGroups"],
        "whyNotAutoApproved": reason,
        "missingEvidence": "No TSX class/terrain/wang metadata; no approved duplicate anchor; collision undetermined.",
        "evidenceType": etype,
        "confidence": min(int(round(rec["currentConfidence"] * 100)), 80),
    })

# ----------------------------------------------------------------------------
# 6. Write outputs (review/ only - never touch protected files).
# ----------------------------------------------------------------------------
def wj(relpath, obj):
    fp = p(*relpath)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=_dec)
    print(f"wrote {relpath[-1]}  ({os.path.getsize(fp):,} bytes)")

wj(["review", "missing_tile_candidates.json"], {
    "generatedAt": GENERATED_AT,
    "generatedBy": "build_auto_resolution.py",
    "methodologyNote": (
        "ALL 395,547 canonical candidates are technically 'missing/unknown' (approved:false, "
        "needsHumanReview:true, finalClass:null - no human approvals exist yet). The complete enumeration "
        "lives in classification/canonical_tile_candidates.json. This file enumerates the EVIDENCE-RELEVANT "
        "and GENERATOR-PRIORITY subset: candidates on the vanilla 25-wide seasonal outdoors sheets whose "
        "localTileId is named in DeepWoods code, plus candidates referenced by the active style pack."
    ),
    "fullPopulation": full_stats,
    "priorityCandidates": priority,
})

wj(["review", "auto_resolution", "tile_evidence_index.json"], {
    "generatedAt": GENERATED_AT,
    "evidenceSources": {
        "tsx_metadata": "ABSENT - 0/2149 tilesets have tile properties/terrain/wang/objectgroups",
        "deepwoods_code": DW_SRC + " (+ tilesheet binding " + DW_SHEET_SRC + ")",
        "hedgemaze_code": "UNAVAILABLE - no HedgeMaze source in project",
        "duplicate_of_approved": "UNAVAILABLE - 0 approved tiles exist",
        "map_usage": "database/layer_usage_index.json / canonical_tile_candidates.json (max confidence 0.80)",
    },
    "entries": evidence_index,
})

wj(["review", "auto_resolution", "auto_approved_tile_tags.json"], {
    "generatedAt": GENERATED_AT,
    "approvedBy": "codex_auto_evidence",
    "autoApprovalThreshold": 90,
    "count": len(auto_approved),
    "rationaleIfEmpty": (
        "No candidate reached confidence >= 90. The three >=90 evidence paths are all unavailable: "
        "(100) explicit TSX/Wang/terrain metadata - 0 tilesets have any; "
        "(95) named DeepWoods/HedgeMaze code with allowed sheet + clear purpose - DeepWoods names are "
        "non-authoritative and conflict with observed Moonvillage layer usage (e.g. id 946), HedgeMaze "
        "source absent; (90) exact duplicate of an approved tile - 0 approved tiles exist to anchor against. "
        "Usage evidence is capped at 85 by the rubric and cannot auto-approve."
    ),
    "tags": auto_approved,
})

wj(["review", "auto_resolution", "medium_confidence_proposed_tags.json"], {
    "generatedAt": GENERATED_AT,
    "confidenceBand": "75-89 (proposed only, NOT approved)",
    "source": "codex_evidence_proposal",
    "count": len(medium_proposed),
    "note": (
        "These are vanilla seasonal-outdoors GRASS/GROUND tiles where the DeepWoods code role and the "
        "observed Moonvillage map usage independently agree on a walkable Back ground role. They still "
        "require human confirmation (no authoritative collision/property metadata exists)."
    ),
    "tags": medium_proposed,
})

# Manual required: full population summary + detailed priority manual list.
wj(["review", "manual_required", "manual_required_tiles.json"], {
    "generatedAt": GENERATED_AT,
    "fullPopulationSummary": {
        "totalUnresolvedCandidates": total,
        "autoApproved": len(auto_approved),
        "mediumConfidenceProposed": len(medium_proposed),
        "remainingManualRequired": total - len(auto_approved) - len(medium_proposed),
        "note": (
            "The complete manual-required population is every candidate in "
            "classification/canonical_tile_candidates.json that is not in medium_confidence_proposed_tags.json "
            "(auto_approved is empty). They cannot be resolved by hard evidence because: no TSX metadata "
            "exists, no approved tiles exist to duplicate-match, and usage evidence caps at 0.80 (<0.85)."
        ),
    },
    "priorityManualTiles": manual_priority,
})

# ----------------------------------------------------------------------------
# 7. Merge preview (DELTA-based - does NOT duplicate the 1GB human-approved DB).
#    Shows exactly how the human-approved DB WOULD change if the auto-approved
#    tags were accepted. With 0 auto-approved tags the delta is empty (no change).
# ----------------------------------------------------------------------------
wj(["review", "auto_resolution", "tile_database_auto_approval_preview.json"], {
    "generatedAt": GENERATED_AT,
    "baseDatabase": "database/tile_database_v1_human_approved.json",
    "previewType": "delta",
    "mergeSemantics": (
        "For each auto-approved tag, the matching DB entry (same candidateId / tilesheet+localTileId) "
        "would have finalClass<-approvedClass, finalPurpose<-approvedPurpose, allowedLayers, collision set, "
        "approved<-true, needsHumanReview<-false. Non-matching entries are unchanged."
    ),
    "autoApprovedTagCount": len(auto_approved),
    "entriesThatWouldChange": [],
    "resultingDatabaseEqualsBase": len(auto_approved) == 0,
    "note": (
        "0 auto-approved tags => the resulting tile_database_v1_human_approved.json would be byte-identical "
        "to the current file. No 1GB copy is produced; this delta documents the (empty) change set. "
        "When real auto-approved tags exist, 'entriesThatWouldChange' will list each merged entry."
    ),
})

print()
print("=== TIER SUMMARY ===")
print("priority candidates enumerated:", len(priority))
print("auto_approved (>=90):", len(auto_approved))
print("medium_confidence_proposed (85):", len(medium_proposed))
print("priority manual_required:", len(manual_priority))
print("full population total:", total)
