"""Build a character walk sheet with ControlNet OpenPose.

Two modes:

  sheet  (default) -- generate ALL frames in ONE wide image in a single pass,
                      driven by a combined multi-pose skeleton
                      (poses/sheet_front_walk.png), then slice into equal cells.
                      Single-pass generation keeps the character consistent
                      across frames "for free" (the model paints them together).
                      ControlNet runs only for the first ~25% of steps
                      (end_percent in the workflow) so it sets the pose without
                      breaking limbs.

  frames -- legacy: one generation per pose, re-posed with a locked seed. Higher
            per-frame control but drifts between frames; kept as a fallback.

    python sprite_sheet.py player                 # one-pass sheet (recommended)
    python sprite_sheet.py player --mode frames    # legacy per-frame
    python sprite_sheet.py office_lead --seed 1234

Needs ComfyUI with the OpenPose-SDXL ControlNet
(models/controlnet/openpose-sdxl.safetensors) and the pose images
(run make_poses.py first). Pillow required; rembg optional (white-key fallback).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POSES = HERE / "poses"
PROMPTS = HERE / "prompts"
WF = HERE / "workflows" / "controlnet_pose.json"
SHEET_FRAMES = 4                          # cells per direction skeleton
# facing phrase injected into the prompt per direction (skeleton sets the walk,
# the prompt sets which way the character faces)
FACING = {
    "front": "seen from the front, facing the camera, face visible",
    "back":  "seen from behind, facing away from the camera, back of the head visible, no face",
    "left":  "side profile view facing left, walking to the left",
    "right": "side profile view facing right, walking to the right",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _prompts():
    style = _read(PROMPTS / "character_style.txt")
    negative = (_read(PROMPTS / "negative.txt") + ", multiple characters, extra items, "
                "icons, bags, weapon, sword, staff, gun, rifle, holding object")
    return style, negative


def slice_sheet(img, n):
    """Split a wide image into n equal-width cells, trim+cut each."""
    import postprocess
    w, h = img.size
    cw = w // n
    out = []
    for i in range(n):
        cell = img.crop((i * cw, 0, (i + 1) * cw, h))
        out.append(postprocess.trim(postprocess.cutout(cell)))
    return out


def pack_strip(frames, out_png: Path, cell=512, pad=4):
    """Bottom-align equal-size cells into one horizontal strip + JSON sidecar."""
    import postprocess
    from PIL import Image

    frames = [postprocess.downscale(f, cell) for f in frames]
    cw = max(f.width for f in frames) + pad * 2
    ch = max(f.height for f in frames) + pad * 2
    sheet = Image.new("RGBA", (cw * len(frames), ch), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        x = i * cw + (cw - f.width) // 2          # center horizontally
        y = ch - pad - f.height                    # bottom-align (feet on a line)
        sheet.paste(f, (x, y), f)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_png)
    meta = {"frame_width": cw, "frame_height": ch, "frames": len(frames),
            "layout": "horizontal", "image": out_png.name}
    out_png.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return cw, ch


def build_sheet_mode(args, client, load_workflow, set_input, postprocess):
    """One wide generation driven by the combined skeleton, then slice."""
    from PIL import Image

    pose_img = POSES / f"sheet_{args.direction}_walk.png"
    if not pose_img.exists():
        sys.exit(f"missing {pose_img} -- run make_poses.py first")
    style, negative = _prompts()
    desc = _read(PROMPTS / "characters" / f"{args.character}.txt")
    facing = FACING[args.direction]
    # tell the model it's a row of frames of the SAME character, facing one way
    positive = (f"{style}, {desc}, {facing}, character walk cycle sprite sheet, "
                f"a row of {SHEET_FRAMES} frames of the same identical character walking, "
                "consistent outfit and colors across all frames, evenly spaced, white background")
    if args.direction == "back":
        negative = negative + ", face, facing camera, front view"

    w, h = args.width * SHEET_FRAMES, args.height
    pose_server = client.upload_image(pose_img)
    wf = load_workflow(WF)
    set_input(wf, "POSE", "image", pose_server)
    set_input(wf, "LATENT", "width", w)
    set_input(wf, "LATENT", "height", h)
    client.set_text(wf, "POSITIVE", positive)
    client.set_text(wf, "NEGATIVE", negative)
    client.set_seed(wf, args.seed)

    raw_dir = REPO / "assets" / "sprites" / args.character / "_sheet"
    print(f">>> single-pass sheet [{args.direction}]  {w}x{h}  ({SHEET_FRAMES} frames)")
    saved = client.generate(wf, str(raw_dir), f"sheet_{args.direction}")
    if not saved:
        sys.exit("no output from ComfyUI")
    frames = slice_sheet(Image.open(saved[0]), SHEET_FRAMES)
    print(f"    sliced into {len(frames)} frames")
    return frames


def build_frames_mode(args, client, load_workflow, set_input, postprocess):
    """Legacy: one generation per pose with a locked seed."""
    from PIL import Image

    style, negative = _prompts()
    desc = _read(PROMPTS / "characters" / f"{args.character}.txt")
    positive = f"{style}, {desc}, {FACING[args.direction]}"
    seq = ["front_idle", "front_walk1", "front_idle", "front_walk2"]
    raw_dir = REPO / "assets" / "sprites" / args.character / "_frames"
    frames = []
    for i, pose in enumerate(seq):
        if not (POSES / f"{pose}.png").exists():
            sys.exit(f"missing pose '{pose}.png' -- run make_poses.py first")
        print(f">>> frame {i+1}/{len(seq)} pose={pose}")
        pose_server = client.upload_image(POSES / f"{pose}.png")
        wf = load_workflow(WF)
        set_input(wf, "POSE", "image", pose_server)
        set_input(wf, "LATENT", "width", args.width)
        set_input(wf, "LATENT", "height", args.height)
        client.set_text(wf, "POSITIVE", positive)
        client.set_text(wf, "NEGATIVE", negative)
        client.set_seed(wf, args.seed)
        saved = client.generate(wf, str(raw_dir), f"{i:02d}_{pose}")
        if not saved:
            print("    ! no output"); continue
        frames.append(postprocess.trim(postprocess.cutout(Image.open(saved[0]))))
    return frames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a character walk sheet via ControlNet")
    ap.add_argument("character", help="name of a prompts/characters/<name>.txt")
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--mode", choices=["sheet", "frames"], default="sheet")
    ap.add_argument("--direction", default="front",
                    choices=["front", "back", "left", "right", "all"],
                    help="facing to generate ('all' = all four for a full overworld character)")
    ap.add_argument("--seed", type=int, default=3030)
    ap.add_argument("--width", type=int, default=512, help="per-frame width")
    ap.add_argument("--height", type=int, default=768, help="per-frame height")
    ap.add_argument("--cell", type=int, default=512, help="final cell height (downscale)")
    args = ap.parse_args(argv)

    if not (PROMPTS / "characters" / f"{args.character}.txt").exists():
        sys.exit(f"no character prompt: prompts/characters/{args.character}.txt")

    sys.path.insert(0, str(HERE))
    from comfy_client import ComfyClient, load_workflow, set_input
    import postprocess

    client = ComfyClient(args.server)
    builder = build_sheet_mode if args.mode == "sheet" else build_frames_mode
    directions = ["front", "back", "left", "right"] if args.direction == "all" else [args.direction]

    for d in directions:
        args.direction = d
        frames = builder(args, client, load_workflow, set_input, postprocess)
        if not frames:
            print(f"  ! no frames for {d}; skipping"); continue
        out = REPO / "assets" / "sprites" / f"{args.character}__walk_{d}.png"
        cw, ch = pack_strip(frames, out, cell=args.cell)
        print(f"wrote sheet {out.relative_to(REPO)}  ({len(frames)} frames, cell {cw}x{ch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
