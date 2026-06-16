# Layer Combination Grammar Summary

- Generated: 2026-06-16T08:20:32+00:00
- Grammar rules discovered/curated: 6
- Generator rules derived: 11

## Discovered Grammar Rules

### walkable_ground

- Name: walkable ground or floor
- Collision: walkable unless Back has Water=T or another special intrinsic property
- Confidence: 95
- Validator checks: Back tile approved or intrinsic metadata-backed, Buildings empty, AlwaysFront not used for collision

### blocking_structure

- Name: blocking structure or object
- Collision: blocked by Buildings layer
- Confidence: 90
- Validator checks: Buildings profile approved for blocking, Back beneath is valid, tile 946 is not used as Buildings/blocker

### wall_with_overhead_top

- Name: wall or building with front/overhead top
- Collision: blocked by Buildings; Front/AlwaysFront are draw layers
- Confidence: 88
- Validator checks: Buildings body has matching approved Front/AlwaysFront top when style requires it, top tile allowed on Front/AlwaysFront

### canopy_overlay

- Name: canopy or roof overlay
- Collision: AlwaysFront does not create collision; collision comes from Buildings or Back metadata.
- Confidence: 85
- Validator checks: AlwaysFront tile has overlay profile, no collision assigned to AlwaysFront profile, tile 946 remains overlay-only until separately approved

### water

- Name: water or special liquid base
- Collision: blocked_or_special unless explicit passability exists
- Confidence: 90
- Validator checks: Water tile must carry Water=T or approved water profile, water edge transitions must be approved before production output

### technical_path

- Name: technical path or route data
- Collision: technical route data, not visual collision
- Confidence: 82
- Validator checks: Paths layer does not replace Back visual base, entrance/exit path markers do not block routes

## Output Readiness

- Rules ready for marker-only output: 11
- Rules ready for production output now: 0
- Rules blocked by missing approved structural tiles: 11

Production output remains blocked until stylepacks have approved structural roles for wall bodies, wall tops, corners, edges, transitions, canopy overlays, shadows, path transitions, and water edges.
