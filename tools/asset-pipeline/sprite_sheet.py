"""Build a character walk sheet with ControlNet OpenPose.

Runs ONE character through a sequence of pose skeletons (poses/*.png) using a
locked seed + character description so the same character is re-posed frame by
frame, then cuts each frame out, bottom-aligns them in equal cells and packs a
horizontal strip + a JSON sidecar the engine can read.

    python sprite_sheet.py player
    python sprite_sheet.py office_lead --seed 1234 --strength 0.9 \
        --poses front_idle front_walk1 front_idle front_walk2

Needs: ComfyUI running with the OpenPose-SDXL ControlNet installed
(models/controlnet/openpose-sdxl.safetensors) and the pose images present
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
DEFAULT_SEQ = ["front_idle", "front_walk1", "front_idle", "front_walk2"]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def pack_strip(frames, out_png: Path, pad: int = 4):
    """Bottom-align equal-size cells into one horizontal strip + JSON sidecar."""
    from PIL import Image

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a character walk sheet via ControlNet")
    ap.add_argument("character", help="name of a prompts/characters/<name>.txt")
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--seed", type=int, default=3030)
    ap.add_argument("--strength", type=float, default=0.85)
    ap.add_argument("--poses", nargs="*", default=DEFAULT_SEQ)
    ap.add_argument("--cell", type=int, default=512, help="downscale each frame to this tall")
    args = ap.parse_args(argv)

    char_file = PROMPTS / "characters" / f"{args.character}.txt"
    if not char_file.exists():
        sys.exit(f"no character prompt: {char_file}")
    for name in dict.fromkeys(args.poses):
        if not (POSES / f"{name}.png").exists():
            sys.exit(f"missing pose '{name}.png' -- run make_poses.py first")

    sys.path.insert(0, str(HERE))
    from comfy_client import ComfyClient, load_workflow, set_input
    import postprocess
    from PIL import Image

    style = _read(PROMPTS / "character_style.txt")
    desc = _read(char_file)
    positive = f"{style}, {desc}"
    negative = (_read(PROMPTS / "negative.txt") + ", multiple characters, extra items, icons, "
                "bags, weapon, sword, staff, gun, rifle, holding object, empty hands")

    client = ComfyClient(args.server)
    raw_dir = REPO / "assets" / "sprites" / args.character / "_frames"
    frames = []
    for i, pose in enumerate(args.poses):
        print(f">>> frame {i+1}/{len(args.poses)} pose={pose}")
        ref = client.upload_image(POSES / f"{pose}.png")
        wf = load_workflow(WF)
        set_input(wf, "POSE", "image", ref)
        set_input(wf, "CONTROL", "strength", args.strength)
        client.set_text(wf, "POSITIVE", positive)
        client.set_text(wf, "NEGATIVE", negative)
        client.set_seed(wf, args.seed)              # locked seed -> same character
        saved = client.generate(wf, str(raw_dir), f"{i:02d}_{pose}")
        if not saved:
            print("    ! no output"); continue
        img = Image.open(saved[0])
        img = postprocess.trim(postprocess.cutout(img))
        img = postprocess.downscale(img, args.cell)
        frames.append(img)
        print(f"    cut+trimmed -> {img.size}")

    if not frames:
        sys.exit("no frames produced")
    out = REPO / "assets" / "sprites" / f"{args.character}__walk_front.png"
    cw, ch = pack_strip(frames, out)
    print(f"\nwrote sheet {out.relative_to(REPO)}  ({len(frames)} frames, cell {cw}x{ch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
