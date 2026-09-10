# Results

## Phase 1: 2D simulator

Protocol: `scripts/phase1_controls.sh`. Three launches per pilot with gust seeds 0, 1, 2.
The rocket is a two-stage sounding rocket with destabilising aerodynamics; an unsteered
one falls over about 20 s after liftoff. Guidance target is straight up. Score is the
apoapsis at burnout (radial vis-viva), so the ceiling is set by the vehicle, not the sky.

| Pilot | Sees | Outcomes | Median apoapsis | Median max altitude | Median mean pitch error |
| --- | --- | --- | --- | --- | --- |
| Hands off | nothing | tumble ×3 | 6.6 km | 3.0 km | 9.6° |
| Random stick | nothing | tumble ×3 | 5.2 km | 2.4 km | 15.8° |
| **Fly, live plasticity** | panel | **burnout ×3** | **781 km** | **79.1 km** | **6.7°** |
| Fly, frozen weights | panel | burnout ×3 | 781 km | 79.1 km | 6.7° |
| Fly, blind | black | tumble ×3 | 3.9 km | 1.7 km | 21.7° |
| PD autopilot | telemetry | burnout ×3 | 832 km | 80.3 km | 0.4° |
| Panel autopilot | panel, perfect eye | burnout ×3 | 832 km | 80.3 km | 0.4° |

What this does and does not show:

- **The connectome steers the rocket.** With the calibrated `DNp20`/`DNpe017` readout
  the fly reaches burnout on every seed and leaves the atmosphere; every pilot without
  a working stick falls over. The fly holds attitude to within about ±10° in a slow
  oscillation (its stick is a smoothed, single-cell-per-side signal with 300 ms of lag).
- **It is the wiring, not learning.** Live and frozen runs are identical to the last
  digit. The reward and aversive currents were delivered (556 and 539 pulses in the first
  live flight) and the dopamine cells fired, but no Kenyon cell fired, so no plastic
  synapse could change. See [calibration.md](calibration.md).
- **Blind is worse than hands-off.** With no needle, the decoder reads only the noisy
  dark baseline of two single cells and wiggles the stick, which is slightly worse than
  leaving it alone. This is the right control for "does the panel matter": it does.
- **The instrument does not limit the fly.** Read perfectly, the same panel flies as well
  as direct telemetry. The 50 km gap between the fly and the autopilots is the fly.

Per-tick telemetry, commands, spike counts, and hashes for every flight are in
`runs/*/episode-*.jsonl` (not committed).
