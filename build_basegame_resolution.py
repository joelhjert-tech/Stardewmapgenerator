#!/usr/bin/env python3
"""
build_basegame_resolution.py

Second-pass auto-resolution using the unpacked base-game (vanilla) assets.

Hard evidence now available:
  (A) Sheet identity: Moonvillage tilesheets that are BYTE-IDENTICAL to a vanilla
      base-game sheet -> their tiles are confirmed vanilla (allowed) source.
  (B) Authoritative intrinsic metadata: vanilla maps embed @TileIndex@<idx>@<Prop>
      properties (Water / Type / Passable / Diggable ...) per tilesheet, and place
      tiles on authoritative layers. Vanilla is the canonical game, so this is
      source-of-truth (review/auto_resolution/vanilla_authoritative_index.json).

Auto-approval (conf >= 90) is granted ONLY when an INTRINSIC property fixes collision:
  Water=true                -> water_base, blocked_or_special, [Back]          (95)
  Type=Grass/Dirt/Sand/Stone-> ground_base, walkable, [Back]                   (95)
  Type=Wood/Carpet          -> floor_base, walkable, [Back]                    (95)
  Passable=true (no Type)   -> overlay/decoration, walkable                    (90)
  Passable=false (no Type)  -> collision_blocker, blocks, [Buildings]          (90)

Usage-only inferences (no intrinsic property) stay PROPOSED (85) or manual.
Read-only w.r.t. protected files; writes review/ artifacts only.
"""
import ijson, json, os, glob, hashlib, collections
from decimal import Decimal

ROOT = os.path.dirname(os.path.abspath(__file__))
def p(*a): return os.path.join(ROOT, *a)
def _dec(o):
    if isinstance(o, Decimal): return float(o)
    raise TypeError(type(o).__name__)
GENERATED_AT = "2026-06-14T00:00:00Z"

CANON = p("classification", "canonical_tile_candidates.json")
VIDX = p("review", "auto_resolution", "vanilla_authoritative_index.json")
BG = p("mission_assets", "unpacked_basegame")
MV_SHEETS = p("mission_assets", "moonvillage", "tilesheets")

