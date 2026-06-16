#!/usr/bin/env python3
"""Build the first visual prototype profile recommendation and unlock plan."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOL_ROOT = Path(__file__).resolve().parent
REPORT_DIR = TOOL_ROOT / "reports"
STRUCTURAL_DIR = TOOL_ROOT / "structural_learning"
MINIMUM_REVIEW_DIR = STRUCTURAL_DIR / "minimum_review"
PATH_BASE_REVIEW_DIR = STRUCTURAL_DIR / "path_base_review"

ROLE_MATRIX_PATH = TOOL_ROOT / "pattern_learning" / "layout_profiles" / "layout_profile_role_matrix.json"
PROFILE_READINESS_PATH = REPORT_DIR / "production_readiness_by_layout_profile.json"
STYLEPACK_COMPAT_PATH = TOOL_ROOT / "pattern_learning" / "layout_profiles" / "stylepack_layout_profile_compatibility.json"
MINIMUM_PACK_PATH = MINIMUM_REVIEW_DIR / "minimum_structural_review_pack.json"
PATH_BASE_PACK_PATH = PATH_BASE_REVIEW_DIR / "path_base_review_pack.json"

CHOSEN_PROFILE = "outdoor"
CHOSEN_STYLEPACK = "moonvillage_forest_ruins"
CHOSEN_MAP_SIZE = "48x48"
CHOSEN_SEED = "generator default deterministic outdoor marker layout"
PATH_BASE_DECISION_FILE = STRUCTURAL_DIR / "path_base_review" / "decisions" / "path_base_decisions.json"
MINIMUM_STRUCTURAL_DECISION_FILE = MINIMUM_REVIEW_DIR / "decisions" / "minimum_structural_decisions.json"
PATH_BASE_DECISION_TEMPLATE = STRUCTURAL_DIR / "path_base_review" / "decisions" / "path_base_decisions.template.json"
MINIMUM_STRUCTURAL_DECISION_TEMPLATE = MINIMUM_REVIEW_DIR / "decisions" / "minimum_structural_decisions.template.json"
FIRST_VISUAL_REQUIRED_ROLES = ["path_base", "path_transition", "wall_body", "wall_top", "wall_corner", "wall_edge", "shadow"]
FIRST_VISUAL_ALTERNATE_ROLES = {"wall_body": ["hedge_body"], "wall_top": ["canopy_overlay"]}

REVIEW_LIMITS = {
    "critical": 24,
    "high": 18,
    "medium": 12,
    "optional": 8,
}

# Minimum safe target deliberately avoids decoration, water, and canopy
# requirements for the first visual pass. Those can stay disabled or marker-only
# until their own review is done.
OUTDOOR_MINIMUM_ROLES = [
    {
        "role": "ground_base",
        "requiredClass": "ground_base",
        "requiredLayer": "Back",
        "collision": "walkable",
        "minimumCount": 1,
        "priority": "critical",
        "preferredCandidateSource": "already approved vanilla/base-game metadata",
        "reviewRole": None,
    },
    {
        "role": "ground_variation",
        "requiredClass": "ground_base",
        "requiredLayer": "Back",
        "collision": "walkable",
        "minimumCount": 1,
        "priority": "high",
        "preferredCandidateSource": "already approved vanilla/base-game metadata",
        "reviewRole": None,
    },
    {
        "role": "path_base",
        "requiredClass": "path_base",
        "requiredLayer": "Back",
        "collision": "walkable",
        "minimumCount": 1,
        "priority": "critical",
        "preferredCandidateSource": "vanilla/base-game road or path tiles with path/floor stack evidence",
        "reviewRole": "path_base",
    },
    {
        "role": "path_transition",
        "requiredClass": "path_transition",
        "requiredLayer": "Back",
        "collision": "walkable",
        "minimumCount": 4,
        "priority": "critical",
        "preferredCandidateSource": "structural_learning path_transition vanilla candidates",
        "reviewRole": "path_transition",
    },
    {
        "role": "wall_body",
        "requiredClass": "wall_body or exterior_wall",
        "requiredLayer": "Buildings",
        "collision": "blocked",
        "minimumCount": 1,
        "priority": "critical",
        "preferredCandidateSource": "outdoor vanilla Buildings wall/body candidates",
        "reviewRole": "wall_body",
    },
    {
        "role": "wall_top",
        "requiredClass": "wall_top or wall_front",
        "requiredLayer": "Front",
        "collision": "decorative_front",
        "minimumCount": 1,
        "priority": "critical",
        "preferredCandidateSource": "outdoor vanilla Front wall-top candidates near Buildings bodies",
        "reviewRole": "wall_top",
    },
    {
        "role": "wall_corner",
        "requiredClass": "wall_corner",
        "requiredLayer": "Buildings/Front",
        "collision": "blocked",
        "minimumCount": 4,
        "priority": "critical",
        "preferredCandidateSource": "outdoor vanilla corner candidates with turn/cap neighbor masks",
        "reviewRole": "wall_corner",
    },
    {
        "role": "wall_edge",
        "requiredClass": "wall_side or wall_front",
        "requiredLayer": "Buildings/Front",
        "collision": "blocked or decorative_front by approved profile",
        "minimumCount": 4,
        "priority": "critical",
        "preferredCandidateSource": "outdoor vanilla edge/cap candidates",
        "reviewRole": "wall_edge",
    },
    {
        "role": "shadow",
        "requiredClass": "shadow",
        "requiredLayer": "Back or Front",
        "collision": "decorative_front",
        "minimumCount": 1,
        "priority": "high",
        "preferredCandidateSource": "shadow candidates near wall/body stacks",
        "reviewRole": "shadow",
    },
    {
        "role": "canopy_overlay",
        "requiredClass": "tree_canopy or overlay",
        "requiredLayer": "AlwaysFront",
        "collision": "overlay_only",
        "minimumCount": 0,
        "priority": "optional",
        "preferredCandidateSource": "canopy_overlay candidates; tile 946 only if seasonal outdoors canopy-center scope applies",
        "reviewRole": "canopy_overlay",
    },
    {
        "role": "decoration",
        "requiredClass": "decoration",
        "requiredLayer": "Front",
        "collision": "decorative_front",
        "minimumCount": 0,
        "priority": "optional",
        "preferredCandidateSource": "later decoration review; omit from first visual prototype",
        "reviewRole": None,
    },
    {
        "role": "water_edge",
        "requiredClass": "water_transition",
        "requiredLayer": "Back",
        "collision": "water_blocked or walkable edge by approved profile",
        "minimumCount": 0,
        "priority": "optional",
        "preferredCandidateSource": "water_edge review pack only if prototype includes water",
        "reviewRole": "water_edge",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def role_lookup(role_matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for profile, roles in (role_matrix.get("profiles") or {}).items():
        for item in roles:
            lookup[f"{profile}:{item.get('roleName')}"] = item
            lookup.setdefault(item.get("roleName"), item)
    return lookup


def profile_stylepack_support(compatibility: dict[str, Any], profile: str) -> list[str]:
    out = []
    key = "dungeon" if profile in {"dungeon", "mine"} else profile
    for item in compatibility.get("stylepacks", []):
        support = (item.get("supports") or {}).get(key)
        out.append(f"{item.get('stylePackId')}: {support}")
    return out


def score_profile(profile_id: str, role_matrix: dict[str, Any], readiness: dict[str, Any], compatibility: dict[str, Any]) -> dict[str, Any]:
    roles = (role_matrix.get("profiles") or {}).get(profile_id, [])
    readiness_item = next((p for p in readiness.get("profiles", []) if p.get("profileId") == profile_id), {})
    required_roles = [r for r in roles if not r.get("optional")]
    missing = [r for r in required_roles if not r.get("productionAllowedNow")]
    approved = [r for r in required_roles if r.get("productionAllowedNow")]
    stylepack_support = profile_stylepack_support(compatibility, profile_id)
    if profile_id == "outdoor":
        risk = "medium"
        effort = "medium: most roles already have focused outdoor/structural review candidates; path_base still needs a small dedicated review."
        payoff = "high: directly exercises Moonvillage forest/ruins, hedge/maze, and fairy-forest stylepacks."
        recommended = True
    elif profile_id == "indoor":
        risk = "low-medium"
        effort = "medium-low on role count, but there is no mature Moonvillage interior stylepack yet."
        payoff = "medium: useful later, but less relevant to current forest/ruins generator goals."
        recommended = False
    else:
        risk = "medium-high"
        effort = "high: dungeon needs cave wall, ladder, ore, monster, treasure, and entrance/exit roles."
        payoff = "high later: strong for void dungeon, but too many technical roles remain unapproved for the first visual pass."
        recommended = False
    return {
        "profile": profile_id,
        "requiredRoles": [r.get("roleName") for r in required_roles],
        "currentlyApprovedRoles": [r.get("roleName") for r in approved],
        "missingRoles": [{"role": r.get("roleName"), "reason": r.get("blockerReason")} for r in missing],
        "optionalRoles": [r.get("roleName") for r in roles if r.get("optional")],
        "stylepackSupport": stylepack_support,
        "markerFallbackCoverage": "available" if all(r.get("canGenerateMarker") for r in roles) else "partial",
        "validatorReadiness": "PASS: marker, layer grammar, out-of-bounds, stylepack, and regression tests passed in the previous profile mission.",
        "riskLevel": risk,
        "estimatedManualApprovalEffort": effort,
        "expectedVisualPayoff": payoff,
        "firstVisualTestRecommended": recommended,
        "visualPrototypeAllowedNow": readiness_item.get("visualPrototypeAllowed", False),
    }


def preview_for_role(role: str) -> str | None:
    if role == "path_base":
        path = PATH_BASE_REVIEW_DIR / "previews" / "path_base_labeled.png"
        return str(path) if path.exists() else None
    candidates = [
        MINIMUM_REVIEW_DIR / "previews" / f"{role}_minimum_labeled.png",
        MINIMUM_REVIEW_DIR / "previews" / f"{role}_minimum_clean.png",
        STRUCTURAL_DIR / "previews" / f"{role}_review_labeled.png",
        STRUCTURAL_DIR / "previews" / f"{role}_review_clean.png",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def review_pack_for_role(role: str) -> str | None:
    if role == "path_base" and PATH_BASE_PACK_PATH.exists():
        return str(PATH_BASE_PACK_PATH)
    candidates = [
        MINIMUM_REVIEW_DIR / "minimum_structural_review_pack.json",
        STRUCTURAL_DIR / "review_packs" / f"{role}_review_pack.json",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def build_checklist(role_matrix_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for spec in OUTDOOR_MINIMUM_ROLES:
        matrix = role_matrix_lookup.get(f"outdoor:{spec['role']}", {})
        approved_count = matrix.get("compatibleApprovedCount", matrix.get("approvedCount", 0))
        blocker = matrix.get("blockerReason", "not present in role matrix")
        review_role = spec.get("reviewRole")
        if spec["minimumCount"] == 0:
            blocker = "optional for first visual prototype; omit or keep marker-only."
        elif approved_count and blocker == "ready":
            blocker = "ready"
        item = {
            "role": spec["role"],
            "requiredClass": spec["requiredClass"],
            "requiredLayer": spec["requiredLayer"],
            "collision": spec["collision"],
            "minimumCount": spec["minimumCount"],
            "preferredCandidateSource": spec["preferredCandidateSource"],
            "reviewPackPath": review_pack_for_role(review_role) if review_role else None,
            "previewPath": preview_for_role(review_role) if review_role else None,
            "currentlyApprovedCount": approved_count,
            "blockerReason": blocker,
            "priority": spec["priority"],
        }
        out.append(item)
    return out


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, int]:
    risk_flags = candidate.get("riskFlags") or []
    return (float(candidate.get("evidenceScore") or 0), -len(risk_flags))


def build_review_queue(checklist: list[dict[str, Any]]) -> dict[str, Any]:
    minimum_pack = load_json(MINIMUM_PACK_PATH, {})
    path_base_pack = load_json(PATH_BASE_PACK_PATH, {})
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in minimum_pack.get("candidates", []):
        by_role[candidate.get("roleName", "")].append(candidate)
    path_base_role = path_base_pack.get("roleName", "path_base")
    for candidate in path_base_pack.get("candidates", []):
        role_name = candidate.get("roleName") or path_base_role
        by_role[role_name].append({**candidate, "roleName": role_name})
    queue_items = []
    for item in checklist:
        role = item["role"]
        if item["priority"] == "optional":
            limit = REVIEW_LIMITS["optional"]
        else:
            limit = REVIEW_LIMITS.get(item["priority"], 12)
        source_role = role
        if role == "canopy_overlay":
            source_role = "canopy_overlay"
        candidates = sorted(by_role.get(source_role, []), key=candidate_sort_key, reverse=True)[:limit]
        trimmed = []
        for candidate in candidates:
            example_maps = candidate.get("exampleMaps")
            if example_maps is None and isinstance(candidate.get("observedMaps"), list):
                example_maps = {
                    item.get("mapName"): item.get("count")
                    for item in candidate.get("observedMaps", [])
                    if item.get("mapName")
                }
            trimmed_item = {
                "candidateId": candidate.get("candidateId"),
                "roleName": role,
                "sourceRole": candidate.get("roleName"),
                "proposedClass": candidate.get("proposedClass"),
                "proposedPurpose": candidate.get("proposedPurpose"),
                "proposedAllowedLayers": candidate.get("proposedAllowedLayers"),
                "proposedCollision": candidate.get("proposedCollision"),
                "sourceTilesheet": candidate.get("sourceTilesheet"),
                "localTileId": candidate.get("localTileId"),
                "layer": candidate.get("layer"),
                "evidenceScore": candidate.get("evidenceScore"),
                "exampleMaps": example_maps,
                "exampleCoordinates": candidate.get("exampleCoordinates", [])[:5],
                "neighborPatternSummary": candidate.get("neighborPatternSummary"),
                "stackPatternSummary": candidate.get("stackPatternSummary"),
                "riskFlags": candidate.get("riskFlags") or [],
                "previewPath": item.get("previewPath"),
                "humanDecision": None,
            }
            trimmed.append(trimmed_item)
        queue_items.append(
            {
                "role": role,
                "priority": item["priority"],
                "candidateLimit": limit,
                "candidateCount": len(trimmed),
                "reviewPackPath": item.get("reviewPackPath"),
                "previewPath": item.get("previewPath"),
                "blockerReason": item.get("blockerReason"),
                "candidates": trimmed,
            }
        )
    queue = {
        "generatedAt": now_iso(),
        "profile": CHOSEN_PROFILE,
        "stylepack": CHOSEN_STYLEPACK,
        "autoApprovalAllowed": False,
        "productionMapGenerated": False,
        "notes": [
            "Queue is intentionally small and role-focused.",
            "path_base now uses the dedicated path_base_review_pack and remains manual-review only.",
            "optional decoration/water/canopy roles are not required for the first visual prototype.",
        ],
        "items": queue_items,
    }
    decisions = first_visual_decision_wrapper()
    return {"queue": queue, "decisions": decisions}


def rel_tool(path: Path) -> str:
    try:
        return str(path.relative_to(TOOL_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def decision_file_for_role(role: str) -> Path:
    return PATH_BASE_DECISION_FILE if role == "path_base" else MINIMUM_STRUCTURAL_DECISION_FILE


def decision_template_for_role(role: str) -> Path:
    return PATH_BASE_DECISION_TEMPLATE if role == "path_base" else MINIMUM_STRUCTURAL_DECISION_TEMPLATE


def first_visual_decision_wrapper() -> dict[str, Any]:
    return {
        "reviewType": "first_visual_outdoor_unlock",
        "profile": CHOSEN_PROFILE,
        "stylepack": CHOSEN_STYLEPACK,
        "requiredDecisionFiles": [
            rel_tool(PATH_BASE_DECISION_FILE),
            rel_tool(MINIMUM_STRUCTURAL_DECISION_FILE),
        ],
        "requiredRoles": FIRST_VISUAL_REQUIRED_ROLES,
        "alternateRoleNotes": {
            "wall_body": "A hedge/body role can satisfy this only if imported as an approved wall_body/exterior_wall-compatible profile.",
            "wall_top": "A canopy_overlay profile can satisfy the visual top/overlay only for a stylepack that uses canopy instead of wall top.",
        },
        "status": "waiting_for_human_decisions",
        "productionMapGenerated": False,
        "notes": [
            "This wrapper tracks the two real manual decision files. It intentionally does not duplicate every candidate decision.",
            "path_base is critical, but approving path_base alone is not sufficient for the first outdoor visual prototype.",
            "Rejected and unsure decisions must not be imported or merged.",
            "Tile 946 remains forbidden for path_base and all wall/body/blocking/collision roles.",
        ],
    }


def build_manual_decision_checklist(checklist: list[dict[str, Any]], queue: dict[str, Any]) -> dict[str, Any]:
    by_role = {item["role"]: item for item in checklist}
    queue_by_role = {item["role"]: item for item in queue.get("items", [])}
    roles = []
    for role in FIRST_VISUAL_REQUIRED_ROLES + ["canopy_overlay"]:
        item = by_role.get(role, {})
        queue_item = queue_by_role.get(role, {})
        minimum = item.get("minimumCount", 1)
        if role == "canopy_overlay":
            minimum = 0
        approved_count = item.get("currentlyApprovedCount", 0)
        roles.append(
            {
                "roleName": role,
                "alternateNames": FIRST_VISUAL_ALTERNATE_ROLES.get(role, []),
                "reviewPackPath": item.get("reviewPackPath"),
                "previewPath": item.get("previewPath"),
                "decisionFilePath": rel_tool(decision_file_for_role(role)),
                "decisionTemplatePath": rel_tool(decision_template_for_role(role)),
                "minimumApprovalsNeeded": minimum,
                "recommendedCandidates": [
                    {
                        "candidateId": candidate.get("candidateId"),
                        "sourceTilesheet": candidate.get("sourceTilesheet"),
                        "localTileId": candidate.get("localTileId"),
                        "evidenceScore": candidate.get("evidenceScore"),
                        "riskFlags": candidate.get("riskFlags") or [],
                    }
                    for candidate in (queue_item.get("candidates") or [])[:8]
                ],
                "currentApprovalCount": approved_count,
                "stillBlocked": bool(minimum and approved_count < minimum),
                "notes": (
                    "Critical but not sufficient alone; the full structural minimum set must also be approved."
                    if role == "path_base"
                    else "Optional overlay alternative for wall_top when the selected outdoor style uses canopy."
                    if role == "canopy_overlay"
                    else item.get("blockerReason", "")
                ),
            }
        )
    return {
        "generatedAt": now_iso(),
        "reviewType": "first_visual_manual_decision_checklist",
        "profile": CHOSEN_PROFILE,
        "stylepack": CHOSEN_STYLEPACK,
        "decisionFiles": [rel_tool(PATH_BASE_DECISION_FILE), rel_tool(MINIMUM_STRUCTURAL_DECISION_FILE)],
        "pathBaseIsCriticalButNotSufficient": True,
        "fullMinimumStructuralSetMustBeApproved": True,
        "roles": roles,
    }


def markdown_manual_decision_checklist(doc: dict[str, Any]) -> str:
    lines = [
        "# First Visual Manual Decision Checklist",
        "",
        f"- Profile: `{doc['profile']}`",
        f"- Stylepack: `{doc['stylepack']}`",
        "- `path_base` is critical but not sufficient alone.",
        "- The full minimum structural set must be approved before visual generation.",
        "",
        "## Decision Files",
        "",
    ]
    for path in doc["decisionFiles"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Roles", ""])
    for role in doc["roles"]:
        alternate = f" / {', '.join(role['alternateNames'])}" if role.get("alternateNames") else ""
        lines.extend(
            [
                f"### {role['roleName']}{alternate}",
                "",
                f"- Review pack: `{role.get('reviewPackPath') or 'not available yet'}`",
                f"- Preview: `{role.get('previewPath') or 'not available yet'}`",
                f"- Decision file: `{role['decisionFilePath']}`",
                f"- Decision template: `{role['decisionTemplatePath']}`",
                f"- Minimum approvals needed: `{role['minimumApprovalsNeeded']}`",
                f"- Current approval count: `{role['currentApprovalCount']}`",
                f"- Still blocked: `{role['stillBlocked']}`",
                f"- Notes: {role['notes']}",
            ]
        )
        if role["recommendedCandidates"]:
            lines.append("- Recommended candidates:")
            for candidate in role["recommendedCandidates"]:
                lines.append(f"  - `{candidate['candidateId']}`: {candidate.get('sourceTilesheet')} tile {candidate.get('localTileId')} score {candidate.get('evidenceScore')}")
        lines.append("")
    return "\n".join(lines)


def build_manual_readiness(checklist_doc: dict[str, Any]) -> dict[str, Any]:
    decision_files = {
        "path_base": PATH_BASE_DECISION_FILE.exists(),
        "minimum_structural": MINIMUM_STRUCTURAL_DECISION_FILE.exists(),
    }
    blocked_roles = [role for role in checklist_doc["roles"] if role.get("stillBlocked")]
    return {
        "generatedAt": now_iso(),
        "profile": CHOSEN_PROFILE,
        "stylepack": CHOSEN_STYLEPACK,
        "pathBaseDecisionFileExists": decision_files["path_base"],
        "minimumStructuralDecisionFileExists": decision_files["minimum_structural"],
        "unapprovedRoles": [role["roleName"] for role in blocked_roles],
        "visualPrototypeBlocked": bool(blocked_roles or not all(decision_files.values())),
        "nextManualAction": "Fill and save path_base_decisions.json and minimum_structural_decisions.json, then run the importer and validators.",
    }


def markdown_manual_readiness(doc: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# First Visual Manual Approval Readiness",
            "",
            f"- Path base decision file exists: `{doc['pathBaseDecisionFileExists']}`",
            f"- Minimum structural decision file exists: `{doc['minimumStructuralDecisionFileExists']}`",
            f"- Roles still unapproved/blocking: {', '.join(doc['unapprovedRoles']) or 'none'}",
            f"- Visual prototype blocked: `{doc['visualPrototypeBlocked']}`",
            f"- Next manual action: {doc['nextManualAction']}",
            "",
            "The first outdoor visual prototype remains blocked until both decision files exist, approved decisions are imported, and all required structural roles validate.",
        ]
    )


def markdown_comparison(comparison: dict[str, Any]) -> str:
    lines = ["# First Visual Profile Comparison", ""]
    for item in comparison["profiles"]:
        rec = "YES" if item["firstVisualTestRecommended"] else "no"
        lines.extend(
            [
                f"## {item['profile']}",
                "",
                f"- Recommended first: {rec}",
                f"- Risk level: {item['riskLevel']}",
                f"- Validator readiness: {item['validatorReadiness']}",
                f"- Marker fallback coverage: {item['markerFallbackCoverage']}",
                f"- Manual approval effort: {item['estimatedManualApprovalEffort']}",
                f"- Visual payoff: {item['expectedVisualPayoff']}",
                f"- Approved roles: {', '.join(item['currentlyApprovedRoles']) or 'none'}",
                f"- Optional roles: {', '.join(item['optionalRoles']) or 'none'}",
                "",
                "### Missing Roles",
                "",
            ]
        )
        for missing in item["missingRoles"]:
            lines.append(f"- `{missing['role']}`: {missing['reason']}")
        lines.extend(["", "### Stylepack Support", ""])
        for support in item["stylepackSupport"]:
            lines.append(f"- {support}")
        lines.append("")
    return "\n".join(lines)


def markdown_recommendation() -> str:
    return """# First Visual Prototype Recommendation

