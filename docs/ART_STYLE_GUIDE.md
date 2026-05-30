# Art Style Guide — *The Mechanics of Government*

This guide locks the visual target so AI-generated assets stay coherent across hundreds of
generations. Every prompt in `tools/asset-pipeline/prompts/` builds on the shared
`style_prefix.txt`, and `postprocess.py` enforces the palette and sizing rules below.

## 1. Visual target: HD-2D-lite

We are building **HD-2D** (the Octopath Traveler / Triangle Strategy / DQ3-remake look):
2D sprites and props standing on a tilted 3D world, with depth, soft lighting and bloom.

Because the game ships to **web + mobile**, we use an **HD-2D-lite** profile that keeps the look
but stays cheap to render:

| Element | Full HD-2D (desktop) | HD-2D-lite (web/mobile, our target) |
| --- | --- | --- |
| Camera | Perspective, shallow tilt | Near-orthographic, ~30° tilt, fixed |
| Ground | Real 3D meshes + PBR | Flat/low-poly planes with **tileable textures** |
| Sprites | High-res billboards | Billboards, capped resolution, alpha-cut |
| Lighting | Real-time + DoF + heavy bloom | **Baked** light, light bloom, **no real-time DoF on mobile** |
| Shadows | Real-time | Blob/baked shadows |

**Implication for assets:** the pipeline must emit (a) **seamless tileable ground textures**,
(b) **alpha-cut billboard** props and characters, and (c) optional **normal maps** for cheap
fake lighting. Sprites are lit neutrally (flat front light) so baked scene light reads correctly.

## 2. Camera & projection (so props match the ground angle)

- Tilt: **~30° from top-down** (a 2:1.7-ish foreshortening). Generate props/structures as if
  viewed from this angle — *not* pure side view, *not* pure top-down.
- Sun direction: **upper-left**, soft. Keep it consistent so baked-in shading agrees scene-wide.

## 3. Resolution & sizing

| Asset class | Native gen size | Final asset size | Notes |
| --- | --- | --- | --- |
| Ground/terrain tile | 1024² | **256² or 512²**, seamless | Power-of-two; tiles edge-to-edge |
| Nature prop (tree, rock) | 1024² | trim to content, **≤512** tall | Alpha background |
| Structure / office "castle" | 1024² | trim to content, **≤1024** tall | Alpha background, billboard |
| Character walk sheet | per-frame 512² | **48–64 px** per frame after downscale | 4 dir × 3–4 frames |
| Portrait | 1024² | **512²** | Dialogue bust |
| UI panel / frame | as needed | 9-slice friendly | Parchment + gold filigree |

Final downscale uses **nearest-neighbour** to preserve crisp pixel edges. Power-of-two output
keeps GPU/web texture upload happy.

## 4. Palette

The world reads as an **aged cartographer's atlas brought to life** — the source map's parchment,
sepia inks and gold leaf. Three regional palette moods, all sharing the parchment/gold UI layer:

- **cold** (north / seas): desaturated blues, slate greys, cold white snow, pale teal water.
- **neutral** (central / vale / west): mossy greens, warm greys, weathered stone.
- **warm** (the Reach): wheat gold, olive, terracotta roofs.
- **hot** (Dorne): sand, ochre, dusty rose, sun-bleached stone.

`postprocess.py --palette <mood>` quantizes each asset toward the matching `.gpl`/JSON palette so
nothing drifts off-model. Define the master palettes in `tools/asset-pipeline/palettes/` (start by
sampling colours directly from `assets/source/world_map.png`).

UI layer is constant everywhere: **parchment cream `#e8d8b0`**, **ink brown `#3a2c1a`**,
**gold filigree `#c9a227`**.

## 5. Required models / nodes (install on the GPU box)

| Purpose | Asset | Where |
| --- | --- | --- |
| Base checkpoint | SDXL 1.0 base (or an SDXL anime/painterly merge) | `models/checkpoints/` |
| Pixel/painterly LoRA | **Pixel Art XL** (`pixel-art-xl.safetensors`) | `models/loras/` |
| Alt pixel LoRA | **Z Image Turbo pixel-art** LoRA | `models/loras/` |
| Sprite sheets | **SD_PixelArt_SpriteSheet_Generator** checkpoint | `models/checkpoints/` |
| Seamless tiles | `ComfyUI-seamless-tiling` (spinagon) custom node | `custom_nodes/` |
| Sprite consistency | ControlNet (OpenPose) + IP-Adapter models | `models/controlnet/`, `models/ipadapter/` |

> Filenames in the workflow JSONs are placeholders — after installing, re-export each workflow
> from your ComfyUI via **File → Export (API Format)** if node IDs differ, or just fix the
> `ckpt_name` / `lora_name` strings.

## 6. Consistency rules (non-negotiable)

1. Every prompt starts with the contents of `prompts/style_prefix.txt`.
2. One **fixed seed per asset family** (set in `generate.py`); only vary it deliberately.
3. Characters are generated **one direction/frame at a time** off a single **IP-Adapter reference
   image** (the master concept frame) — there is no reliable one-prompt full-sheet generator yet.
4. Always finish with a **human cleanup pass** (palette snap in `postprocess.py`, then manual
   touch-up in Aseprite/LibreSprite/Pixelorama) before an asset is considered "final".
