# Mine/Dungeon Pipeline

Current pipeline:

```text
local reference maps
-> fresh relearn
-> visual canon
-> building block extraction
-> Joel review sheets
-> derived locked approved blocks
-> Smart Edge-Wrapper v2
-> prototype output
-> validators
```

Current state:

- 144 Joel-approved core blocks exist in the derived locked library.
- Floor blocks are still pending approval.
- Marker fallback remains active.
- Custom maps are prototype-only.
- `Smart Edge-Wrapper v2` can optionally read the visual canon with `--template-source visual-canon-v1`, but only `Joel_approved`, `generator_ready`, and `locked` templates are loaded.
