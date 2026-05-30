"""CI-safe sanity checks for the asset pipeline — no GPU, no server, stdlib only.

Validates:
  * every workflow in workflows/ is well-formed ComfyUI API-format and exposes the
    node titles the pipeline overrides (POSITIVE, NEGATIVE, SAMPLER, LATENT, SAVE);
  * data/offices.json parses, every office.biome references a defined biome, and ids
    are unique;
  * every distinct biome terrain has a matching prompts/terrain/<terrain>.txt.

Exit code 0 = all good, 1 = problems found.

    python validate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORKFLOWS = HERE / "workflows"
PROMPTS = HERE / "prompts"
DATA = REPO / "data" / "offices.json"

REQUIRED_TITLES = {"POSITIVE", "NEGATIVE", "SAMPLER", "LATENT", "SAVE"}


def _titles(wf: dict) -> set:
    return {
        str(n.get("_meta", {}).get("title", "")).upper()
        for n in wf.values()
        if isinstance(n, dict)
    }


def check_workflows(errors: list) -> None:
    files = sorted(WORKFLOWS.glob("*.json"))
    if not files:
        errors.append("no workflows found in workflows/")
        return
    for f in files:
        try:
            wf = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{f.name}: invalid JSON: {e}")
            continue
        if not isinstance(wf, dict) or not wf:
            errors.append(f"{f.name}: not a non-empty API-format object")
            continue
        for nid, node in wf.items():
            if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
                errors.append(f"{f.name}: node {nid} missing class_type/inputs")
        missing = REQUIRED_TITLES - _titles(wf)
        if missing:
            errors.append(f"{f.name}: missing node titles: {sorted(missing)}")
        else:
            print(f"  ok  {f.name}  ({len(wf)} nodes)")


def check_model(errors: list) -> None:
    if not DATA.exists():
        errors.append(f"missing {DATA}")
        return
    try:
        model = json.loads(DATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"offices.json: invalid JSON: {e}")
        return

    biome_ids = {b["id"] for b in model.get("biomes", [])}
    terrains = {b["terrain"] for b in model.get("biomes", [])}
    ids = [o["id"] for o in model.get("offices", [])]
    if len(ids) != len(set(ids)):
        errors.append("offices.json: duplicate office ids")
    for o in model.get("offices", []):
        if o.get("biome") not in biome_ids:
            errors.append(f"office {o['id']}: unknown biome '{o.get('biome')}'")
    cap = model.get("world", {}).get("capital")
    if cap and cap not in set(ids):
        errors.append(f"world.capital '{cap}' is not an office id")
    print(f"  ok  offices.json  ({len(ids)} offices, {len(biome_ids)} biomes)")

    for t in sorted(terrains):
        if not (PROMPTS / "terrain" / f"{t}.txt").exists():
            errors.append(f"missing prompt for terrain '{t}' (prompts/terrain/{t}.txt)")


def main() -> int:
    errors: list = []
    print("Checking workflows...")
    check_workflows(errors)
    print("Checking world model + prompts...")
    check_model(errors)

    if errors:
        print(f"\nFAILED with {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
