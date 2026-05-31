"""Batch asset generator for *The Mechanics of Government*.

Reads the world model (`data/offices.json`), the prompt fragments (`prompts/`) and the
ComfyUI workflows (`workflows/`), then plans + (optionally) generates every game asset,
runs post-processing, and writes `assets/manifest.json`.

It is safe to run with `--dry-run` on any machine (no GPU, no server, no deps beyond the
standard library): it prints the full job plan and writes the manifest with
status="planned". A real run requires a reachable ComfyUI and `pip install -r requirements.txt`.

Examples:
    python generate.py --dry-run                 # plan everything, write manifest
    python generate.py --only terrain            # generate just terrain (needs ComfyUI)
    python generate.py --only structures props   # several classes
    python generate.py --server 127.0.0.1:8188   # full run
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = REPO / "data" / "offices.json"
PROMPTS = HERE / "prompts"
WORKFLOWS = HERE / "workflows"
ASSETS = REPO / "assets"
MANIFEST = ASSETS / "manifest.json"

# one fixed seed per asset family keeps a coherent look (ART_STYLE_GUIDE §6)
SEEDS = {"terrain": 42, "structures": 1010, "props": 2020, "sprites": 3030, "portraits": 4040}

CLASSES = ["terrain", "structures", "props", "sprites", "portraits"]


@dataclass
class Job:
    id: str
    cls: str
    workflow: str
    positive: str
    negative: str
    seed: int
    size: List[int]
    out_path: str
    subject: str = ""
    biome: str = ""
    palette: Optional[str] = "neutral"  # None = skip palette-snap (keep raw colours)
    cutout: bool = False
    trim: bool = False
    final_size: Optional[int] = None
    prompt_file: str = ""
    status: str = "planned"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _prompt(style: str, fragment: str) -> str:
    return f"{style}, {fragment}".replace("\n", " ").strip(", ")


def build_jobs(model: dict, classes: List[str]) -> List[Job]:
    style = _read(PROMPTS / "style_prefix.txt")
    negative = _read(PROMPTS / "negative.txt")
    # Terrain tiles need a *flat, straight-down* framing -- the shared 30-degree
    # "Octopath" prefix makes ground read as a vertical wall, so terrain gets its
    # own style + a negative that explicitly rejects walls/bricks/buildings.
    terrain_style = _read(PROMPTS / "terrain_style.txt")
    terrain_negative = negative + ", " + _read(PROMPTS / "terrain_negative.txt")
    biome_palette = {b["id"]: b.get("palette", "neutral") for b in model["biomes"]}
    jobs: List[Job] = []

    # ---- terrain: one per distinct biome terrain type ----
    if "terrain" in classes:
        seen = {}
        for b in model["biomes"]:
            seen.setdefault(b["terrain"], b)
        for terrain, b in sorted(seen.items()):
            pf = PROMPTS / "terrain" / f"{terrain}.txt"
            if not pf.exists():
                print(f"  ! no prompt for terrain '{terrain}' ({pf.name}); skipping")
                continue
            jobs.append(Job(
                id=f"terrain/{terrain}__flat__001", cls="terrain",
                workflow="terrain_tile_seamless.json",
                positive=_prompt(terrain_style, _read(pf)), negative=terrain_negative,
                seed=SEEDS["terrain"], size=[1024, 1024],
                out_path=f"assets/terrain/{terrain}__flat__001.png",
                subject=terrain, biome=b["id"], palette=None,
                final_size=512, prompt_file=str(pf.relative_to(HERE)),
            ))

    # ---- structures: one per office, styled from its fields ----
    if "structures" in classes:
        for o in model["offices"]:
            frag = (f"a {o['structure'].replace('_', ' ')} fantasy castle, "
                    f"home of {o['role']}, {o.get('notes', '')}, "
                    f"isolated on plain flat background, billboard sprite")
            jobs.append(Job(
                id=f"structures/{o['id']}__billboard__001", cls="structures",
                workflow="prop_billboard.json",
                positive=_prompt(style, frag), negative=_read(PROMPTS / "negative.txt"),
                seed=SEEDS["structures"], size=[1024, 1024],
                out_path=f"assets/structures/{o['id']}__billboard__001.png",
                subject=o["structure"], biome=o["biome"],
                palette=biome_palette.get(o["biome"], "neutral"),
                cutout=True, trim=True, final_size=1024,
            ))

    # ---- props: one per file in prompts/props ----
    if "props" in classes:
        for pf in sorted((PROMPTS / "props").glob("*.txt")):
            name = pf.stem
            jobs.append(Job(
                id=f"props/{name}__var__001", cls="props",
                workflow="prop_billboard.json",
                positive=_prompt(style, _read(pf)), negative=negative,
                seed=SEEDS["props"], size=[1024, 1024],
                out_path=f"assets/props/{name}__var__001.png",
                subject=name, cutout=True, trim=True, final_size=384,
                prompt_file=str(pf.relative_to(HERE)),
            ))

    # ---- sprites: one front frame per character (see consistency note below) ----
    if "sprites" in classes:
        for pf in sorted((PROMPTS / "characters").glob("*.txt")):
            name = pf.stem
            jobs.append(Job(
                id=f"sprites/{name}__front__001", cls="sprites",
                workflow="character_spritesheet.json",
                positive=_prompt("PixelartFSS", _read(pf)), negative=negative,
                seed=SEEDS["sprites"], size=[512, 512],
                out_path=f"assets/sprites/{name}__front__001.png",
                subject=name, cutout=True, trim=True, final_size=64,
                prompt_file=str(pf.relative_to(HERE)),
            ))

    # ---- portraits: one per office lead ----
    if "portraits" in classes:
        lead = _read(PROMPTS / "characters" / "office_lead.txt")
        for o in model["offices"]:
            frag = f"{lead}, leader of {o['role']}"
            jobs.append(Job(
                id=f"portraits/{o['id']}_lead__neutral", cls="portraits",
                workflow="portrait.json",
                positive=_prompt(style, frag), negative=negative,
                seed=SEEDS["portraits"], size=[1024, 1024],
                out_path=f"assets/portraits/{o['id']}_lead__neutral.png",
                subject=o["id"], biome=o["biome"], final_size=512,
            ))

    return jobs


def run_job(job: Job, client, postprocess, seed: int = None, variant: int = 1) -> None:
    from comfy_client import load_workflow

    use_seed = job.seed if seed is None else seed
    wf = load_workflow(WORKFLOWS / job.workflow)
    client.set_text(wf, "POSITIVE", job.positive)
    client.set_text(wf, "NEGATIVE", job.negative)
    client.set_seed(wf, use_seed)
    client.set_size(wf, job.size[0], job.size[1])

    # variant N -> filename suffix __NNN (replacing the planned __001)
    base_out = Path(REPO / job.out_path)
    stem = base_out.stem.rsplit("__", 1)[0] if base_out.stem.endswith("001") else base_out.stem
    out = base_out.with_name(f"{stem}__{variant:03d}{base_out.suffix}")
    raw_dir = out.parent / "_raw"
    raw = client.generate(wf, str(raw_dir), out.stem)
    if not raw:
        job.status = "error:no-output"
        return
    src = raw[0]

    # post-process into the final asset
    from types import SimpleNamespace
    has_palette = bool(job.palette) and (PROMPTS.parent / "palettes" / f"{job.palette}.json").exists()
    args = SimpleNamespace(
        infile=str(src),
        out=str(out),
        cutout=job.cutout,
        trim=job.trim,
        palette=job.palette if has_palette else None,
        size=job.final_size,
    )
    try:
        postprocess.process(args)
        job.status = "generated"
    except BaseException as e:  # SystemExit (missing dep) or any postprocess error
        # Never lose the work: fall back to the raw render as the final tile,
        # but surface the real reason so we can fix the postprocess step.
        import traceback
        print(f"  ! postprocess failed for {job.id}; keeping raw. Reason: {e!r}")
        traceback.print_exc()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src.read_bytes())
        job.status = "generated:raw"


def write_manifest(jobs: List[Job]) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    entries = []
    for j in jobs:
        e = asdict(j)
        e["seamless"] = j.cls == "terrain"
        entries.append(e)
    MANIFEST.write_text(json.dumps({"assets": entries}, indent=2), encoding="utf-8")
    print(f"\nwrote manifest with {len(entries)} entries -> {MANIFEST.relative_to(REPO)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate MoG game assets")
    p.add_argument("--only", nargs="*", choices=CLASSES, help="limit to these classes")
    p.add_argument("--server", default="127.0.0.1:8188")
    p.add_argument("--variants", type=int, default=1, metavar="N",
                   help="render N seed-varied versions of each asset (__001.._00N) to cherry-pick")
    p.add_argument("--dry-run", action="store_true", help="plan + write manifest, no generation")
    args = p.parse_args(argv)

    if not DATA.exists():
        sys.exit(f"missing world model: {DATA}")
    model = json.loads(DATA.read_text(encoding="utf-8"))
    classes = args.only or CLASSES
    jobs = build_jobs(model, classes)

    print(f"Planned {len(jobs)} job(s) across: {', '.join(classes)}")
    for j in jobs:
        print(f"  [{j.cls:10}] {j.id}")

    if args.dry_run:
        write_manifest(jobs)
        print("\n[dry-run] no images generated.")
        return 0

    sys.path.insert(0, str(HERE))
    from comfy_client import ComfyClient
    import postprocess

    client = ComfyClient(args.server)
    failures = total = 0
    for j in jobs:
        for v in range(1, args.variants + 1):
            total += 1
            label = j.id if args.variants == 1 else f"{j.id} (variant {v}/{args.variants})"
            print(f"\n>>> {label}")
            try:
                # vary the seed per variant so each render differs
                run_job(j, client, postprocess, seed=j.seed + (v - 1) * 1000, variant=v)
            except Exception as e:
                j.status = f"error: {e}"
                failures += 1
            print(f"    {j.status}")
    write_manifest(jobs)
    print(f"\nDone: {total - failures} ok, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