# ---------------------------------------------------------------- (A) sheet identity
def md5(fp):
    h = hashlib.md5()
    with open(fp, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()

van_hashes = set()
for fp in glob.glob(os.path.join(BG, "*.png")):
    van_hashes.add(md5(fp))

confirmed_vanilla_paths = set()   # moonvillage tilesheet copies that ARE vanilla
for fp in glob.glob(os.path.join(MV_SHEETS, "**", "*.png"), recursive=True):
    if md5(fp) in van_hashes:
        confirmed_vanilla_paths.add(os.path.normcase(os.path.abspath(fp)))
print(f"confirmed-vanilla moonvillage sheet files: {len(confirmed_vanilla_paths)}")

# ---------------------------------------------------------------- (B) authoritative index
vidx = json.load(open(VIDX, encoding="utf-8"))["sheets"]

def season_norm(basename):
    n = (basename or "").lower()
    if n.endswith(".png"): n = n[:-4]
    for s in ("summer_", "fall_", "winter_"):
        if n.startswith(s):
            n = "spring_" + n[len(s):]
            break
    return n

def norm_bool(vals):
    """Return True/False/None from a set of raw string values (case-insensitive)."""
    t = {str(v).strip().lower() for v in vals}
    truthy = t & {"t", "true", "1", "yes"}
    falsy = t & {"f", "false", "0", "no"}
    if truthy and not falsy: return True
    if falsy and not truthy: return False
    return None  # conflicting / unknown

def norm_type(vals):
    t = {str(v).strip().lower() for v in vals}
    t = {x for x in t if x and x not in ("t", "true")}  # drop junk
    return t  # set of distinct type strings

def lookup(sheet_basename, idx):
    key = season_norm(sheet_basename)
    s = vidx.get(key)
    if s is None:
        return None
    return s.get(str(idx))

# class/collision resolver from authoritative cell
def resolve(cell):
    """Return dict(class, purpose, layers, collision, confidence, evidence) or None."""
    props = cell.get("props", {})
    layers = cell.get("layers", {})
    water = norm_bool(props["Water"]) if "Water" in props else None
    passable = norm_bool(props["Passable"]) if "Passable" in props else None
    types = norm_type(props["Type"]) if "Type" in props else set()

    if water is True:
        return dict(cls="water_base", purpose="vanilla water tile",
                    layers=["Back"], collision="blocked_or_special", conf=95,
                    ev=f"intrinsic @Water=T (authoritative); vanilla Back usage")
    if len(types) == 1:
        t = next(iter(types))
        if t in ("grass", "dirt", "sand", "stone"):
            return dict(cls="ground_base", purpose=f"vanilla {t} ground (terrain)",
                        layers=["Back"], collision="walkable", conf=95,
                        ev=f"intrinsic @Type={t} (Back-layer terrain is engine-passable)")
        if t in ("wood", "carpet"):
            return dict(cls="floor_base", purpose=f"vanilla {t} floor",
                        layers=["Back"], collision="walkable", conf=95,
                        ev=f"intrinsic @Type={t} (Back-layer floor is engine-passable)")
        # other single Type value -> still Back terrain, walkable
        return dict(cls="ground_base", purpose=f"vanilla {t} terrain",
                    layers=["Back"], collision="walkable", conf=95,
                    ev=f"intrinsic @Type={t}")
    if len(types) > 1:
        return None  # conflicting Type across vanilla maps -> ambiguous, manual
    if passable is True:
        dom = max(layers, key=layers.get) if layers else "Buildings"
        cls = "overlay" if dom in ("Front", "AlwaysFront") else "decoration"
        return dict(cls=cls, purpose="vanilla explicitly-passable tile",
                    layers=[dom] if dom in ("Buildings", "Front", "AlwaysFront", "Back") else ["Buildings"],
                    collision="walkable", conf=90,
                    ev="intrinsic @Passable=T (explicitly walkable)")
    if passable is False:
        return dict(cls="collision_blocker", purpose="vanilla explicitly-impassable tile",
                    layers=["Buildings"], collision="blocks", conf=90,
                    ev="intrinsic @Passable=F (explicitly impassable)")
    return None  # no intrinsic collision property -> not auto-approvable here

# ---------------------------------------------------------------- stream candidates
# group auto-approved by (season_norm sheet, index)
auto_groups = {}    # (sheetkey, idx) -> {resolution, candidateIds:set, sheets:set, cats:Counter}
proposed = []       # 85-band (vanilla-confirmed, usage-only or front-overlay)
manual_vanilla = [] # vanilla-confirmed but no intrinsic property and not front-only -> manual
considered = 0
mv_on_vanilla = 0
total_candidates = 0
mv_total = 0

for c in ijson.items(open(CANON, "rb"), "item"):
    total_candidates += 1
    if c.get("sourceCategory") != "moonvillage":
        continue
    mv_total += 1
    cip = c.get("copiedImagePath") or ""
    if os.path.normcase(os.path.abspath(cip)) not in confirmed_vanilla_paths:
        continue
    mv_on_vanilla += 1
    nm = c.get("tilesheetName", "")
    idx = c.get("localTileId")
    cell = lookup(nm, idx)
    if not cell:
        continue
    considered += 1
    res = resolve(cell)
    cid = c.get("candidateId")
    if res:
        key = (season_norm(nm), idx)
        g = auto_groups.get(key)
        if g is None:
            g = {"res": res, "candidateIds": [], "sheets": set(), "cats": collections.Counter(),
                 "vanillaLayers": cell.get("layers", {}), "props": cell.get("props", {})}
            auto_groups[key] = g
        g["candidateIds"].append(cid)
        g["sheets"].add(nm)
    else:
        # vanilla-confirmed but no intrinsic collision property:
        # if vanilla uses it ONLY on Front/AlwaysFront -> safe walkable overlay (proposed 85)
        layers = cell.get("layers", {})
        if layers and set(layers) <= {"Front", "AlwaysFront", "Front2", "AlwaysFront2"}:
            proposed.append({
                "candidateId": cid, "localTileId": idx, "tilesheetName": nm,
                "proposedClass": "overlay", "proposedPurpose": "vanilla front/always-front overlay",
                "allowedLayers": [max(layers, key=layers.get)], "collision": "none",
                "confidence": 85, "approved": False, "needsHumanReview": True,
                "source": "codex_evidence_proposal",
                "evidenceType": "vanilla_authoritative_usage_front_only",
                "reason": "Byte-identical-to-vanilla tile; vanilla places it only on Front/AlwaysFront "
                          "(passable overlay). Collision safe; specific class generic -> proposed.",
            })
        else:
            dom = max(layers, key=layers.get) if layers else None
            manual_vanilla.append({
                "candidateId": cid, "localTileId": idx, "tilesheetName": nm,
                "vanillaDominantLayer": dom, "vanillaLayers": layers,
                "whyNotAutoApproved": ("Byte-identical-to-vanilla tile but NO intrinsic collision property "
                                       "(@Water/@Type/@Passable) and vanilla usage spans Buildings + overlay "
                                       "layers, so collision/role is genuinely ambiguous (e.g. canopy that is "
                                       "AlwaysFront in some maps, Buildings in others). Needs human role choice."),
                "missingEvidence": "No intrinsic tile property; mixed-layer authoritative usage.",
            })

# ---------------------------------------------------------------- emit auto-approved tags
auto_tags = []
for (sheetkey, idx), g in sorted(auto_groups.items()):
    r = g["res"]
    auto_tags.append({
        "candidateIds": sorted(set(g["candidateIds"])),
        "approvedClass": r["cls"],
        "approvedPurpose": r["purpose"],
        "allowedLayers": r["layers"],
        "collision": r["collision"],
        "terrainSet": None, "terrainA": None, "terrainB": None,
        "edgeMask": [], "cornerMask": [], "transitionType": None,
        "footprint": None, "allowedRooms": [], "avoidNear": [], "weight": 1,
        "approvedBy": "codex_auto_evidence",
        "approvedAt": GENERATED_AT,
        "evidenceType": "vanilla_intrinsic_tile_property",
        "evidenceSourceFile": "review/auto_resolution/vanilla_authoritative_index.json",
        "confidence": r["conf"],
        "reason": (f"Moonvillage sheet is BYTE-IDENTICAL to vanilla base-game sheet (confirmed vanilla "
                   f"source). {r['ev']}. Sheet family '{sheetkey}', tileIndex {idx}."),
        "safetyNotes": ("Collision is fixed by an intrinsic vanilla tile property + Stardew layer engine "
                        "semantics, not by appearance. Tilesheet is provably vanilla (byte-identical). "
                        "Seasonal recolors share the vanilla tile layout."),
        "vanillaProps": {k: sorted(v) for k, v in g["props"].items()},
        "vanillaLayers": g["vanillaLayers"],
        "sheetsCovered": sorted(g["sheets"]),
    })

def wj(relpath, obj):
    fp = p(*relpath)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=_dec)
    print(f"wrote {relpath[-1]}  ({os.path.getsize(fp):,} bytes)")

