# World Map — from atlas to overworld

The source image (`assets/source/world_map.png`) is a Westeros-style cartographer's map reskinned
as **"The Offices of the Department of War."** We treat it as the game's **overworld**: every
labelled castle is a visitable **office node**, and the painted terrain becomes traversable
**biomes**. The machine-readable version lives in [`data/offices.json`](../data/offices.json).

## Office → location key

| Map location | Office | Org role | Tier |
| --- | --- | --- | --- |
| King's Landing | **SecWar** | Office of the Secretary of War | capital (hub) |
| Red Keep | WHLO | War HQ Liaison Office | sub-capital |
| Winterfell | OSW P&R | Personnel & Readiness | major office |
| The Dreadfort | OSW I&S | Intelligence & Security | major office |
| The Eyrie | OSW CAPE | Cost Assessment & Program Evaluation | major office |
| Raventree Hall | OSW CIO | Chief Information Officer | major office |
| Harrenhal | ODAM | Director of Administration & Management | major office |
| Casterly Rock | OSW COMP | Comptroller | major office |
| The Twins | Joint Staff | The Joint Staff | major office |
| Highgarden | OSW A&S | Acquisition & Sustainment | major office |
| Oldtown | OSW R&E | Research & Engineering | major office |
| Dragonstone | SecAF | Department of the Air Force | service secretariat |
| The Arbor | SecNav | Department of the Navy | service secretariat |
| Horn Hill | Sec Army | Department of the Army | service secretariat |
| The Wall / Castle Black | Frontier Command | Frontier outpost | outpost |

## Biomes (drive terrain/tile generation)

- **The Frozen Expanse** — snow/ice, far north (The Wall).
- **Northern Woods** — boreal forest around Winterfell/Dreadfort.
- **The Neck** — marsh/wetland band (Moat Cailin).
- **The Riverlands** — rivers + green plains (Twins, Raventree, Harrenhal).
- **The Westerlands** — rocky hills + gold cliffs (Casterly Rock).
- **The Vale** — high mountains (The Eyrie).
- **The Crownlands** — central grass/coast (King's Landing).
- **The Reach** — farmland + gardens (Highgarden, Oldtown, Horn Hill).
- **Dorne** — southern desert sand.
- **The Seas** — Shivering Sea, Glimmering Sea, Narrow Channel (water + islands: Dragonstone, The Arbor, Pyke/Iron Islands).

## How the map is used

1. `slice_map.py` cuts the source map into **per-region reference crops** (used as IP-Adapter /
   img2img references so generated tiles & structures match the atlas style) and produces a
   **grid-overlay preview** for laying out the playable tile grid.
2. `data/offices.json` `map_position` (normalized 0–1) gives each office a spot on the overworld
   so the future Godot scene can place town nodes without re-deriving them.
3. Biome polygons are authored later in **Tiled** (imported to Godot via YATI) using the sliced
   reference crops as a tracing guide — the AI generates the *tiles*, Tiled paints *where* they go.

## Suggested early gameplay framing (optional, for later passes)

A "new analyst" travels from office to office learning what each does — a literal walkable org
chart. SecWar (King's Landing) is the hub; service secretariats (Army/Navy/Air Force) are island
or border destinations. This is narrative context only; not part of this asset-pipeline deliverable.
