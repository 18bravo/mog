"""Post-process raw ComfyUI output into game-ready assets.

Steps (each optional via flags):
  * background removal (alpha cutout) for billboards/sprites  -- needs `rembg`
  * trim to content bounding box
  * palette quantization toward a fixed game palette          -- snaps colours on-model
  * nearest-neighbour downscale to the final asset size       -- crisp pixel edges

Usage:
  python postprocess.py in.png --out out.png --size 512 --palette cold
  python postprocess.py raw.png --out tree.png --cutout --trim --size 384

Requires Pillow. `--cutout` additionally requires `rembg` (pip install rembg).
Palettes are JSON files of "#rrggbb" lists in ./palettes/<name>.json (optional).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PALETTE_DIR = Path(__file__).resolve().parent / "palettes"


def _pil():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is required: pip install pillow")
    return Image


def cutout(img):
    """Make the background transparent. Prefer rembg (subject segmentation);
    fall back to a white-background keyer that needs no extra dependency."""
    try:
        from rembg import remove
        return remove(img)
    except Exception as e:  # not installed, or model/runtime failure
        print(f"  (rembg unavailable: {e}; using white-key fallback)")
        return white_key(img)


def white_key(img, thresh=40):
    """Flood-fill near-white from the four corners and make it transparent.
    Flooding from the edges preserves white *inside* the figure (collars, etc).
    Works only when the subject sits on a clean light background."""
    Image = _pil()
    from PIL import ImageDraw

    rgb = img.convert("RGB")
    w, h = rgb.size
    sentinel = (255, 0, 255)
    flood = rgb.copy()
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if sum(flood.getpixel(corner)) > 600:  # only seed on a light corner
            ImageDraw.floodfill(flood, corner, sentinel, thresh=thresh)

    out = img.convert("RGBA")
    fpx, opx = flood.load(), out.load()
    for y in range(h):
        for x in range(w):
            if fpx[x, y] == sentinel:
                opx[x, y] = (0, 0, 0, 0)
    return out


def trim(img):
    """Crop to the alpha (or colour) bounding box."""
    bbox = img.getchannel("A").getbbox() if "A" in img.getbands() else img.getbbox()
    return img.crop(bbox) if bbox else img


def load_palette(name: str):
    path = PALETTE_DIR / f"{name}.json"
    if not path.exists():
        sys.exit(
            f"palette '{name}' not found at {path}.\n"
            "Create it as a JSON list of hex colours, e.g. [\"#1b2a4a\", \"#e8d8b0\"]."
        )
    hexes = json.loads(path.read_text(encoding="utf-8"))
    flat = []
    for hx in hexes:
        hx = hx.lstrip("#")
        flat += [int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)]
    return flat


def quantize(img, palette_flat):
    Image = _pil()
    pal_img = Image.new("P", (1, 1))
    padded = palette_flat + [0] * (768 - len(palette_flat))
    pal_img.putpalette(padded)
    rgb = img.convert("RGB").quantize(palette=pal_img, dither=Image.Dither.NONE)
    out = rgb.convert("RGBA")
    if "A" in img.getbands():
        out.putalpha(img.getchannel("A"))
    return out


def downscale(img, size: int):
    Image = _pil()
    w, h = img.size
    scale = size / max(w, h)
    new = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(new, Image.Resampling.NEAREST)


def process(args) -> int:
    Image = _pil()
    img = Image.open(args.infile).convert("RGBA")
    if args.cutout:
        img = cutout(img)
    if args.trim:
        img = trim(img)
    if args.palette:
        img = quantize(img, load_palette(args.palette))
    if args.size:
        img = downscale(img, args.size)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  ({img.size[0]}x{img.size[1]})")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Post-process generated assets")
    p.add_argument("infile")
    p.add_argument("--out", required=True)
    p.add_argument("--cutout", action="store_true", help="remove background (rembg)")
    p.add_argument("--trim", action="store_true", help="crop to content bbox")
    p.add_argument("--palette", help="palette name in ./palettes/<name>.json")
    p.add_argument("--size", type=int, help="downscale longest edge to N px (nearest)")
    return process(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
