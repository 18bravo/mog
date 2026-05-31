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
    """Normalized (x, y) in 0..1 for a front-facing standing figure."""
    return {
        NOSE: (0.50, 0.10), NECK: (0.50, 0.18),
        RSHO: (0.41, 0.20), LSHO: (0.59, 0.20),
        RELB: (0.38, 0.33), LELB: (0.62, 0.33),
        RWRI: (0.37, 0.45), LWRI: (0.63, 0.45),
        RHIP: (0.45, 0.52), LHIP: (0.55, 0.52),
        RKNE: (0.45, 0.70), LKNE: (0.55, 0.70),
        RANK: (0.45, 0.92), LANK: (0.55, 0.92),
        REYE: (0.47, 0.085), LEYE: (0.53, 0.085),
        REAR: (0.44, 0.10), LEAR: (0.56, 0.10),
    }


def _front_walk(step):
    """step=+1 -> right leg forward/up, left back; step=-1 -> mirror."""
    p = _base_front()
    s = step
    # legs swing: forward leg knee/ankle raised + forward, back leg extended
    p[RKNE] = (0.46, 0.68 - 0.03 * s); p[RANK] = (0.47, 0.88 - 0.05 * s)
    p[LKNE] = (0.54, 0.68 + 0.03 * s); p[LANK] = (0.53, 0.88 + 0.05 * s)
    # arms counter-swing
    p[RELB] = (0.39, 0.33 + 0.02 * s); p[RWRI] = (0.40, 0.45 + 0.03 * s)
    p[LELB] = (0.61, 0.33 - 0.02 * s); p[LWRI] = (0.60, 0.45 - 0.03 * s)
    return p


POSES = {
    "front_idle": _base_front(),
    "front_walk1": _front_walk(+1),
    "front_walk2": _front_walk(-1),
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
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