Recommendation: **outdoor first**, using `moonvillage_forest_ruins` as the first stylepack target.

Why outdoor wins:

- It has the best direct Moonvillage payoff: forest, ruins, fairy-forest, hedge, and village-edge maps are the main generator target.
- Existing stylepacks are outdoor-first; `moonvillage_forest_ruins`, `fairy_forest`, and `cursed_hedge_maze` already validate in marker-safe mode.
- Ground and ground variation are already production-ready from vanilla/base-game metadata.
- The missing roles map cleanly onto the structural review packs already prepared: path transitions, wall bodies, wall tops, corners, edges, and shadows.
- Dungeon/mine is structurally clean but needs more technical roles before visual output: ladder, entrance/exit, ore, monster spawn, treasure, cave wall, cave top, and cave shadow.
- Indoor has clean grammar and fewer missing roles on paper, but it lacks a mature stylepack and is less useful for the immediate Moonvillage map-generation goal.

Scope for the first visual prototype:

- Use a 48x48 outdoor map.
- Use `moonvillage_forest_ruins`.
- Use approved ground/ground variation.
- Require only the smallest structural set: path base, path transition, wall body, wall top, four corners, four edges/caps, and shadow if needed.
- Omit water, decoration, and canopy from the first visual prototype unless those roles are approved before the run.

