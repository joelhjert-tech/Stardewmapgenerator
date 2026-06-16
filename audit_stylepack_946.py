import json
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
STYLEPACK_ROOT = TOOL_ROOT / "stylepacks"
REPORT_PATH = TOOL_ROOT / "reports" / "stylepack_946_fix_report.md"
PATCH_PATH = TOOL_ROOT / "review" / "basegame_merge" / "stylepack_suggested_patch_946.json"


RISK_ROLE_MARKERS = {"wallbody", "wall_body", "body", "blocker", "collision", "wallbase", "wall_base", "hedgebody", "hedge_body"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def layer_for_group(group_name, stylepack):
    rules = stylepack.get("layerRules") or {}
    name = group_name.lower()
    if "body" in name or "blocker" in name or "collision" in name:
        return rules.get("blockingBody", "Buildings")
    if "top" in name or "canopy" in name or "overlay" in name or "edge" in name or "corner" in name:
        return rules.get("tallOverlay") or rules.get("topEdge", "AlwaysFront")
    if "ground" in name or "path" in name:
        return rules.get("ground", "Back")
    return "unknown"


def scan_stylepack(path):
    stylepack = load_json(path)
    uses = []
    for section in ("groups", "semanticGroups"):
        groups = stylepack.get(section) or {}
        for group_name, values in groups.items():
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                local_id = None
                gid = None
                if isinstance(value, dict):
                    local_id = value.get("localTileId")
                    gid = value.get("gid")
                elif isinstance(value, int):
                    gid = value
                if local_id == 946 or gid in {946, 947}:
                    role_blob = group_name.lower()
                    layer = layer_for_group(group_name, stylepack)
                    risky = layer == "Buildings" or any(marker in role_blob for marker in RISK_ROLE_MARKERS)
                    uses.append(
                        {
                            "stylepackFile": path.name,
                            "stylePackId": stylepack.get("stylePackId") or path.stem,
                            "jsonPath": f"/{section}/{group_name}/{index}",
                            "section": section,
                            "group": group_name,
                            "index": index,
                            "tileId": local_id,
                            "gid": gid,
                            "currentLayer": layer,
                            "currentValue": value,
                            "risk": "tile_946_assigned_to_blocking_body_role" if risky else "tile_946_requires_overlay_profile_review",
                            "risky": risky,
                        }
                    )
    return uses


def main():
    all_uses = []
    for path in sorted(STYLEPACK_ROOT.glob("*.json")):
        all_uses.extend(scan_stylepack(path))

    suggested_patches = []
    for use in all_uses:
        if use["risky"]:
            suggested_patches.append(
                {
                    "stylepackFile": use["stylepackFile"],
                    "operation": "remove_or_replace",
                    "jsonPath": use["jsonPath"],
                    "tileId": use["tileId"],
                    "gid": use["gid"],
                    "currentRole": use["group"],
                    "currentLayer": use["currentLayer"],
                    "suggestedAction": "replace_with_marker",
                    "replacementPolicy": "Use a temporary marker tile or a future human-approved wall/hedge body tile. Do not use tile 946 as Buildings/blocking.",
                    "reason": "Vanilla and Moonvillage usage show tile 946 is dominantly AlwaysFront/canopy-like and has no intrinsic blocking property.",
                }
            )
        else:
            suggested_patches.append(
                {
                    "stylepackFile": use["stylepackFile"],
                    "operation": "review_only",
                    "jsonPath": use["jsonPath"],
                    "tileId": use["tileId"],
                    "gid": use["gid"],
                    "currentRole": use["group"],
                    "currentLayer": use["currentLayer"],
                    "suggestedAction": "create_separate_usage_profile",
                    "replacementPolicy": "Only keep if Joel later approves an AlwaysFront/canopy overlay profile.",
                    "reason": "Tile 946 is profile-specific, not globally banned.",
                }
            )

    PATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    PATCH_PATH.write_text(
        json.dumps(
            {
                "generatedAt": now_iso(),
                "appliesAutomatically": False,
                "tile946Policy": "Do not approve or use tile 946 as Buildings/wallBody/blocker. Keep as prototype-only unless a separate overlay profile is approved.",
                "usesFound": all_uses,
                "suggestedPatches": suggested_patches,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Stylepack 946 Fix Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Stylepacks scanned: {len(list(STYLEPACK_ROOT.glob('*.json')))}",
        f"- Tile 946 uses found: {len(all_uses)}",
        f"- Risky blocking/body uses: {sum(1 for use in all_uses if use['risky'])}",
        "",
        "## Policy",
        "",
        "- Tile 946 is not globally banned.",
        "- Tile 946 must not be used as `wallBody`, `Buildings`, blocker, collision, wall base, or hedge body.",
        "- It may only move toward canopy/front/AlwaysFront overlay use after a separate approved usage profile exists.",
        "- Until then, replace wall/body uses with a marker tile or a future approved wall body tile.",
        "",
        "## Uses Found",
    ]
    if not all_uses:
        lines.append("- None.")
    for use in all_uses:
        lines.append(
            f"- `{use['stylepackFile']}` `{use['jsonPath']}` role `{use['group']}` layer `{use['currentLayer']}`: {use['risk']}"
        )
    lines.extend(
        [
            "",
            "## Suggested Patch",
            "",
            f"- JSON patch proposal: `{PATCH_PATH}`",
            "- Not applied automatically.",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"tile 946 uses found: {len(all_uses)}; risky: {sum(1 for use in all_uses if use['risky'])}")


if __name__ == "__main__":
    main()
