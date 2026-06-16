# Layer Grammar Validator Design

- Generated: 2026-06-16T08:20:32+00:00

## Future Checks

- Reject illegal Back/Buildings/Front/AlwaysFront combinations that do not appear in vanilla grammar or approved Moonvillage exceptions.
- Reject unapproved wall stacks where Buildings has no approved blocking/body profile.
- Reject AlwaysFront as a collision source; collision must come from Buildings or intrinsic Back metadata.
- Warn on Buildings without valid Back beneath it unless explicitly approved as a special technical map.
- Require Water=T or approved water profile for production water tiles.
- Keep tile 946 quarantined from Buildings, wall body, blocker, collision, and wall base roles.
- Check entrance and exit paths against blocking Buildings stacks.
- Require style-defined top/front overlays for wall bodies when the stylepack says those are mandatory.
- Reject stylepack tile roles that refer to unapproved final tile IDs while marker fallback is required.

## Implementation Path

1. Load `layer_combination_grammar.json` and `generator_layer_rules_from_vanilla.json`.
2. Validate generated semantic stacks before tile resolution.
3. Validate resolved tile stacks after tile resolution.
4. Fail production output on any unresolved structural marker or unapproved tile profile.