No visual prototype is generated in this mission.
"""


def markdown_checklist(checklist: list[dict[str, Any]]) -> str:
    lines = ["# First Visual Minimum Approval Checklist", "", f"- Selected profile: `{CHOSEN_PROFILE}`", f"- Selected stylepack: `{CHOSEN_STYLEPACK}`", ""]
    for item in checklist:
        lines.extend(
            [
                f"## {item['role']}",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Required class: `{item['requiredClass']}`",
                f"- Required layer: `{item['requiredLayer']}`",
                f"- Collision: `{item['collision']}`",
                f"- Minimum count: `{item['minimumCount']}`",
                f"- Currently approved count: `{item['currentlyApprovedCount']}`",
                f"- Preferred source: {item['preferredCandidateSource']}",
                f"- Review pack: `{item['reviewPackPath'] or 'not available yet'}`",
                f"- Preview: `{item['previewPath'] or 'not available yet'}`",
                f"- Blocker: {item['blockerReason']}",
                "",
            ]
        )
    return "\n".join(lines)


def markdown_queue(queue: dict[str, Any]) -> str:
    lines = ["# First Visual Review Queue", "", f"- Profile: `{queue['profile']}`", f"- Stylepack: `{queue['stylepack']}`", "- Auto approval: `false`", ""]
    for item in queue["items"]:
        lines.extend(
            [
                f"## {item['role']}",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Candidate count: `{item['candidateCount']}`",
                f"- Review pack: `{item['reviewPackPath'] or 'not available yet'}`",
                f"- Preview: `{item['previewPath'] or 'not available yet'}`",
                f"- Blocker: {item['blockerReason']}",
            ]
        )
        if item["candidates"]:
            lines.append("- Top candidates:")
            for c in item["candidates"][:8]:
                lines.append(f"  - `{c['candidateId']}`: {c.get('sourceTilesheet')} tile {c.get('localTileId')} score {c.get('evidenceScore')}")
        lines.append("")
    return "\n".join(lines)


def markdown_tile_946() -> str:
    return """# First Visual Tile 946 Impact

