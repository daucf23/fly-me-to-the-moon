# Results

## Phase 1: 2D simulator

Protocol: `scripts/phase1_controls.sh`. Three launches per pilot with gust seeds 3, 4, 5
(held out: the decoder was tuned on seeds 0 and 1, see below). The rocket is a two-stage
sounding rocket with destabilising aerodynamics; an unsteered one falls over about 20 s
after liftoff. Guidance target is straight up unless stated. Score is the apoapsis of the
osculating orbit at burnout, so the ceiling is set by the vehicle, not the sky. Gravity is
central (the planet is round, pitch is measured from local vertical) so the orbit numbers
are real ones.

| Pilot | Sees | Outcomes | Median apoapsis | Median max altitude | Median mean steer error |
| --- | --- | --- | --- | --- | --- |
| Hands off | nothing | tumble ×3 | 6.1 km | 2.7 km | 11.0° |
| Random stick | nothing | tumble ×3 | 4.8 km | 2.1 km | 14.7° |
| **Fly, live plasticity** | panel | **burnout ×3** | **831.2 km** | **80.3 km** | **0.71°** |
| Fly, frozen weights | panel | burnout ×3 | 831.2 km | 80.3 km | 0.71° |
| Fly, blind | black | tumble ×3 | 6.6 km | 3.1 km | 15.4° |
| Fly, first-version decoder | panel | burnout ×3 | 770.4 km | 78.7 km | 7.43° |
| PD autopilot | telemetry | burnout ×3 | 831.6 km | 80.3 km | 0.35° |
| Panel autopilot | panel, perfect eye | burnout ×3 | 831.7 km | 80.3 km | 0.32° |

Robustness, same seeds:

| Condition | Fly | PD autopilot |
| --- | --- | --- |
| Gust torque doubled (`--gust-std 0.12`) | 829.2 km, 1.43° | 831.1 km, 0.70° |

### To orbit

The sounding rocket cannot orbit whatever the pilot does (best profile: periapsis −167 km).
`--vehicle orbital` swaps in a 550 kg upper stage with a long, gentle burn (4.2 km/s in
total); `--gravity-turn` follows a profile found by sweeping start/end altitude and final
pitch with the autopilot: vertical to 1 km, then pitch linearly with altitude to 105° at
80 km, i.e. the nose ends 15° below the horizon so burnout lands near apoapsis. There is
no coast or circularisation burn, because the fly has no throttle, so the orbit is whatever
the vehicle has at burnout, and "orbit" means both apsides above 70 km on a bound
trajectory. The fly's needle now tracks a target that moves through 105° of pitch.

| Pilot, seeds 3–5 | Outcomes | Periapsis × apoapsis (median) | Mean steer error |
| --- | --- | --- | --- |
| **Fly** | **orbit ×3** | **89.1 × 964 km** | **0.81°** |
| PD autopilot | orbit ×3 | 89.6 × 1025 km | 0.73° |

The apoapsis gap is the fly pitching over a touch late during the fast part of the turn;
the periapsis, which is what decides whether you stay up, is within 0.5 km.

What this does and does not show:

- **The connectome steers the rocket.** With the calibrated `DNp20`/`DNpe017` readout the
  fly reaches burnout on every seed, leaves the atmosphere, and ends 0.4 km (0.05%) short
  of a controller that reads the true state. Every pilot without a working stick falls
  over. Given a vehicle that can, and a turn to follow, it reaches orbit on every seed
  (below).
- **It is the wiring, not learning.** Live and frozen runs are identical to the last
  digit. The reward and aversive currents were delivered and the dopamine cells fired,
  but no Kenyon cell fired, so no plastic synapse could change. The plastic synapses are
  two hops from a steering cell, so this is a dynamics problem rather than a wiring one;
  [calibration.md](calibration.md) has the measurements and the failed attempts.
- **Blind is no better than hands-off.** With no needle the decoder reads only the noisy
  dark baseline of two single cells. This is the right control for "does the panel
  matter": it does.
- **The instrument does not limit the fly.** Read perfectly, the same panel flies as well
  as direct telemetry.

## Decoder sweep

The first version (300 ms smoothing, full stick at 35 Hz, full needle at 10°) flew to
781 km with a slow ±10° oscillation. `scripts/sweep.py` runs the frozen fly on seeds 0 and
1 for a grid of settings, six flights in parallel. Since live and frozen are identical this
is a pure decoder/instrument sweep; nothing in the brain changes between configurations.

Smoothing time constant × stick gain, needle at 10° (median apoapsis km / mean |error|°):

| tau \ gain | 20 Hz | 35 Hz | 50 Hz | 70 Hz | 100 Hz |
| --- | --- | --- | --- | --- | --- |
| 500 ms | tumble | tumble | tumble | | |
| 300 ms | 765 / 8.1 | 782 / 6.7 | 826 / 2.1 | | |
| 150 ms | 815 / 3.8 | 827 / 2.0 | 830 / 1.4 | 831 / 1.1 | 829 / 1.6 |
| 100 ms | | | 830 / 1.2 | 830 / 1.1 | 829 / 1.5 |
| 50 ms | | | 831 / 1.1 | 831 / 1.1 | 830 / 1.4 |

Lag is the problem, not noise. Anything at or below 150 ms with 50–70 Hz sits on a plateau
within 1.5 km of the autopilot; 100 Hz begins to overshoot; 500 ms falls over regardless
of gain. Needle scale at 70 Hz / 100 ms: 5° gives 831 / 0.8, 10° gives 830 / 1.1, 20°
tumbles on one seed (a 1 px step of the needle is then 1° and the bar saturates too late
to matter). Under doubled gusts 5° (830 / 1.1) still beats 2.5° (830 / 1.3), so the
defaults became 70 Hz, 100 ms, 5°, and the table above was then measured on seeds 3–5.

Per-tick telemetry, commands, spike counts, and hashes for every flight are in
`runs/*/episode-*.jsonl` (not committed).
