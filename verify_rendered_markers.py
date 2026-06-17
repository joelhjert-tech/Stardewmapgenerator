#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

TORCH_LOCAL_IDS = {48, 80}


def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_expected_torches(text: str | None) -> list[tuple[int, int]]:
    if not text:
        return []

    coords: list[tuple[int, int]] = []
    for part in text.replace(";", " ").split():
        x_s, y_s = part.split(",", 1)
        coords.append((int(x_s), int(y_s)))
    return coords


def torches_from_layout_json(path: str | Path) -> list[tuple[int, int]]:
    doc = read_json(path)
    markers = doc.get("specialMarkers") or doc.get("special_markers") or {}
    return [tuple(map(int, pair)) for pair in markers.get("torches", [])]


def tile_layer(tmj: dict, name: str) -> dict:
    for layer in tmj.get("layers", []):
        if layer.get("name") == name and layer.get("type") == "tilelayer":
            return layer
    raise ValueError(f"TMJ has no tile layer named {name!r}")


def local_id(gid: int | None) -> int | None:
    if gid is None or gid <= 0:
        return None
    return gid - 1


def check_torches(tmj_path: Path, expected: list[tuple[int, int]]) -> list[str]:
    tmj = read_json(tmj_path)
    width = int(tmj["width"])
    height = int(tmj["height"])
    front = tile_layer(tmj, "Front")
    data = front["data"]

    errors: list[str] = []

    if not expected:
        errors.append("expected torch list is empty; marker bridge may not be generating torches")
        return errors

    for x, y in expected:
        if not (0 <= x < width and 0 <= y < height):
            errors.append(f"torch coordinate {(x, y)} is out of bounds for {width}x{height}")
            continue

        idx = y * width + x
        actual = local_id(data[idx])

        if actual not in TORCH_LOCAL_IDS:
            errors.append(
                f"missing torch at {(x, y)}: expected Front local tile "
                f"{sorted(TORCH_LOCAL_IDS)}, got {actual}"
            )

    return errors


def check_authored_ladder(metadata_path: Path) -> list[str]:
    metadata = read_json(metadata_path)
    wrapper = metadata.get("freshTemplateWrapper", {})

    count = wrapper.get("ladderEntrancePlacements")
    placed_id = wrapper.get("ladderPlacedId")

    errors: list[str] = []

    if not count or int(count) < 1:
        errors.append(f"authored ladder entrance not reported as placed; ladderEntrancePlacements={count}")

    if not placed_id:
        errors.append("authored ladder entrance has no ladderPlacedId")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify rendered semantic markers survived into TMJ output.")
    parser.add_argument("--tmj", required=True, help="Rendered TMJ path.")
    parser.add_argument("--metadata", required=True, help="Rendered metadata.json path.")
    parser.add_argument("--layout-json", help="Semantic layout JSON containing specialMarkers.torches.")
    parser.add_argument(
        "--expected-torches",
        help='Manual expected torch list, e.g. "12,31 21,20 33,24 36,13 9,39".',
    )
    parser.add_argument("--require-authored-ladder", action="store_true")
    args = parser.parse_args()

    if args.layout_json:
        expected = torches_from_layout_json(args.layout_json)
    else:
        expected = parse_expected_torches(args.expected_torches)

    errors = check_torches(Path(args.tmj), expected)

    if args.require_authored_ladder:
        errors.extend(check_authored_ladder(Path(args.metadata)))

    if errors:
        print("FAIL: rendered marker verification failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS: rendered markers verified")
    print(f"- torches verified: {len(expected)}")
    if args.require_authored_ladder:
        print("- authored ladder entrance verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