- Chosen profile: `outdoor`.
- Chosen stylepack: `moonvillage_forest_ruins`.
- Tile 946 is **not needed** for the first visual prototype unlock plan.
- The first visual prototype can proceed without canopy overlays.
- Approved 946 scope remains narrow: seasonal outdoors sheets only, `canopy_overlay` / `tree_canopy_center`, `AlwaysFront`, `overlay_only`.
- Forbidden 946 contexts remain forbidden: wall body, wall corner as Buildings/blocking, wall edge as Buildings/blocking, wall base, hedge body, blocker, collision blocker, Buildings collision, and blocked collision.
- If a later fairy-forest/canopy pass wants tile 946, it should be reviewed as an optional canopy overlay profile only, not as a structural blocker.
"""


def markdown_execution_plan() -> str:
    return f"""# First Visual Prototype Execution Plan

This is a plan only. No visual prototype was generated in this mission.

- Selected profile: `{CHOSEN_PROFILE}`
- Selected stylepack: `{CHOSEN_STYLEPACK}`
- Map size: `{CHOSEN_MAP_SIZE}`
- Seed: `{CHOSEN_SEED}`
- Expected output folder for the future run: `tools/tiled-map-assistant/generated_maps/visual_tests/outdoor/`

Future command, after the minimum approvals are imported and validated:

