# GitHub Mine/Dungeon Export Summary

- Branch pushed: `mine-dungeon-focus-cleanup`
- Initial export commit hash: `22be66a`
- Remote: `https://github.com/joelhjert-tech/Stardewmapgenerator.git`
- PR created: no
- PR creation reason: `gh` is not installed in this shell
- Manual PR URL: `https://github.com/joelhjert-tech/Stardewmapgenerator/pull/new/mine-dungeon-focus-cleanup`

## Included

- Mine/dungeon generator scripts
- Smart Edge-Wrapper v2
- Mine/Dungeon Visual Canon v1
- Joel approval importer and review pack
- Fresh mine/dungeon template metadata
- Joel-approved building-block metadata
- Joel-authored run metadata
- Mine/dungeon validators
- Prototype metadata and validation reports only
- Latest mine/dungeon reports
- Focused docs and safety policy

## Excluded

- `mission_assets`
- unpacked basegame files
- vanilla `.tbin`, `.xnb`, tilesheet `.png`, rendered preview `.png`
- original Moonvillage source maps
- third-party repo clones
- raw scan folders
- broad/non-mine generator docs and older experiments

## Validation

- Export JSON parse: PASS
- Export Python compile: PASS
- Import smoke check: PASS
- Export smoke unit tests: PASS
- Asset/preview-dependent validators: skipped honestly because assets and rendered previews are intentionally excluded

## Forbidden File Scan

PASS. No forbidden source assets, rendered previews, raw scans, binaries, or third-party repo clones were staged.

## Next Step

Open a PR from `mine-dungeon-focus-cleanup` into `main`, then review whether the export should include any additional non-asset support schemas for repo-local validators.
