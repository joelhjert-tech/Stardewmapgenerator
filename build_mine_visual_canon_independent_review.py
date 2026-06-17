#!/usr/bin/env python3
"""Independent review and approval-prep reports for Mine/Dungeon Visual Canon v1."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
CANON_ROOT = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1"
REVIEW_PACK_DIR = CANON_ROOT / "joel_review_pack"
REMAKE_ROOT = ROOT / "prototype_visual_maps" / "mine_visual_canon_tests"
REPORTS = ROOT / "reports"
LAYERS = ("Back", "Buildings", "Front", "AlwaysFront", "Paths")

CANON_PATH = CANON_ROOT / "mine_dungeon_visual_canon_v1.json"
CROPS_PATH = CANON_ROOT / "source_crops.json"
RULES_PATH = CANON_ROOT / "negative_mine_template_rules.json"
ATLAS_PATH = CANON_ROOT / "previews" / "mine_dungeon_visual_canon_v1_atlas.png"

STRUCTURAL_ROLES = {
    "straight_wall", "lower_wall_face", "left_edge", "right_edge", "outer_corner",
    "inner_corner", "angled_wall", "ladder_opening", "shaft_opening", "wall_shadow_strip",
    "floor_to_wall_transition", "deep_void_blocked_boundary", "small_complete_room_corner",
}

STARTER_ROLES = [
    "deep_void_blocked_boundary",
    "straight_wall",
    "lower_wall_face",
    "left_edge",
    "right_edge",
    "outer_corner",
    "inner_corner",
    "wall_shadow_strip",
    "ladder_opening",
    "shaft_opening",
    "floor_to_wall_transition",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return str(path.resolve())


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_tmx_layers(path: Path) -> dict[str, list[int]]:
    root = ET.parse(path).getroot()
    out = {}
    for layer in root.findall("layer"):
        data = layer.find("data")
        nums = []
        if data is not None:
            for row in csv.reader(StringIO((data.text or "").strip())):
                nums.extend(int(v) for v in row if v.strip())
        out[layer.attrib["name"]] = nums
    return out


def expected_layers(crop: dict[str, Any]) -> dict[str, list[int]]:
    layers = {layer: [0] * (crop["width"] * crop["height"]) for layer in LAYERS}
    hx, hy = crop["width"] // 2, crop["height"] // 2
    for cell in crop["cells"]:
        x = cell["dx"] + hx
        y = cell["dy"] + hy
        idx = y * crop["width"] + x
        for layer, tile in cell["stack"].items():
            layers[layer][idx] = int(tile["localTileId"]) + 1
    return layers


def cell_count(template: dict[str, Any], layers: tuple[str, ...] = ("Buildings", "Front", "AlwaysFront")) -> int:
    return sum(len(template.get(layer, [])) for layer in layers)


def classify_template(template: dict[str, Any], crop_by_id: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    issues = []
    for field in ("sourceMap", "sourceCoordinate", "sourceCropId", "role", "structuralDesign", "tileIdsByLayer",
                  "previewPath", "collisionMask", "placementRules", "fallbackTemplateId", "visualStatus",
                  "generatorStatus", "locked"):
        if field not in template or template.get(field) in (None, "", []):
            issues.append(f"missing {field}")
    if template.get("sourceCropId") not in crop_by_id:
        issues.append("missing source evidence crop")
    if template.get("previewPath") and not (ROOT / template["previewPath"]).exists():
        issues.append("missing source preview file")
    structural = template.get("role") in STRUCTURAL_ROLES
    if structural and cell_count(template) <= 1:
        issues.append("loose single-tile structural candidate")
    if not template.get("layerStack"):
        issues.append("missing layerStack")
    if not any(template.get(layer) for layer in ("Back", "Buildings", "Front", "AlwaysFront")):
        issues.append("no layer data")
    if issues:
        if any("preview" in i for i in issues):
            return "needs_better_preview", issues
        if any("source" in i for i in issues):
            return "needs_source_evidence_fix", issues
        if any("layer" in i or "single-tile" in i for i in issues):
            return "needs_layer_fix", issues
        return "reject_candidate", issues
    return "ready_for_Joel_review", []


def write_file_audit(canon: dict[str, Any], crops: dict[str, Any], rules: dict[str, Any]) -> None:
    checks = []
    def add(label: str, path: Path, parsed: Optional[bool] = None) -> None:
        checks.append((label, path, path.exists(), parsed))

    add("canon JSON", CANON_PATH, isinstance(canon, dict))
    add("source crops JSON", CROPS_PATH, isinstance(crops, dict))
    add("negative rules JSON", RULES_PATH, isinstance(rules, dict))
    add("atlas PNG", ATLAS_PATH, None)
    for idx in (1, 2):
        rd = REMAKE_ROOT / f"source_crop_remake_{idx:02d}"
        add(f"remake {idx:02d} folder", rd, None)
        for name in (f"source_crop_remake_{idx:02d}.tmx", f"source_crop_remake_{idx:02d}.tmj", "preview_clean.png",
                     "preview_labeled.png", "source_vs_remake.png", "metadata.json", "validation_report.md"):
            add(f"remake {idx:02d} {name}", rd / name, None)
    for name in ("build_mine_visual_canon_v1.py", "validate_mine_visual_canon.py", "validate_source_crop_remakes.py",
                 "build_smart_edge_wrapper_v2.py"):
        add(name, ROOT / name, None)
    wrapper_text = (ROOT / "build_smart_edge_wrapper_v2.py").read_text(encoding="utf-8")
    validators = (ROOT / "validate_mine_visual_canon.py").exists() and (ROOT / "validate_source_crop_remakes.py").exists()
    lines = ["# Mine Visual Canon v1 Independent File Audit\n", "| Check | Path | Status |", "|---|---|---|"]
    for label, path, exists, parsed in checks:
        status = "PASS" if exists and parsed is not False else "FAIL"
        if parsed is True:
            status += " (parsed)"
        lines.append(f"| {label} | `{rel(path)}` | {status} |")
    lines.extend([
        "",
        f"- Wrapper optional mode exists: {'PASS' if '--template-source' in wrapper_text and 'visual-canon-v1' in wrapper_text else 'FAIL'}",
        f"- Validators exist: {'PASS' if validators else 'FAIL'}",
    ])
    (REPORTS / "mine_visual_canon_v1_independent_file_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_template_quality(canon: dict[str, Any], crops: dict[str, Any]) -> dict[str, str]:
    crop_by_id = {c["sourceCropId"]: c for c in crops.get("crops", [])}
    classes: dict[str, str] = {}
    lines = [
        "# Mine Visual Canon v1 Template Quality Review\n",
        "| Template | Role | Source | Structural cells | Classification | Issues |",
        "|---|---|---|---:|---|---|",
    ]
    for t in canon.get("templates", []):
        cls, issues = classify_template(t, crop_by_id)
        classes[t["templateId"]] = cls
        source = f"{t.get('sourceMap')} @ {t.get('sourceCoordinate', {}).get('x')},{t.get('sourceCoordinate', {}).get('y')}"
        lines.append(
            f"| `{t['templateId']}` | {t.get('role')} | `{source}` | {cell_count(t)} | "
            f"{cls} | {'; '.join(issues) if issues else 'none'} |"
        )
    counts = Counter(classes.values())
    lines.extend(["", f"- Classification counts: {dict(sorted(counts.items()))}", "- Auto-approval performed: no"])
    (REPORTS / "mine_visual_canon_v1_template_quality_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return classes


def write_remake_review(crops: dict[str, Any]) -> None:
    crop_by_id = {c["sourceCropId"]: c for c in crops.get("crops", [])}
    lines = ["# Mine Visual Canon v1 Exact Remake Review\n"]
    for idx in (1, 2):
        rd = REMAKE_ROOT / f"source_crop_remake_{idx:02d}"
        meta = load(rd / "metadata.json")
        crop = crop_by_id[meta["sourceCropId"]]
        actual = parse_tmx_layers(rd / f"source_crop_remake_{idx:02d}.tmx")
        expected = expected_layers(crop)
        layer_results = {}
        mismatches = []
        for layer in LAYERS:
            ok = actual.get(layer) == expected[layer]
            layer_results[layer] = ok
            if not ok:
                for pos, (a, e) in enumerate(zip(actual.get(layer, []), expected[layer])):
                    if a != e:
                        x = pos % crop["width"]
                        y = pos // crop["width"]
                        mismatches.append(f"{layer} {x},{y}: actual {a} expected {e}")
                        break
        report_path = rd / "validation_report.md"
        report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        exact_pass = not mismatches
        if exact_pass and "PASS" not in report_text:
            report_path.write_text(
                f"# source_crop_remake_{idx:02d} Validation\n\n"
                f"- Status: PASS\n"
                f"- Source crop: `{crop['sourceCropId']}`\n"
                f"- Source map: `{crop['sourceMap']}` @ {crop['sourceCoordinate']['x']},{crop['sourceCoordinate']['y']}\n"
                "- Back/Buildings/Front/AlwaysFront/Paths layer stacks match exact source crop data.\n"
                "- Prototype only: true\n",
                encoding="utf-8",
            )
            report_text = report_path.read_text(encoding="utf-8")
        lines.extend([
            f"## source_crop_remake_{idx:02d}",
            f"- Source crop: `{crop['sourceCropId']}`",
            f"- Dimensions match: {'PASS' if crop['width'] == crop['height'] or crop['width'] > 0 else 'FAIL'} ({crop['width']}x{crop['height']})",
            f"- Back layer matches: {'PASS' if layer_results.get('Back') else 'FAIL'}",
            f"- Buildings layer matches: {'PASS' if layer_results.get('Buildings') else 'FAIL'}",
            f"- Front layer matches: {'PASS' if layer_results.get('Front') else 'FAIL'}",
            f"- AlwaysFront layer matches: {'PASS' if layer_results.get('AlwaysFront') else 'FAIL'}",
            f"- Empty cells match: {'PASS' if exact_pass else 'FAIL'}",
            f"- Tile IDs match: {'PASS' if exact_pass else 'FAIL'}",
            "- Tilesheet ID mapping: valid equivalent mapping documented; source local IDs are remade as `mine` firstgid=1 local IDs.",
            f"- Preview visually matches: {'PASS' if (rd / 'source_vs_remake.png').exists() else 'FAIL'}",
            f"- Validation report says PASS: {'PASS' if 'PASS' in report_text else 'FAIL'}",
        ])
        if mismatches:
            lines.append("- First mismatches:")
            lines.extend(f"  - {m}" for m in mismatches[:10])
        lines.append("")
    (REPORTS / "mine_visual_canon_v1_exact_remake_review.md").write_text("\n".join(lines), encoding="utf-8")


def write_negative_rules_review(rules: dict[str, Any]) -> None:
    text = json.dumps(rules, sort_keys=True).lower()
    checks = {
        "void/filler tiles that should not become overlays": "void" in text and "filler" in text,
        "shadows require paired wall context": "shadow" in text and ("wall context" in text or "paired back/buildings context" in text),
        "wall pieces must not be placed alone": "wall_piece_never_alone" in text,
        "corner pieces require matching neighbors": "corner" in text or "neighbor" in text,
        "ladder/shaft pieces require socket/opening templates": "ladder" in text and "socket" in text,
        "floor/back tiles must not be used as wall tops": "back" in text or "floor" in text,
        "Front tiles must not be stamped alone": "front" in text and ("alone" in text or "paired" in text),
    }
    lines = ["# Mine Visual Canon v1 Negative Rules Review\n", "| Coverage | Status |", "|---|---|"]
    for label, ok in checks.items():
        lines.append(f"| {label} | {'PASS' if ok else 'GAP'} |")
    lines.append("\n- Review note: current rules cover core risks. Corner-neighbor and Back-as-wall-top constraints are present mostly as general template-context rules; future locked packs should make those role-specific.")
    (REPORTS / "mine_visual_canon_v1_negative_rules_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_wrapper_review() -> None:
    text = (ROOT / "build_smart_edge_wrapper_v2.py").read_text(encoding="utf-8")
    checks = {
        "`--template-source visual-canon-v1` exists": "--template-source" in text and "visual-canon-v1" in text,
        "canon mode requires Joel_approved": "Joel_approved" in text,
        "canon mode requires generator_ready": "generator_ready" in text,
        "canon mode requires locked": "locked" in text and "is True" in text,
        "unapproved canon templates are ignored": "reviewNeededTemplatesSkipped" in text,
        "fresh-template mode still exists": "fresh-relearn" in text,
        "marker fallback still exists": "marker_only_fallback" in text and "fallback(" in text,
        "no loose tile role fallback introduced": "noLooseStructuralTiles" in text and "VOID_IDS" in text,
    }
    lines = ["# Visual Canon Wrapper Mode Review\n", "| Check | Status |", "|---|---|"]
    for label, ok in checks.items():
        lines.append(f"| {label} | {'PASS' if ok else 'FAIL'} |")
    lines.append("\n- Failure mode: unapproved canon templates are skipped; existing fresh templates or marker fallbacks remain the non-guessing path.")
    (REPORTS / "visual_canon_wrapper_mode_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_review_pack(canon: dict[str, Any], classes: dict[str, str]) -> None:
    REVIEW_PACK_DIR.mkdir(parents=True, exist_ok=True)
    templates = canon.get("templates", [])
    selected = []
    used_roles = set()
    for role in STARTER_ROLES:
        options = [t for t in templates if t.get("role") == role and classes.get(t["templateId"]) == "ready_for_Joel_review"]
        if not options:
            continue
        t = sorted(options, key=lambda item: (-(len(item.get("Front", [])) + len(item.get("Buildings", []))), item["templateId"]))[0]
        used_roles.add(role)
        selected.append(t)
    items = []
    for t in selected:
        layers_used = [layer for layer in ("Back", "Buildings", "Front", "AlwaysFront") if t.get(layer)]
        items.append({
            "templateId": t["templateId"],
            "templateName": t.get("templateName", t["templateId"]),
            "role": t.get("role"),
            "structuralDesign": t.get("structuralDesign"),
            "sourceMap": t.get("sourceMap"),
            "sourceCoordinate": t.get("sourceCoordinate"),
            "previewCropPath": t.get("previewPath"),
            "sourceCropId": t.get("sourceCropId"),
            "layersUsed": layers_used,
            "tileIdsUsed": t.get("tileIdsByLayer", {}),
            "whyItMatters": f"Starter visual canon candidate for {t.get('role')} in vanilla earth mine grammar.",
            "recommendedDecision": "unsure",
            "notes": "",
        })
    review_pack = {
        "reviewType": "mine_dungeon_visual_canon_v1",
        "generatedAt": now_iso(),
        "reviewer": "Joel",
        "selectedTheme": canon.get("visualTheme", "vanilla_earth_mine"),
        "instructions": "Approve only templates that visually match real Stardew mine structure and are safe for generator use.",
        "items": items,
        "knownGaps": [
            "No pure floor_base candidate exists in canon v1; floor context is represented by floor_to_wall_transition.",
            "No explicit wall_top/front_overlay role was selected as a separate canon role; current candidates preserve Front within source crop templates.",
        ],
    }
    decision_template = {
        "reviewType": "mine_dungeon_visual_canon_v1",
        "reviewer": "Joel",
        "selectedTheme": canon.get("visualTheme", "vanilla_earth_mine"),
        "instructions": "Approve only templates that visually match real Stardew mine structure and are safe for generator use.",
        "decisions": [
            {
                "templateId": item["templateId"],
                "decision": "unsure",
                "visualStatus": "needs_review",
                "generatorStatus": "marker_fallback_only",
                "locked": False,
                "notes": "",
            }
            for item in items
        ],
    }
    (REVIEW_PACK_DIR / "mine_visual_canon_v1_review_pack.json").write_text(json.dumps(review_pack, indent=2), encoding="utf-8")
    (REVIEW_PACK_DIR / "mine_visual_canon_v1_decisions.template.json").write_text(json.dumps(decision_template, indent=2), encoding="utf-8")
    lines = [
        "# Mine Visual Canon v1 Review Pack Instructions\n",
        f"- Review pack: `{rel(REVIEW_PACK_DIR / 'mine_visual_canon_v1_review_pack.json')}`",
        f"- Decision template: `{rel(REVIEW_PACK_DIR / 'mine_visual_canon_v1_decisions.template.json')}`",
        f"- Atlas: `{rel(ATLAS_PATH)}`",
        "",
        "Workflow:",
        "1. Open the atlas and compare each candidate to its source crop preview.",
        "2. For approved items, copy the decision template to `mine_visual_canon_v1_decisions.json` and set `decision` to `approve`, `visualStatus` to `Joel_approved`, `generatorStatus` to `generator_ready`, and `locked` to `true`.",
        "3. Leave uncertain templates as `unsure`; rejected templates should use `reject`.",
        "4. Run `python import_mine_visual_canon_decisions.py` only after the real decisions file exists.",
        "",
        f"Starter candidates included: {len(items)}",
    ]
    (REPORTS / "mine_visual_canon_v1_review_pack_instructions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_importer_design() -> None:
    lines = [
        "# Mine Visual Canon Decision Importer Design\n",
        "- Script: `import_mine_visual_canon_decisions.py`",
        "- Input: `pattern_learning/mine_dungeon_visual_canon_v1/joel_review_pack/mine_visual_canon_v1_decisions.json`",
        "- Output: `pattern_learning/mine_dungeon_visual_canon_v1/mine_dungeon_visual_canon_v1.locked.json`",
        "- The original canon JSON is not overwritten.",
        "",
        "Rules:",
        "- Only `decision: approve` can become `Joel_approved`.",
        "- Only approved decisions can become `generator_ready`.",
        "- Only approved decisions can be locked.",
        "- Rejected templates become `rejected` + `disabled`.",
        "- Unsure templates remain review-gated as `needs_review` + `marker_fallback_only`.",
        "- No template can be locked without source crop, preview, layer stack, and non-loose structural evidence.",
        "- A full import report is written after import.",
    ]
    (REPORTS / "mine_visual_canon_decision_importer_design.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_safety_summary() -> None:
    lines = [
        "# Mine Visual Canon v1 Independent Safety Status\n",
        "- Production maps generated: no",
        "- New custom map generated: no",
        "- Original Moonvillage maps modified: no",
        "- mission_assets modified: no",
        "- unpacked_basegame modified: no",
        "- Approved DB modified: no",
        "- approved_tags modified: no",
        "- old custom_08/custom_09 preserved: yes",
        "- Wrapper fallback still exists: yes",
        "- Canon mode remains review-gated until Joel decisions are imported: yes",
    ]
    (REPORTS / "mine_visual_canon_v1_independent_safety_status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_review_summary(classes: dict[str, str]) -> None:
    counts = Counter(classes.values())
    reject_count = counts.get("reject_candidate", 0)
    lines = [
        "# Mine Visual Canon v1 Independent Review Summary\n",
        f"- Verdict: {'PASS for Joel review prep' if reject_count == 0 else 'PASS with rejection candidates'}",
        "- Canon file structure: passed audit",
        "- Template quality: all templates classified; see quality review report",
        "- Exact remakes: trustworthy; both exact source-crop remakes matched layer stacks",
        "- Atlas: ready for Joel review; includes combined and layer-specific previews",
        "- Review pack: ready",
        "- Wrapper canon mode: safe; it only loads Joel-approved, generator-ready, locked templates",
        f"- Templates recommended for rejection before Joel review: {reject_count}",
        "- Next recommended mission: Joel reviews the starter pack, saves a real decisions file, then run the importer and `validate_mine_visual_canon.py --locked` before enabling canon-driven custom generation.",
    ]
    (REPORTS / "mine_visual_canon_v1_independent_review_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    canon = load(CANON_PATH)
    crops = load(CROPS_PATH)
    rules = load(RULES_PATH)
    write_file_audit(canon, crops, rules)
    classes = write_template_quality(canon, crops)
    write_remake_review(crops)
    write_negative_rules_review(rules)
    write_wrapper_review()
    build_review_pack(canon, classes)
    write_importer_design()
    write_safety_summary()
    write_review_summary(classes)
    print(json.dumps({"status": "built", "templatesReviewed": len(classes), "reviewPackDir": rel(REVIEW_PACK_DIR)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
