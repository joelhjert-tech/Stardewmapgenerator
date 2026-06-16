import json
from datetime import datetime, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
CLASS_ROOT = TOOL_ROOT / "classification"
REVIEW_UI_ROOT = TOOL_ROOT / "review-ui"
DATA_ROOT = REVIEW_UI_ROOT / "data"
PREVIEW_ROOT = TOOL_ROOT / "previews" / "review_packs"


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel_from_review_ui(path):
    return Path("..", path.relative_to(TOOL_ROOT)).as_posix()


def rel_from_review_ui_if_possible(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    try:
        return rel_from_review_ui(path)
    except ValueError:
        return None


def session_status(review_pack_id):
    session_path = CLASS_ROOT / "review_sessions" / f"{review_pack_id}.session.json"
    data = load_json(session_path)
    if not data:
        return "not_started", None
    if data.get("completedAt"):
        return "completed", rel_from_review_ui(session_path)
    return "in_progress", rel_from_review_ui(session_path)


def main():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    queue = load_json(CLASS_ROOT / "tile_review_queue.json", [])
    schema_path = CLASS_ROOT / "tile_class_schema.json"
    schema = load_json(schema_path, {})

    approved_paths = {p.name.replace(".approved_tags.json", ""): p for p in (CLASS_ROOT / "approved_tags").glob("*.approved_tags.json")}
    rejected_paths = {p.name.replace(".rejected_tags.json", ""): p for p in (CLASS_ROOT / "rejected_tags").glob("*.rejected_tags.json")}
    proposed_paths = {}
    for p in (CLASS_ROOT / "proposed_tags").glob("*.json"):
        key = p.name
        if key.endswith("_proposed_tags.json"):
            key = key[: -len("_proposed_tags.json")]
        proposed_paths[key] = p

    packs = []
    for item in queue:
        review_pack_id = item["reviewPackId"]
        pack_path = CLASS_ROOT / "review_packs" / f"{review_pack_id}.json"
        preview_path = PREVIEW_ROOT / f"{review_pack_id}.png"
        status, session_rel = session_status(review_pack_id)
        clean_preview_path = rel_from_review_ui_if_possible(item.get("copiedImagePath"))
        labeled_preview_path = rel_from_review_ui(preview_path)
        packs.append(
            {
                **item,
                "reviewStatus": status,
                "packPath": rel_from_review_ui(pack_path),
                "previewPath": rel_from_review_ui(preview_path),
                "cleanPreviewPath": clean_preview_path,
                "labeledPreviewPath": labeled_preview_path,
                "proposedTagsPath": rel_from_review_ui(proposed_paths[review_pack_id]) if review_pack_id in proposed_paths else None,
                "approvedTagsPath": rel_from_review_ui(approved_paths[review_pack_id]) if review_pack_id in approved_paths else None,
                "rejectedTagsPath": rel_from_review_ui(rejected_paths[review_pack_id]) if review_pack_id in rejected_paths else None,
                "sessionPath": session_rel,
                "hasPreview": preview_path.exists(),
                "hasProposedTags": review_pack_id in proposed_paths,
                "hasApprovedTags": review_pack_id in approved_paths,
                "hasRejectedTags": review_pack_id in rejected_paths,
            }
        )

    review_index = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "schemaPath": rel_from_review_ui(schema_path),
        "manualTemplatePath": rel_from_review_ui(CLASS_ROOT / "manual_tile_tags_template.json"),
        "exportInstructions": {
            "approvedTags": "../classification/approved_tags/[reviewPackId].approved_tags.json",
            "rejectedTags": "../classification/rejected_tags/[reviewPackId].rejected_tags.json",
            "reviewSessions": "../classification/review_sessions/[reviewPackId].session.json",
            "browserDownloads": "If the browser cannot write directly, save exported JSON into review-ui/exports and move/copy it into the matching classification folder.",
        },
        "classNames": sorted(schema.keys()),
        "collisionValues": ["unknown", "walkable", "blocked", "front_only", "decorative", "water", "custom"],
        "transitionTypes": ["none", "edge", "inner_corner", "outer_corner", "mixed", "center", "cap", "end", "junction"],
        "commonLayers": ["Back", "Buildings", "Front", "AlwaysFront", "Paths", "Map", "Objects"],
        "packs": packs,
    }
    (DATA_ROOT / "review_index.json").write_text(json.dumps(review_index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {DATA_ROOT / 'review_index.json'} with {len(packs)} review packs.")


if __name__ == "__main__":
    main()
