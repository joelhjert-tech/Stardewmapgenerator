# Stardew Volcano Reference Notes

## What was inspected

- Local packed-content folder presence at `C:\Users\Joel_\Documents\Stardew Moonvillage\tools\tiled-map-assistant\mission_assets\packed`.
- Local Volcano layout reference folder presence at `C:\Users\Joel_\Documents\Stardew Moonvillage\tools\tiled-map-assistant\mission_assets\Content\VolcanoLayouts`.
- The Volcano layout folder contains a packed-layout metadata JSON and an associated PNG export. The JSON was inspected only to confirm it references a texture export; the texture data and image content were not copied or used as runtime input.

## Architecture ideas borrowed

- Treat authored or generated layout data as a semantic mask first, then compile markers separately.
- Keep route concepts such as gates, switches, and set-piece markers as metadata on top of the navigable floor mask.
- Preserve a staged generation shape: choose route/layout structure, compile markers, then let later renderer/post-pass layers consume the semantic output.
- Require route locks to be functional graph constraints, not decorative markers. A locked edge must be a graph bridge/cut edge so the gate side is unreachable until the edge is restored.

## What was deliberately not copied

- No Stardew Valley assets were copied.
- No `.xnb`, `.tbin`, `.png`, unpacked maps, or `mission_assets/` files were added to the repository.
- No production path depends on Stardew's shipped Volcano `Layouts.xnb`.
- The generator does not ingest the Volcano layout image or metadata as runtime input.

## Confirmation

This milestone uses the local Volcano files only as architecture reference. The implemented route-lock slice remains graph-first and procedural.
