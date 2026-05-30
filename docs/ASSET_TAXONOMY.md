# Asset Taxonomy & Naming

Every asset the pipeline emits is recorded in `assets/manifest.json` (generated). Files follow a
predictable, engine-agnostic naming scheme so the future Godot/Tiled project can ingest them
without renaming.

## Naming convention

```
<class>/<biome-or-subject>__<variant>__<NNN>.<ext>
```

- `class`   — one of: `terrain`, `props`, `structures`, `sprites`, `portraits`, `ui`
- lower_snake_case throughout; `__` separates fields; `NNN` is a zero-padded variant index.

Examples:
```
terrain/snow__flat__001.png
terrain/grass__path_edge__002.png
structures/winterfell__billboard__001.png
props/pine_tree__tall__003.png
sprites/player__walk_south.png          (packed 3–4 frame strip)
sprites/npc_p_and_r__walk_east.png
portraits/secwar_lead__neutral.png
ui/panel__parchment__9slice.png
```

## Classes

### 1. `terrain/` — seamless ground textures
One set per biome `terrain` value in `offices.json` (snow, forest_floor, hills, farmland, sand,
mountain, grass, river, marsh, water). Seamless, power-of-two (256²/512²). Optional `*_normal.png`.

### 2. `structures/` — the office "castles" (billboards)
One per office in `offices.json`, styled to its `structure` field and `biome` palette
(icy Winterfell, golden Casterly Rock, grand King's Landing capital, ruined Harrenhal, etc.).
Alpha-cut, generated at the ~30° HD-2D camera angle.

### 3. `props/` — nature & set dressing (billboards)
Trees (pine, broadleaf, dead weirwood), rocks, mountains, marsh reeds, banners, signposts.
Alpha-cut. Multiple variants each for visual variety.

### 4. `sprites/` — characters (4-direction walk)
Player + one NPC archetype per office (the "office lead" / clerk), optional "red-tape" enemies.
Each character: 4 directions × 3–4 frames, packed as strips. Generated one frame at a time off a
locked IP-Adapter reference (see ART_STYLE_GUIDE §6). Downscaled to 48–64 px/frame.

### 5. `portraits/` — dialogue busts
512² bust per office lead, parchment-framed in UI.

### 6. `ui/` — HUD & menus
Parchment panels, gold-filigree frames, scroll menus, map cartouche — matching the source map's
border. 9-slice friendly where possible.

## Manifest entry shape

```json
{
  "id": "terrain/snow__flat__001",
  "class": "terrain",
  "path": "assets/terrain/snow__flat__001.png",
  "subject": "snow",
  "biome": "frozen_expanse",
  "seamless": true,
  "size": [512, 512],
  "workflow": "terrain_tile_seamless.json",
  "prompt_file": "prompts/terrain/snow.txt",
  "seed": 42,
  "palette": "cold",
  "status": "generated"
}
```

`status` progresses `generated` → `cleaned` → `final` as the human cleanup pass happens.
