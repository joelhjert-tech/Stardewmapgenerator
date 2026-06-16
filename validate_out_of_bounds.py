#!/usr/bin/env python3
"""
validate_out_of_bounds.py

Out-of-bounds / "can the player leave" failsafe for generated Moonvillage maps.

Inspired by the SMAPI mod "Can The Player Leave" (pneuma163, Nexus 28257), which
flood-fills the player-reachable walkable region and reports any tile where the
player can walk OFF the map in an unintended way (a walkable map-edge tile that is
not a declared warp/door), plus unreachable walkable pockets.

This is the INVERSE of validate_marker_map.py's entrance->exit connectivity check:
  - connectivity proves the player CAN reach the exit;
  - this proves the player CANNOT reach anywhere they shouldn't (off-map / dead pockets).

Read-only. Operates on the semantic/marker map (.semantic.json) today; the
walkable-grid builder is isolated so a TMX/TMJ builder can be added later using
collision truth (Buildings-layer occupancy + Passable property + Water + approved
profiles), exactly as the reference mod derives collision.

Exit code 0 = no unexpected escapes; 1 = problems found (use as a hard gate).
"""
from __future__ import annotations
import json, sys, argparse
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MAP = ROOT / "generated_maps" / "marker_tests" / "outdoor" / "marker_test_map.semantic.json"
REPORT = ROOT / "reports" / "out_of_bounds_validation_report.md"

# Roles a player can stand on / walk through. Anything NOT listed is treated as
# blocking (fail-safe default: unknown roles block, so a missing role can never be
# silently treated as walkable and open an escape).
PASSABLE_ROLES = {
    "marker_ground", "marker_cave_floor", "marker_path", "marker_entrance", "marker_exit",
    "marker_ladder", "marker_treasure", "marker_monster_spawn", "marker_ore_spawn", "marker_forage_spawn",
    "marker_decoration_zone", "marker_protected",
}
BLOCKING_ROLES = {
    "marker_wall", "marker_rock_wall", "marker_cave_wall", "marker_wall_top", "marker_wall_body", "marker_corner",
    "marker_edge", "marker_transition", "marker_blocked", "marker_water",
    "marker_overlay",
}
KNOWN_ROLES = PASSABLE_ROLES | BLOCKING_ROLES
# Roles that are legitimate openings on the map edge (intended exits/warps).
EXIT_ROLES = {"marker_entrance", "marker_exit"}


def walkable_grid_from_semantic(data: dict):
    """Return (cells, width, height, walkable_fn, exit_set, entrance_set)."""
    cells = data.get("cells") or data.get("rows")
    if not cells:
        raise ValueError("semantic map has no 'cells'/'rows' grid")
    height = len(cells)
    width = max(len(r) for r in cells)
    exits, entrances = set(), set()
    for y, row in enumerate(cells):
        for x, role in enumerate(row):
            if role == "marker_exit":
                exits.add((x, y))
            elif role == "marker_entrance":
                entrances.add((x, y))

    def is_walkable(x, y):
        if not (0 <= y < len(cells) and 0 <= x < len(cells[y])):
            return False
        return cells[y][x] in PASSABLE_ROLES

    return cells, width, height, is_walkable, exits, entrances


def neighbors4(x, y):
    yield x + 1, y
    yield x - 1, y
    yield x, y + 1
    yield x, y - 1


def flood(seeds, is_walkable, width, height):
    seen = set()
    q = deque(s for s in seeds if is_walkable(*s))
    seen.update(q)
    while q:
        x, y = q.popleft()
        for nx, ny in neighbors4(x, y):
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen and is_walkable(nx, ny):
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def check_out_of_bounds(data: dict) -> dict:
    cells, width, height, is_walkable, exits, entrances = walkable_grid_from_semantic(data)
    intended = exits | entrances

    # All walkable tiles.
    all_walkable = {(x, y) for y in range(len(cells)) for x in range(len(cells[y])) if is_walkable(x, y)}
    unknown_roles = [
        {"x": x, "y": y, "role": role}
        for y, row in enumerate(cells)
        for x, role in enumerate(row)
        if role not in KNOWN_ROLES
    ]
    unknown_roles.sort(key=lambda item: (item["y"], item["x"], item["role"]))

    # Player-reachable region: flood from entrances (fallback: exits, then any walkable).
    seeds = entrances or exits or (sorted(all_walkable)[:1])
    reachable = flood(seeds, is_walkable, width, height)

    def on_edge(x, y):
        return x == 0 or y == 0 or x == width - 1 or y == height - 1

    # 1) Out-of-bounds escapes: a REACHABLE walkable edge tile that is not an intended exit.
    escapes = sorted(
        (x, y) for (x, y) in reachable if on_edge(x, y) and (x, y) not in intended
    )
    # 2) Unreachable walkable pockets (dead space the player can never use; also a sign
    #    of a sealed escape that only LOOKS contained).
    unreachable = sorted(all_walkable - reachable)
    # 3) Declared exits the player cannot actually reach.
    unreachable_exits = sorted(exits - reachable)
    # 4) Edge openings with no exit role even if unreachable (latent escapes if walls shift).
    latent_edge_walkable = sorted(
        (x, y) for (x, y) in all_walkable if on_edge(x, y) and (x, y) not in intended and (x, y) not in reachable
    )

    return {
        "width": width, "height": height,
        "walkableTiles": len(all_walkable),
        "reachableTiles": len(reachable),
        "entrances": sorted(entrances),
        "exits": sorted(exits),
        "intendedExitTiles": sorted(intended),
        "outOfBoundsEscapes": escapes,
        "unreachableWalkablePockets": unreachable,
        "unreachableDeclaredExits": unreachable_exits,
        "latentEdgeWalkable": latent_edge_walkable,
        "unknownRoles": unknown_roles,
    }