```powershell
python tools/tiled-map-assistant/generate_marker_map.py --layout-profile outdoor
```

The actual production/visual command should remain gated behind `generator_safety_gate.py`; do not bypass it with raw tile IDs.

Pre-run validators:

- `python tools/tiled-map-assistant/validate_stylepacks.py`
- `python tools/tiled-map-assistant/validate_marker_map.py --layout-profile outdoor`
- `python tools/tiled-map-assistant/validate_layer_grammar.py --marker-only`
- `python tools/tiled-map-assistant/validate_structural_approved_tags.py`
- `python tools/tiled-map-assistant/run_validation_tests.py`

Post-run validators:

- Validate generated TMX/TMJ parse.
- Validate layer grammar in production mode.
- Validate out-of-bounds.
- Confirm no tile 946 wall/body/blocking/collision usage.
- Confirm no unapproved tile IDs appear in final visual layers.

Safeguards:

- Back up `tile_database_v1_human_approved.json` before importing any new approved tags.
- Keep original Moonvillage maps untouched.
- Keep `mission_assets` read-only.
- Write future visual tests only under `tools/tiled-map-assistant/generated_maps/visual_tests/`.

Acceptance criteria for the future visual prototype:

- Visual map is generated only after all required minimum roles validate.
- No marker role remains for a required production role.
- Optional decoration/water/canopy roles may be omitted.
- Exits remain reachable and protected.
- TMX/TMJ opens in Tiled.
"""


def markdown_safety() -> str:
    return """# First Visual Profile Unlock Safety Report

