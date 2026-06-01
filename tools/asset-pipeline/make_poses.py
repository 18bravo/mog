"""Generate OpenPose skeleton images to drive ControlNet for sprite frames.

ControlNet-OpenPose reads a skeleton image (colored limbs + joint dots on black)
and forces the generated character into that pose. We use it to author a
consistent walk cycle: the same character, posed frame by frame.

Note on facings: an OpenPose skeleton encodes *limb positions*, not which way a
character faces (front vs back look nearly identical). So we use the skeleton for
the walk-cycle leg/arm motion and let the prompt set the facing
(front / back / left / right). This script emits a front-facing idle + a 2-step
front walk by default; pass --all for side/back stubs too.

    python make_poses.py            # poses/front_idle, front_walk1, front_walk2
    python make_poses.py --all

Output: tools/asset-pipeline/poses/*.png  (default 512x768, black background)
Requires Pillow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "poses"

# COCO-18 keypoint indices
NOSE, NECK, RSHO, RELB, RWRI, LSHO, LELB, LWRI, RHIP, RKNE, RANK, LHIP, LKNE, LANK, REYE, LEYE, REAR, LEAR = range(18)

# Standard OpenPose limb connections + colors (BGR-ish RGB used by ControlNet annotators)
LIMBS = [
    (NECK, RSHO), (NECK, LSHO), (RSHO, RELB), (RELB, RWRI), (LSHO, LELB), (LELB, LWRI),
    (NECK, RHIP), (RHIP, RKNE), (RKNE, RANK), (NECK, LHIP), (LHIP, LKNE), (LKNE, LANK),
    (NECK, NOSE), (NOSE, REYE), (REYE, REAR), (NOSE, LEYE), (LEYE, LEAR),
]
LIMB_COLORS = [
    (153, 0, 0), (153, 51, 0), (153, 102, 0), (153, 153, 0), (102, 153, 0), (51, 153, 0),
    (0, 153, 0), (0, 153, 51), (0, 153, 102), (0, 153, 153), (0, 102, 153), (0, 51, 153),
    (0, 0, 153), (51, 0, 153), (102, 0, 153), (153, 0, 153), (153, 0, 102),
]
POINT_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
    (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85),
]


def _base_front():
    """Normalized (x, y) in 0..1 for a front-facing standing figure.
    Compact, heroic RPG proportions with headroom (figure spans ~0.12..0.86)."""
    return {
        NOSE: (0.50, 0.14), NECK: (0.50, 0.23),
        RSHO: (0.39, 0.25), LSHO: (0.61, 0.25),
        RELB: (0.35, 0.37), LELB: (0.65, 0.37),
        RWRI: (0.34, 0.49), LWRI: (0.66, 0.49),
        RHIP: (0.44, 0.53), LHIP: (0.56, 0.53),
        RKNE: (0.43, 0.69), LKNE: (0.57, 0.69),
        RANK: (0.43, 0.85), LANK: (0.57, 0.85),
        REYE: (0.47, 0.125), LEYE: (0.53, 0.125),
        REAR: (0.44, 0.14), LEAR: (0.56, 0.14),
    }


def _front_walk(step):
    """step=+1 -> right leg forward/up, left back; step=-1 -> mirror.
    Exaggerated stride so the animation reads clearly."""
    p = _base_front()
    s = step
    # legs swing forward/back with a clear raise on the forward leg
    p[RKNE] = (0.46, 0.66 - 0.04 * s); p[RANK] = (0.48, 0.84 - 0.07 * s)
    p[LKNE] = (0.54, 0.66 + 0.04 * s); p[LANK] = (0.52, 0.84 + 0.07 * s)
    # arms counter-swing, kept close to the body (avoids 'holding something' look)
    p[RELB] = (0.37, 0.37 + 0.02 * s); p[RWRI] = (0.38, 0.49 + 0.03 * s)
    p[LELB] = (0.63, 0.37 - 0.02 * s); p[LWRI] = (0.62, 0.49 - 0.03 * s)
    return p


def _side_walk(step):
    """Profile (side) walk: legs scissor front/back along x, arms swing along x.
    step=+1 / -1 are the two stride extremes; step=0 is a near-idle."""
    p = _base_front()
    s = step
    # narrow the torso/shoulders toward a profile read
    p[RSHO] = (0.48, 0.25); p[LSHO] = (0.52, 0.25)
    p[NOSE] = (0.53, 0.14); p[REYE] = (0.55, 0.125); p[LEYE] = (0.52, 0.125)
    p[REAR] = (0.49, 0.14); p[LEAR] = (0.49, 0.14)
    p[RHIP] = (0.49, 0.53); p[LHIP] = (0.51, 0.53)
    # legs scissor horizontally (one forward, one back)
    p[RKNE] = (0.49 + 0.06 * s, 0.69); p[RANK] = (0.49 + 0.10 * s, 0.85)
    p[LKNE] = (0.51 - 0.06 * s, 0.69); p[LANK] = (0.51 - 0.10 * s, 0.85)
    # arms swing opposite to legs
    p[RELB] = (0.50 - 0.05 * s, 0.37); p[RWRI] = (0.50 - 0.08 * s, 0.49)
    p[LELB] = (0.50 + 0.05 * s, 0.37); p[LWRI] = (0.50 + 0.08 * s, 0.49)
    return p


POSES = {
    "front_idle": _base_front(),
    "front_walk1": _front_walk(+1),
    "front_walk2": _front_walk(-1),
    # back uses the same skeleton shapes as front (facing is set by the prompt)
    "back_idle": _base_front(),
    "back_walk1": _front_walk(+1),
    "back_walk2": _front_walk(-1),
    # side profile (used for both left and right; right is mirrored at compose time)
    "side_idle": _side_walk(0),
    "side_walk1": _side_walk(+1),
    "side_walk2": _side_walk(-1),
}

# Which pose names make up each direction's 4-frame walk sheet.
DIRECTION_SEQ = {
    "front": ["front_idle", "front_walk1", "front_idle", "front_walk2"],
    "back":  ["back_idle", "back_walk1", "back_idle", "back_walk2"],
    "left":  ["side_idle", "side_walk1", "side_idle", "side_walk2"],
    "right": ["side_idle", "side_walk1", "side_idle", "side_walk2"],  # mirrored on compose
}


def draw_pose(coords, w, h):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    px = {k: (v[0] * w, v[1] * h) for k, v in coords.items()}
    lw = max(2, int(h * 0.012))
    r = max(2, int(h * 0.009))
    for (a, b), col in zip(LIMBS, LIMB_COLORS):
        if a in px and b in px:
            d.line([px[a], px[b]], fill=col, width=lw)
    for k, (x, y) in px.items():
        d.ellipse([x - r, y - r, x + r, y + r], fill=POINT_COLORS[k])
    return img


def compose_sheet(names, cw, ch, mirror=False):
    """Lay the named pose skeletons side by side on one black canvas.
    mirror=True flips each cell horizontally (turns a left profile into right)."""
    from PIL import Image
    sheet = Image.new("RGB", (cw * len(names), ch), (0, 0, 0))
    for i, name in enumerate(names):
        cell = draw_pose(POSES[name], cw, ch)
        if mirror:
            cell = cell.transpose(Image.FLIP_LEFT_RIGHT)
        sheet.paste(cell, (i * cw, 0))
    return sheet


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate OpenPose skeletons")
    p.add_argument("--width", type=int, default=512)
    p.add_argument("--height", type=int, default=768)
    p.add_argument("--all", action="store_true", help="(reserved) also emit side/back stubs")
    args = p.parse_args(argv)

    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Pillow is required: pip install pillow")

    OUT.mkdir(parents=True, exist_ok=True)
    for name, coords in POSES.items():
        img = draw_pose(coords, args.width, args.height)
        img.save(OUT / f"{name}.png")
        print(f"  wrote {OUT.name}/{name}.png")

    # Combined walk-sheet skeleton per direction: all four frames in ONE wide
    # image so the character can be generated in a single pass (consistency for
    # free). 'right' reuses the side skeletons mirrored.
    for direction, seq in DIRECTION_SEQ.items():
        sheet = compose_sheet(seq, args.width, args.height, mirror=(direction == "right"))
        path = OUT / f"sheet_{direction}_walk.png"
        sheet.save(path)
        print(f"  wrote {OUT.name}/{path.name} ({sheet.size[0]}x{sheet.size[1]}, {len(seq)} cells)")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
