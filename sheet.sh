#!/usr/bin/env bash
#
# One-command walk-sheet builder (ControlNet OpenPose).
#
#   ./sheet.sh <character> [extra sprite_sheet.py args]
#
# Examples:
#   ./sheet.sh player
#   ./sheet.sh office_lead --seed 1234 --strength 0.9
#
# Runs ON YOUR MAC. Needs ComfyUI up with the OpenPose-SDXL ControlNet at
# models/controlnet/openpose-sdxl.safetensors.
#
set -uo pipefail

BRANCH="claude/retro-rpg-map-design-QREqr"
CHAR="${1:-player}"; shift || true
SERVER="${COMFY_SERVER:-127.0.0.1:8188}"
cd "$(dirname "$0")" || exit 1

echo "==> Syncing code..."
git fetch origin "$BRANCH" --quiet || { echo "fetch failed"; exit 1; }
git reset --hard "origin/$BRANCH" --quiet

if [ ! -d .venv ]; then
  python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet pillow requests websocket-client
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -c "import rembg" >/dev/null 2>&1 || pip install --quiet rembg onnxruntime || \
  echo "    (rembg unavailable; using white-key cutout)"

echo "==> Regenerating pose skeletons..."
python tools/asset-pipeline/make_poses.py >/dev/null

echo "==> Checking ComfyUI + ControlNet model..."
if ! curl -sf "http://$SERVER/system_stats" >/dev/null 2>&1; then
  echo "    !! ComfyUI not reachable at http://$SERVER -- start it (python main.py)"; exit 1
fi
if [ ! -f "$HOME/ComfyUI/models/controlnet/openpose-sdxl.safetensors" ]; then
  echo "    !! Missing models/controlnet/openpose-sdxl.safetensors -- download it first."; exit 1
fi

echo "==> Building walk sheet for '$CHAR'..."
python tools/asset-pipeline/sprite_sheet.py "$CHAR" --server "$SERVER" "$@"
rc=$?

echo "==> Committing + pushing..."
git add -f assets/sprites
if git diff --cached --quiet; then
  echo "    nothing new to commit."
else
  git commit --quiet -m "walk sheet: $CHAR"
  for i in 1 2 3 4; do git push origin "$BRANCH" && break || { echo "    push retry $i"; sleep $((2 ** i)); }; done
fi
echo ""
[ "$rc" -eq 0 ] && echo "Done. Sheet at assets/sprites/${CHAR}__walk_front.png -- tell Claude it's pushed." \
               || echo "Finished with errors (rc=$rc); see output above."