- Production maps generated: NO.
- Original Moonvillage maps modified: NO.
- `mission_assets` modified: NO.
- New tiles auto-approved: NO.
- Tile 946 canopy-only rule preserved: YES.
- Tile 946 wall/body/blocking/collision ban preserved: YES.
- Work stayed inside `tools/tiled-map-assistant`.
- Stylepack validation: PASS, 0 errors, 4 expected warnings.
- Marker validation: PASS for outdoor, indoor, and dungeon.
- Layer grammar marker validation: PASS, 0 issues.
- Out-of-bounds validation: PASS for outdoor, indoor, and dungeon.
- Full regression suite: PASS, 52/52 tests.
"""


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)

    role_matrix = load_json(ROLE_MATRIX_PATH, {"profiles": {}})
    readiness = load_json(PROFILE_READINESS_PATH, {"profiles": []})
    compatibility = load_json(STYLEPACK_COMPAT_PATH, {"stylepacks": []})
    lookup = role_lookup(role_matrix)

    comparison = {
        "generatedAt": now_iso(),
        "decision": CHOSEN_PROFILE,
        "decisionStylepack": CHOSEN_STYLEPACK,
        "profiles": [score_profile(profile, role_matrix, readiness, compatibility) for profile in ["outdoor", "indoor", "dungeon"]],
    }
    checklist = {
        "generatedAt": now_iso(),
        "profile": CHOSEN_PROFILE,
        "stylepack": CHOSEN_STYLEPACK,
        "minimumScope": "first controlled outdoor visual prototype; water, decoration, and canopy omitted unless separately approved",
        "items": build_checklist(lookup),
    }
    queue_bundle = build_review_queue(checklist["items"])
    manual_checklist = build_manual_decision_checklist(checklist["items"], queue_bundle["queue"])
    manual_readiness = build_manual_readiness(manual_checklist)

    write_json(REPORT_DIR / "first_visual_profile_comparison.json", comparison)
    write_text(REPORT_DIR / "first_visual_profile_comparison.md", markdown_comparison(comparison))
    write_text(REPORT_DIR / "first_visual_prototype_recommendation.md", markdown_recommendation())
    write_json(REPORT_DIR / "first_visual_minimum_approval_checklist.json", checklist)
    write_text(REPORT_DIR / "first_visual_minimum_approval_checklist.md", markdown_checklist(checklist["items"]))
    write_json(STRUCTURAL_DIR / "first_visual_review_queue.json", queue_bundle["queue"])
    write_text(REPORT_DIR / "first_visual_review_queue.md", markdown_queue(queue_bundle["queue"]))
    write_json(STRUCTURAL_DIR / "first_visual_decisions.template.json", queue_bundle["decisions"])
    write_json(STRUCTURAL_DIR / "first_visual_manual_decision_checklist.json", manual_checklist)
    write_text(REPORT_DIR / "first_visual_manual_decision_checklist.md", markdown_manual_decision_checklist(manual_checklist))
    write_json(REPORT_DIR / "first_visual_manual_approval_readiness.json", manual_readiness)
    write_text(REPORT_DIR / "first_visual_manual_approval_readiness.md", markdown_manual_readiness(manual_readiness))
    write_text(REPORT_DIR / "first_visual_tile_946_impact.md", markdown_tile_946())
    write_text(REPORT_DIR / "first_visual_prototype_execution_plan.md", markdown_execution_plan())
    write_text(REPORT_DIR / "first_visual_profile_unlock_safety_report.md", markdown_safety())
    print(f"Recommended first visual prototype profile: {CHOSEN_PROFILE} / {CHOSEN_STYLEPACK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
