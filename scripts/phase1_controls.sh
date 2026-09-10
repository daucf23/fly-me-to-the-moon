#!/usr/bin/env bash
# Phase 1 protocol: the fly against every baseline that gives its number meaning.
# Same gust seeds (0, 1, 2) for every pilot. Results land in runs/*/episodes.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
EPISODES="${EPISODES:-3}"

uv run flybywire calibrate --record-ms 2000 --out runs/calibration.json > /dev/null

for pilot in none random autopilot panel-autopilot; do
  uv run flybywire launch --pilot "$pilot" --episodes "$EPISODES" --run-dir "runs/sim-$pilot" --fresh
done
uv run flybywire launch --pilot fly --episodes "$EPISODES" --run-dir runs/sim-fly --fresh
uv run flybywire launch --pilot fly --episodes "$EPISODES" --run-dir runs/sim-fly-frozen --frozen --fresh
uv run flybywire launch --pilot fly --episodes "$EPISODES" --run-dir runs/sim-fly-black --input black --fresh

uv run python scripts/summarize.py runs/sim-*
