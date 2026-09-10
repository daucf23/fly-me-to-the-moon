#!/usr/bin/env bash
# Phase 1 protocol: the fly against every baseline that gives its number meaning.
# Same gust seeds for every pilot. Decoder settings were tuned on seeds 0-1
# (scripts/sweep.py); this reports on held-out seeds starting at SEED=3.
# Results land in runs/*/episodes.jsonl. Fly conditions run in parallel.
set -euo pipefail
cd "$(dirname "$0")/.."
EPISODES="${EPISODES:-3}"
SEED="${SEED:-3}"

uv run flybywire calibrate --record-ms 2000 --out runs/calibration.json > /dev/null

common=(--episodes "$EPISODES" --seed "$SEED" --fresh)
for pilot in none random autopilot panel-autopilot; do
  uv run flybywire launch --pilot "$pilot" "${common[@]}" --run-dir "runs/sim-$pilot"
done
uv run flybywire launch --pilot autopilot "${common[@]}" --run-dir runs/sim-autopilot-gusty --gust-std 0.12
uv run flybywire launch --pilot autopilot "${common[@]}" --run-dir runs/sim-autopilot-orbit --vehicle orbital --gravity-turn

fly() { uv run flybywire launch --pilot fly "${common[@]}" "$@" > /dev/null; }
fly --run-dir runs/sim-fly &
fly --run-dir runs/sim-fly-frozen --frozen &
fly --run-dir runs/sim-fly-black --input black &
fly --run-dir runs/sim-fly-gusty --gust-std 0.12 &
fly --run-dir runs/sim-fly-orbit --vehicle orbital --gravity-turn &
fly --run-dir runs/sim-fly-legacy --steer-gain-hz 35 --steer-tau-ms 300 --error-scale-deg 10 &
wait

uv run python scripts/summarize.py runs/sim-*