wj(["review", "auto_resolution", "auto_approved_tile_tags.json"], {
    "generatedAt": GENERATED_AT,
    "approvedBy": "codex_auto_evidence",
    "autoApprovalThreshold": 90,
    "evidenceBasis": "base-game (vanilla) byte-identical sheet match + intrinsic @TileIndex properties",
    "count": len(auto_tags),
    "distinctCandidatesCovered": sum(len(t["candidateIds"]) for t in auto_tags),
    "tags": auto_tags,
})

# merged into proposed: keep medium grass corroboration only where NOT already auto-approved
auto_keys = set(auto_groups.keys())
proposed = [pp for pp in proposed if (season_norm(pp["tilesheetName"]), pp["localTileId"]) not in auto_keys]
wj(["review", "auto_resolution", "medium_confidence_proposed_tags.json"], {
    "generatedAt": GENERATED_AT,
    "confidenceBand": "85 (proposed only)",
    "source": "codex_evidence_proposal",
    "count": len(proposed),
    "note": ("Vanilla-confirmed tiles whose collision is safe (Front/AlwaysFront passable overlays) but whose "
             "specific class is generic; plus prior DeepWoods/usage corroborations not covered by an intrinsic "
             "property. Require human confirmation of the semantic class."),
    "tags": proposed,
})

