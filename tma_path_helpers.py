#!/usr/bin/env python3
"""Shared path helpers for Tiled Map Assistant tools."""

from __future__ import annotations

import json
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = TOOL_ROOT / "config"


def resolve_vanilla_authoritative_index(tool_root: Path | None = None) -> dict:
    """Resolve the vanilla authoritative index without duplicating it."""
    root = tool_root or TOOL_ROOT
    expected = root / "database" / "vanilla_authoritative_index.json"
    fallback = root / "review" / "auto_resolution" / "vanilla_authoritative_index.json"
    candidates = [expected, fallback]
    actual = next((path for path in candidates if path.exists()), None)
    return {
        "expectedPath": str(expected),
        "fallbackPaths": [str(fallback)],
        "actualPath": str(actual) if actual else None,
        "exists": actual is not None,
        "usesCompatibilityCopy": actual == expected if actual else False,
        "needsCompatibilityCopy": False,
        "recommendedFuturePath": str(actual or fallback),
        "recommendation": (
            "Use the resolved path from config/asset_paths.json; do not duplicate the large index unless a future tool cannot accept a pointer."
            if actual
            else "Regenerate or restore vanilla_authoritative_index.json before metadata-dependent tools run."
        ),
    }


def write_asset_path_config(tool_root: Path | None = None) -> Path:
    root = tool_root or TOOL_ROOT
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    resolution = resolve_vanilla_authoritative_index(root)
    config = {
        "vanillaAuthoritativeIndex": resolution,
    }
    path = root / "config" / "asset_paths.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path