def errors_and_warnings(result: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if result["unknownRoles"]:
        errors.append(
            f"{len(result['unknownRoles'])} cell(s) use unknown passability roles; "
            f"examples: {result['unknownRoles'][:10]}."
        )
    if result["outOfBoundsEscapes"]:
        sample = result["outOfBoundsEscapes"][:10]
        errors.append(
            f"Player can walk off the map at {len(result['outOfBoundsEscapes'])} edge tile(s) "
            f"with no exit role (e.g. {sample})."
        )
    if result["unreachableDeclaredExits"]:
        errors.append(
            f"{len(result['unreachableDeclaredExits'])} declared exit(s) are not reachable "
            f"from the entrance: {result['unreachableDeclaredExits'][:10]}."
        )
    if result["unreachableWalkablePockets"]:
        errors.append(
            f"{len(result['unreachableWalkablePockets'])} walkable tile(s) are unreachable "
            f"(dead pockets): e.g. {result['unreachableWalkablePockets'][:10]}."
        )
    if result["latentEdgeWalkable"]:
        warnings.append(
            f"{len(result['latentEdgeWalkable'])} edge tile(s) are walkable but currently "
            f"unreachable; they would become escapes if walls shift."
        )
    return errors, warnings


def write_report(map_name: str, r: dict, errors: list[str], warnings: list[str]):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Out-of-Bounds Validation Report",
        "",
        f"- Map: `{map_name}`",
        f"- Size: {r['width']}x{r['height']} | walkable: {r['walkableTiles']} | player-reachable: {r['reachableTiles']}",
        f"- Result: {'PASS' if not errors else 'FAIL'} | errors: {len(errors)} | warnings: {len(warnings)}",
        "",
        "## Inspired by",
        "`Can The Player Leave` (Nexus 28257): flood-fill the reachable region; flag any",
        "walkable map-edge tile that is not an intended warp/door, plus unreachable pockets.",
        "",
        "## Checks",
        f"- Out-of-bounds escapes (reachable edge tiles without an exit role): {len(r['outOfBoundsEscapes'])}",
        f"- Unreachable walkable pockets: {len(r['unreachableWalkablePockets'])}",
        f"- Unreachable declared exits: {len(r['unreachableDeclaredExits'])}",
        f"- Unknown passability roles: {len(r['unknownRoles'])}",
        f"- Latent edge-walkable (currently unreachable, would escape if walls shift): {len(r['latentEdgeWalkable'])}",
        "",
    ]
    if errors:
        lines.append("## Errors")
        lines += [f"- {e}" for e in errors]
        lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines += [f"- {w}" for w in warnings]
        lines.append("")
    if not errors and not warnings:
        lines.append("There is no unexpected way for the player to get out of bounds.")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", nargs="?", default=str(DEFAULT_MAP),
                    help="path to a *.semantic.json generated map")
    args = ap.parse_args()
    path = Path(args.map)
    if not path.exists():
        print(f"Out-of-bounds validation FAIL: map not found: {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    r = check_out_of_bounds(data)
    errors, warnings = errors_and_warnings(r)

    write_report(data.get("mapName", path.stem), r, errors, warnings)
    verdict = "PASS" if not errors else "FAIL"
    print(f"Out-of-bounds validation {verdict}; escapes={len(r['outOfBoundsEscapes'])}; "
          f"unreachableExits={len(r['unreachableDeclaredExits'])}; "
          f"deadPockets={len(r['unreachableWalkablePockets'])}; warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
