#!/usr/bin/env python3
"""
build_vanilla_index.py

Parses every unpacked base-game .tbin map and builds an AUTHORITATIVE per-tile index:
  for each (vanilla tilesheet basename, tileIndex):
    - @TileIndex@ properties seen (name -> set of values) across all maps  [intrinsic metadata]
    - layers the tile is placed on (layer -> count)                        [authoritative usage]
    - number of distinct maps using it

Vanilla maps are the canonical game source, so this is authoritative (unlike mod usage).
Read-only; writes review/auto_resolution/vanilla_authoritative_index.json.
"""
import glob, os, json, collections, re
import tbin_reader as T

ROOT = os.path.dirname(os.path.abspath(__file__))
BG = os.path.join(ROOT, "mission_assets", "unpacked_basegame")
OUT = os.path.join(ROOT, "review", "auto_resolution", "vanilla_authoritative_index.json")

def base_key(name):
    if not name:
        return None
    n = name.replace("\\", "/").split("/")[-1].lower()
    if n.endswith(".png"):
        n = n[:-4]
    return n

TIPROP = re.compile(r"^@TileIndex@(\d+)@(.+)$")

# index[sheetbase][idx] = {"props": {propname: set(values)}, "layers": Counter, "maps": set}
index = collections.defaultdict(lambda: collections.defaultdict(
    lambda: {"props": collections.defaultdict(set), "layers": collections.Counter(), "maps": set()}))

files = sorted(glob.glob(os.path.join(BG, "*.tbin")))
ok = bad = 0
bad_files = []
sheet_props_count = 0
for fp in files:
    name = os.path.basename(fp)
    try:
        mp = T.parse(open(fp, "rb").read())
    except Exception as e:
        bad += 1; bad_files.append((name, str(e))); continue
    if not mp["ok"]:
        bad += 1; bad_files.append((name, f"not fully consumed ({mp['trailingBytes']} trailing)")); continue
    ok += 1
    # tilesheet id -> basename, and capture @TileIndex props
    id2base = {}
    for ts in mp["tilesheets"]:
        b = base_key(ts["imageSource"])
        id2base[ts["id"]] = b
        for k, v in ts["properties"].items():
            m = TIPROP.match(k)
            if m:
                idx = int(m.group(1)); prop = m.group(2)
                index[b][idx]["props"][prop].add(v if isinstance(v, str) else str(v))
                sheet_props_count += 1
    # placed tiles -> authoritative layer usage
    for ly in mp["layers"]:
        lid = ly["id"]
        for (x, y), (sheetId, idx) in ly["tiles"].items():
            b = id2base.get(sheetId)
            if b is None:
                continue
            cell = index[b][idx]
            cell["layers"][lid] += 1
            cell["maps"].add(name)

# serialise
out = {"generatedBy": "build_vanilla_index.py",
       "mapsParsed": ok, "mapsFailed": bad, "badFiles": bad_files[:20],
       "tileIndexPropertyEntries": sheet_props_count,
       "sheets": {}}
for b, idxmap in index.items():
    sheet = {}
    for idx, cell in idxmap.items():
        sheet[str(idx)] = {
            "props": {p: sorted(vs) for p, vs in cell["props"].items()},
            "layers": dict(cell["layers"]),
            "mapCount": len(cell["maps"]),
        }
    out["sheets"][b] = sheet

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)

# stats
print(f"maps parsed OK: {ok} | failed: {bad}")
if bad_files:
    for n, e in bad_files[:10]:
        print("   BAD:", n, "-", e)
print(f"distinct vanilla sheets indexed: {len(out['sheets'])}")
total_idx = sum(len(s) for s in out["sheets"].values())
with_props = sum(1 for s in out["sheets"].values() for v in s.values() if v["props"])
print(f"distinct (sheet,tileIndex) entries: {total_idx}")
print(f"  ... with @TileIndex@ properties: {with_props}")
propnames = collections.Counter()
for s in out["sheets"].values():
    for v in s.values():
        for p in v["props"]:
            propnames[p] += 1
print("top @TileIndex property names:", propnames.most_common(20))
print("wrote", os.path.relpath(OUT, ROOT), f"({os.path.getsize(OUT):,} bytes)")
