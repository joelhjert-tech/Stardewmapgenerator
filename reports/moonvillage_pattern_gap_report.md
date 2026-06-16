# Moonvillage Pattern Gap Report

- Generated: 2026-06-16T08:20:32+00:00
- Moonvillage maps available: 58
- Moonvillage maps compared: 58
- Parse failures: 0
- Dangerous or unusual findings recorded: 47
- Tile 946 usage examples recorded: 109

## Where Moonvillage Follows Vanilla Grammar

- Common Back-only, Back+Buildings, Back+Front, and Back+Buildings+Front stacks can be compared directly to vanilla grammar.
- Layer density and stack reports are now available for generator tuning.

## Safe Differences

- Custom tilesheets can use vanilla-like layer stacks without being visually identical to vanilla.
- Unusual stacks are not automatically wrong; they are queued for review when they diverge from vanilla grammar.

## Dangerous Differences

- Any tile 946 use remains profile-specific and cannot be copied into wall/body/blocking generation.
- Buildings without Back, AlwaysFront without supporting lower layers, and Paths-only stacks are review-needed layer grammar. Vanilla has some sparse/edge-case uses of these stacks, so they are not automatic map bugs, but the generator must not copy them blindly.

## Stylepack Improvements Needed

- Add approved wall body, wall top, edge, corner, transition, canopy overlay, shadow, path transition, and water edge profiles.
- Keep marker fallback active until those structural profiles validate.

## Example Findings

- `53dba2565ee5_AnnetteHouse` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `59d65e1764aa_AnnetteHousebundlecomplete` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `bc96184509f3_AnnetteHouseInside` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual, tile 946 appears and must remain profile-specific/quarantined from blocking roles
- `d223c45a587f_CustomMoonvillage` from `MainMoonvillage-git`: tile 946 appears and must remain profile-specific/quarantined from blocking roles
- `789111fe2f0a_herbhouse` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `5e92dfbbdf09_Hotspringremake` from `MainMoonvillage-git`: tile 946 appears and must remain profile-specific/quarantined from blocking roles
- `8a7a8f6ea8f0_innfloor2` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `e4e31d550150_innfloor3` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `e10b67bc13a9_innfloor3_decorated` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `dd5eb238f29b_innsecretbasement` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual, tile 946 appears and must remain profile-specific/quarantined from blocking roles
- `426a33bf0496_Moongranary` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual
- `761676d20c3b_Moongrocery` from `MainMoonvillage-git`: contains layer stacks that vanilla grammar treats as risky or unusual, tile 946 appears and must remain profile-specific/quarantined from blocking roles
