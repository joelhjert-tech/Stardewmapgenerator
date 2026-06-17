# Setup

Use Python 3.11 or newer.

Install normal project dependencies locally as needed. Pillow is required for scripts that render local prototype previews.

This repo does not include Stardew Valley game assets, unpacked basegame maps, or Moonvillage source maps. The user must provide those locally.

Expected local-only asset folders, if you run asset-dependent scripts:

- `mission_assets/unpacked_basegame/`
- `mission_assets/unpacked_basegame/Mine/`
- `mission_assets/moonvillage/`

Do not commit those folders.

Useful checks that do not require committed game assets:

```powershell
python -m py_compile *.py
python validate_mine_visual_canon.py
python validate_mine_visual_canon.py --locked
```

Prototype generation is local-only and may require asset folders:

```powershell
python build_smart_edge_wrapper_v2.py --template-source visual-canon-v1
```

Do not commit:

- `mission_assets/`
- unpacked basegame files
- Moonvillage source maps
- `.xnb`, `.tbin`, game `.png` assets
- rendered prototype previews
- third-party repo clones
