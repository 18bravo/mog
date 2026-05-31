#!/usr/bin/env bash
#
# One-command asset runner for The Mechanics of Government.
#
#   ./go.sh <class> [variants]
#
# Examples:
#   ./go.sh terrain 3      # pull latest, render terrain with 3 variants each, commit + push
#   ./go.sh structures     # render the office castles (1 variant)
#   ./go.sh props 2
#
# It runs ON YOUR MAC (where ComfyUI + the GPU live). Start ComfyUI first
# (python main.py in the ComfyUI folder, serving http://127.0.0.1:8188).
#
set -uo pipefail

BRANCH="claude/retro-rpg-map-design-QREqr"
CLASS="${1:-terrain}"
VARIANTS="${2:-1}"
SERVER="${COMFY_SERVER:-127.0.0.1:8188}"

cd "$(dirname "$0")" || exit 1

valid="terrain structures props sprites portraits"
case " $valid " in
  *" $CLASS "*) ;;
  *) echo "Unknown class '$CLASS'. Choose one of: $valid"; exit 2 ;;
esac

echo "==> [1/5] Syncing code with remote ($BRANCH)..."
git fetch origin "$BRANCH" --quiet || { echo "git fetch failed"; exit 1; }
# Reset code to match remote. Generated images are untracked and survive this;
# this is the reliable way past the 'divergent branches' pull error.
git reset --hard "origin/$BRANCH" --quiet

echo "==> [2/5] Activating Python venv..."
if [ ! -d .venv ]; then
  echo "    creating .venv ..."
  python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet pillow requests websocket-client
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> [3/5] Checking ComfyUI at $SERVER ..."
if ! curl -sf "http://$SERVER/system_stats" >/dev/null 2>&1; then
  echo "    !! ComfyUI not reachable at http://$SERVER"
  echo "    Start it first: (in your ComfyUI folder) python main.py"
  exit 1
fi

echo "==> [4/5] Generating '$CLASS' x$VARIANTS variant(s)..."
python tools/asset-pipeline/generate.py --only "$CLASS" --variants "$VARIANTS" --server "$SERVER"
gen_rc=$?

echo "==> [5/5] Committing + pushing results..."
git add -f "assets/$CLASS" assets/manifest.json
if git diff --cached --quiet; then
  echo "    nothing new to commit."
else
  git commit --quiet -m "$CLASS assets (${VARIANTS}x variants)"
  for i in 1 2 3 4; do
    if git push origin "$BRANCH"; then break; fi
    echo "    push retry $i ..."; sleep $((2 ** i))
  done
fi

echo ""
if [ "$gen_rc" -eq 0 ]; then
  echo "Done. Generated $CLASS assets are in assets/$CLASS/ and pushed."
else
  echo "Done with some generation failures (rc=$gen_rc) -- whatever rendered was pushed."
fi
echo "Tell Claude it's pushed so it can review."
