"""Slice the source overworld map into reference crops + a grid-overlay preview.

The atlas at ``assets/source/world_map.png`` is the game's overworld. This tool:

1. Cuts it into an N x M grid of reference crops (``assets/source/regions/``) that you
   feed to img2img / IP-Adapter so generated tiles & structures match the atlas style.
2. Writes a grid-overlay preview (``assets/source/world_map_grid.png``) so you can lay
   out the playable tile grid and read off office positions.
3. Optionally crops a tight reference image around each office in ``data/offices.json``
   using its normalized ``map_position`` (``assets/source/offices/<id>.png``).

Usage:
    python slice_map.py --rows 8 --cols 6
    python slice_map.py --offices --pad 0.05

Requires Pillow (``pip install pillow``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO / "assets" / "source" / "world_map.png"
OFFICES = REPO / "data" / "offices.json"


def _require_pillow():
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        sys.exit("Pillow is required: pip install pillow")
    from PIL import Image, ImageDraw

    return Image, ImageDraw


def slice_grid(src: Path, rows: int, cols: int) -> Path:
    Image, ImageDraw = _require_pillow()
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    out_dir = src.parent / "regions"
    out_dir.mkdir(parents=True, exist_ok=True)

    cell_w, cell_h = w // cols, h // rows
    count = 0
    for r in range(rows):
        for c in range(cols):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
            img.crop(box).save(out_dir / f"region_r{r:02d}_c{c:02d}.png")
            count += 1
    print(f"  wrote {count} region crops -> {out_dir}")

    # grid-overlay preview
    preview = img.copy()
    draw = ImageDraw.Draw(preview)
    for c in range(1, cols):
        draw.line([(c * cell_w, 0), (c * cell_w, h)], fill=(200, 30, 30, 200), width=3)
    for r in range(1, rows):
        draw.line([(0, r * cell_h), (w, r * cell_h)], fill=(200, 30, 30, 200), width=3)
    preview_path = src.parent / "world_map_grid.png"
    preview.convert("RGB").save(preview_path)
    print(f"  wrote grid overlay -> {preview_path}")
    return preview_path


def crop_offices(src: Path, pad: float) -> int:
    Image, _ = _require_pillow()
    if not OFFICES.exists():
        sys.exit(f"missing {OFFICES}")
    data = json.loads(OFFICES.read_text(encoding="utf-8"))
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    out_dir = src.parent / "offices"
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    half = pad
    for office in data.get("offices", []):
        pos = office.get("map_position")
        if not pos:
            continue
        cx, cy = pos["x"] * w, pos["y"] * h
        box = (
            max(0, int(cx - half * w)),
            max(0, int(cy - half * h)),
            min(w, int(cx + half * w)),
            min(h, int(cy + half * h)),
        )
        img.crop(box).save(out_dir / f"{office['id']}.png")
        n += 1
    print(f"  wrote {n} office reference crops -> {out_dir}")
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Slice the overworld map")
    p.add_argument("--src", default=str(DEFAULT_SRC))
    p.add_argument("--rows", type=int, default=8)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--offices", action="store_true", help="also crop around each office")
    p.add_argument("--pad", type=float, default=0.05, help="office crop half-size (fraction)")
    args = p.parse_args(argv)

    src = Path(args.src)
    if not src.exists():
        sys.exit(
            f"Source map not found: {src}\n"
            "Drop the atlas image at assets/source/world_map.png and re-run."
        )

    print(f"Slicing {src} ({args.rows}x{args.cols}) ...")
    slice_grid(src, args.rows, args.cols)
    if args.offices:
        crop_offices(src, args.pad)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