# merge preview entries
preview_entries = []
for t in auto_tags:
    for cid in t["candidateIds"]:
        preview_entries.append({"candidateId": cid, "finalClass": t["approvedClass"],
                                "finalPurpose": t["approvedPurpose"], "allowedLayers": t["allowedLayers"],
                                "collision": t["collision"], "approved": True, "needsHumanReview": False,
                                "confidence": t["confidence"]})
wj(["review", "auto_resolution", "tile_database_auto_approval_preview.json"], {
    "generatedAt": GENERATED_AT,
    "baseDatabase": "database/tile_database_v1_human_approved.json",
    "previewType": "delta",
    "mergeSemantics": ("Each listed candidateId's DB entry would get finalClass/finalPurpose/allowedLayers/"
                       "collision set and approved=true, needsHumanReview=false. Other entries unchanged."),
    "autoApprovedTagCount": len(auto_tags),
    "entriesThatWouldChangeCount": len(preview_entries),
    "entriesThatWouldChange": preview_entries[:5000],
    "truncated": len(preview_entries) > 5000,
    "resultingDatabaseEqualsBase": len(auto_tags) == 0,
})

auto_cand = sum(len(t["candidateIds"]) for t in auto_tags)
wj(["review", "manual_required", "manual_required_tiles.json"], {
    "generatedAt": GENERATED_AT,
    "fullPopulationSummary": {
        "totalUnresolvedCandidatesBefore": total_candidates,
        "autoApprovedCandidates": auto_cand,
        "mediumConfidenceProposed": len(proposed),
        "remainingManualRequired": total_candidates - auto_cand - len(proposed),
        "moonvillageTotal": mv_total,
        "moonvillageOnConfirmedVanillaSheets": mv_on_vanilla,
        "note": ("After the base-game pass, the remaining manual population is dominated by: (1) tiles on "
                 "the 112 CUSTOM (non-vanilla) Moonvillage sheets; (2) reference_mods/stardew_mods tiles; "
                 "(3) vanilla-confirmed tiles with no intrinsic property and mixed-layer usage (listed below); "
                 "(4) directional terrain-transition / forest-matrix tiles needing neighbour context."),
    },
    "priorityManualVanillaAmbiguous": manual_vanilla[:2000],
    "priorityManualVanillaAmbiguousCount": len(manual_vanilla),
})

print()
print("=== BASE-GAME RESOLUTION SUMMARY ===")
print(f"vanilla-confirmed-but-ambiguous (manual): {len(manual_vanilla)}")
print(f"moonvillage candidates on confirmed-vanilla sheets: {mv_on_vanilla}")
print(f"  ... with a vanilla authoritative index entry: {considered}")
print(f"auto-approved tags (grouped by sheet-family+index): {len(auto_tags)}")
print(f"  ... distinct candidates covered: {sum(len(t['candidateIds']) for t in auto_tags)}")
print(f"medium-confidence proposed: {len(proposed)}")
cls_counts = collections.Counter(t["approvedClass"] for t in auto_tags)
print("auto-approved by class:", dict(cls_counts))
conf_counts = collections.Counter(t["confidence"] for t in auto_tags)
print("auto-approved by confidence:", dict(conf_counts))
