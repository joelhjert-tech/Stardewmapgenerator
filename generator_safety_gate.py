#!/usr/bin/env python3
"""Safety gate for visual/prototype map generators."""

from __future__ import annotations

import subprocess
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

from validate_stylepacks import validate_all
from validate_layer_grammar import build_production_readiness_matrix, production_block_reasons
from validate_out_of_bounds import check_out_of_bounds, errors_and_warnings


TOOL_ROOT = Path(__file__).resolve().parent
REPORT_DIR = TOOL_ROOT / "reports"
MARKER_TEST_ROOT = TOOL_ROOT / "generated_maps" / "marker_tests"
MARKER_SEMANTIC_MAP = MARKER_TEST_ROOT / "outdoor" / "marker_test_map.semantic.json"


def write_gate_report(generator_name: str, action: str, reasons: list[str], checks: dict | None = None) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks = checks or {}
    lines = [
        "# Generator Safety Gate Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
        f"- Generator: `{generator_name}`",
        f"- Action: `{action}`",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in reasons)
    if checks:
        lines.extend(["", "## Gate Checks", ""])
        for key, value in checks.items():
            lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "## Policy",
        "",
        "- Production visual generation is blocked until stylepack validation passes and structural tile roles resolve to approved profiles.",
        "- If structural roles are marker-only, generators must fall back to `generate_marker_map.py`.",
        "- Marker map validation and layer grammar validation must pass after fallback generation.",
        "- Out-of-bounds validation must pass for marker-only and production output.",
        "- Tile 946 must never be emitted as Buildings/wall/body/blocking output.",
    ])
    (REPORT_DIR / "generator_safety_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORT_DIR / "generator_layer_grammar_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_subprocess_check(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(args, text=True, capture_output=True)
    output = (result.stdout or "").strip()
    if result.stderr:
        output = (output + "\n" + result.stderr.strip()).strip()
    return result.returncode == 0, output


def validate_out_of_bounds_map(path: Path = MARKER_SEMANTIC_MAP) -> dict:
    if not path.exists():
        return {
            "pass": False,
            "reason": f"Out-of-bounds report cannot be generated because map is missing: {path}",
            "escapeCount": None,
            "unreachableExitCount": None,
            "unreachableWalkablePocketCount": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        result = check_out_of_bounds(data)
        errors, warnings = errors_and_warnings(result)
    except Exception as exc:
        return {
            "pass": False,
            "reason": f"Out-of-bounds report cannot be generated: {exc}",
            "escapeCount": None,
            "unreachableExitCount": None,
            "unreachableWalkablePocketCount": None,
        }
    return {
        "pass": not errors,
        "reason": "Out-of-bounds validation passed." if not errors else "; ".join(errors),
        "escapeCount": len(result["outOfBoundsEscapes"]),
        "unreachableExitCount": len(result["unreachableDeclaredExits"]),
        "unreachableWalkablePocketCount": len(result["unreachableWalkablePockets"]),
        "warningCount": len(warnings),
    }


def evaluate_gate(
    stylepack_validation: dict,
    readiness: dict,
    production_requested: bool = True,
    out_of_bounds_validation: dict | None = None,
) -> dict:
    reasons: list[str] = []
    if not stylepack_validation["pass"]:
        reasons.append("Stylepack validation failed.")
    if out_of_bounds_validation is None:
        reasons.append("Out-of-bounds validation was not supplied.")
    elif not out_of_bounds_validation.get("pass", False):
        reasons.append(out_of_bounds_validation.get("reason") or "Out-of-bounds validation failed.")
    if stylepack_validation["markerOnlyRequired"]:
        reasons.append("Structural roles are marker-only because approved border/transition/wall/canopy/corner tiles are missing.")
    if not stylepack_validation["productionReady"]:
        reasons.append("Production-ready visual output is not available.")
    if production_requested:
        reasons.extend(production_block_reasons(readiness))
    return {
        "action": "fallback_to_marker_only" if reasons else "visual_generation_allowed",
        "reasons": reasons or ["All safety gates passed."],
        "shouldFallback": bool(reasons),
    }


def evaluate_marker_rule(rule: dict, readiness: dict | None = None, production_requested: bool = False) -> dict:
    """Evaluate a calibrated marker-only generator rule.

    A marker rule may be used to emit semantic marker output. It must not unlock
    production visuals unless the rule and readiness matrix both explicitly allow it.
    """
    readiness = readiness or {}
    production_allowed = bool(rule.get("productionAllowedNow") or rule.get("productionAllowed"))
    marker_allowed = bool(rule.get("markerOnlyAllowed", True))
    required = set(rule.get("requiredApprovedClasses") or [])
    approved = set((readiness.get("classCounts") or {}).keys())
    missing = sorted(required - approved)
    if production_requested:
        reasons = []
        if not production_allowed:
            reasons.append(f"Rule {rule.get('ruleId')} is marker-only and cannot produce production visuals.")
        if missing:
            reasons.append(f"Rule {rule.get('ruleId')} is missing approved production classes: {', '.join(missing)}.")
        if reasons:
            return {"action": "fallback_to_marker_only", "shouldFallback": True, "markerOnlyAllowed": marker_allowed, "productionAllowed": False, "reasons": reasons}
        return {"action": "visual_generation_allowed", "shouldFallback": False, "markerOnlyAllowed": marker_allowed, "productionAllowed": True, "reasons": ["Rule and approved classes allow production output."]}
    if marker_allowed:
        return {"action": "marker_rule_allowed", "shouldFallback": False, "markerOnlyAllowed": True, "productionAllowed": False, "reasons": ["Marker-only semantic output allowed."]}
    return {"action": "rule_blocked", "shouldFallback": True, "markerOnlyAllowed": False, "productionAllowed": False, "reasons": ["Rule is not allowed even for marker output."]}


def run_gate(generator_name: str) -> dict:
    """Run the safety gate and return both caller-control and validation status."""
    validation = validate_all()
    readiness = build_production_readiness_matrix()
    out_of_bounds = validate_out_of_bounds_map()
    decision = evaluate_gate(validation, readiness, production_requested=True, out_of_bounds_validation=out_of_bounds)
    checks = {
        "stylepackValidationPass": validation["pass"],
        "stylepackProductionReady": validation["productionReady"],
        "stylepackMarkerOnlyRequired": validation["markerOnlyRequired"],
        "structuralProductionReady": readiness["structuralProductionReady"],
        "allProductionRolesReady": readiness["allProductionReady"],
        "outOfBoundsCheckPass": out_of_bounds["pass"],
        "outOfBoundsEscapeCount": out_of_bounds["escapeCount"],
        "outOfBoundsUnreachableExitCount": out_of_bounds["unreachableExitCount"],
        "outOfBoundsUnreachableWalkablePocketCount": out_of_bounds["unreachableWalkablePocketCount"],
        "tile946Quarantine": "enforced by stylepack and layer grammar validators",
        "restrictedAssetCheck": "enforced by stylepack validator",
    }
    if decision["shouldFallback"]:
        subprocess.run([sys.executable, str(TOOL_ROOT / "generate_marker_map.py"), "--layout-profile", "outdoor"], check=True)
        marker_ok, marker_output = run_subprocess_check([sys.executable, str(TOOL_ROOT / "validate_marker_map.py"), "--layout-profile", "outdoor"])
        grammar_ok, grammar_output = run_subprocess_check([sys.executable, str(TOOL_ROOT / "validate_layer_grammar.py"), "--marker-only"])
        oob_ok, oob_output = run_subprocess_check([sys.executable, str(TOOL_ROOT / "validate_out_of_bounds.py"), str(MARKER_SEMANTIC_MAP)])
        checks["markerMapValidationPass"] = marker_ok
        checks["layerGrammarValidationPass"] = grammar_ok
        checks["outOfBoundsCheckPass"] = oob_ok
        checks["outOfBoundsOutput"] = oob_output
        if not marker_ok:
            decision["reasons"].append(f"Marker map validation failed after fallback: {marker_output}")
        if not grammar_ok:
            decision["reasons"].append(f"Layer grammar validation failed after fallback: {grammar_output}")
        if not oob_ok:
            decision["reasons"].append(f"Out-of-bounds validation failed after fallback: {oob_output}")
        write_gate_report(generator_name, "fallback_to_marker_only", decision["reasons"], checks)
        return {
            "shouldStop": True,
            "ok": marker_ok and grammar_ok and oob_ok,
            "action": "fallback_to_marker_only",
            "checks": checks,
            "reasons": decision["reasons"],
        }
    write_gate_report(generator_name, "visual_generation_allowed", decision["reasons"], checks)
    return {
        "shouldStop": False,
        "ok": True,
        "action": "visual_generation_allowed",
        "checks": checks,
        "reasons": decision["reasons"],
    }


def enforce_marker_fallback(generator_name: str) -> bool:
    """Return True when caller should stop because marker fallback was selected."""
    return run_gate(generator_name)["shouldStop"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator-name", default="manual_gate_check")
    args = parser.parse_args()
    result = run_gate(args.generator_name)
    print(f"Generator safety gate {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
