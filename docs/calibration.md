# Calibration: which neurons see the needle

Everything here was measured with `flybywire calibrate` and the probe scripts described
below, on the full retained MaleCNS v1.0 graph with plasticity frozen and no reinforcement.
Each stimulus was held for 1 s to settle, then recorded for 2 s. Rates are spikes per
second per cell.

## Assumption that failed

The plan bet on `DNa02`, a steering descending neuron, because flies steer toward vertical
bars. Under any panel we tried, `DNa02` fired zero spikes. So did `DNp09`, `MN9`, `DNa01`,
`DNb01`, and 468 other descending types.

Of **474 descending-neuron types with a cell on each side, exactly two respond to the
panel**: `DNp20` and `DNpe017`. Each has one cell per side. DOOMFLY reached the same pair
after its own calibration. Whatever these cells do in a living fly, in this model they are
the only channel from the eye to the stick.

## What they respond to

A bar 7 px wide at various horizontal positions:

| Position | `DNp20` L / R Hz | `DNpe017` L / R Hz |
| --- | --- | --- |
| black | 6.5 / 19.0 | 6.5 / 9.5 |
| bar at −1 (left edge) | 12.5 / 18.5 | 12.5 / 9.0 |
| bar at −0.5 | 7.5 / 19.5 | 7.5 / 9.5 |
| bar at 0 (centre) | 8.5 / 19.5 | 8.5 / 10.0 |
| bar at +0.5 | 8.0 / 18.0 | 8.0 / 9.0 |
| bar at +1 (right edge) | 7.5 / 28.5 | 7.5 / 14.5 |

Only the extreme lateral positions register. A proportional needle position is invisible
to these cells; a needle at the edge is not.

A full-height bar anchored to one edge, varying its width (both types summed per side):

| Width px | Left bar: L / R Hz | Right bar: L / R Hz | Wall ms per 50 ms |
| --- | --- | --- | --- |
| 0 (black) | 13.0 / 28.5 | 13.0 / 28.5 | 61 |
| 3 | 27.0 / 30.5 | 19.0 / 34.5 | 61 |
| 8 | 37.0 / 30.0 | 14.0 / 50.0 | 62 |
| 15 | 51.0 / 28.5 | 13.0 / 64.5 | 63 |
| 25 | 59.0 / 27.0 | 38.5 / 50.5 | 65 / 216 |
| 40 | 49.5 / 23.5 | 38.5 / 48.5 | 204 / 231 |

The response is monotonic in width up to about 20 px, then the network changes regime:
compute triples, the opposite side lights up, and `DNpe017` collapses. Brightness does
not matter (128 and 255 give identical rates); lit area does. A mid-height band drives
about half as hard as a full-height bar.

## Resulting instrument and decoder

- **Needle**: a full-height bar on the edge of the side the nose must move toward, width
  proportional to the pitch error, capped at 20 px (`flybywire/instruments.py`).
- **Decoder**: per side, the summed rate of `DNp20`+`DNpe017` minus that side's dark
  baseline (L 13.0 Hz, R 28.5 Hz), exponentially smoothed over 300 ms because single
  cells give one to three spikes per 50 ms window; right minus left, 3 Hz deadband, linear
  to full stick at 35 Hz (`flybywire/pilot.py`).
- **Throttle**: fixed at full. No motor readout responded.

Read with a perfect eye (`--pilot panel-autopilot`), this instrument flies the 2D rocket
as well as a controller with direct telemetry access, so it does not limit the fly.

## The memory circuit is unreachable

The plasticity rule modifies KC→MBON synapses and is gated by Kenyon cell firing. Under the
panel, **all 4,064 Kenyon cells are silent**; they only fire when roughly half the visual
field is bright (about 1,500 of them, at 9,000 spikes/s total), which is the same regime
that ruins the steering readout and triples compute. A symmetric bright "sky" band of up to
40 rows did not wake them and compressed the steering signal.

Consequence: reward and aversive currents are delivered and logged, the dopamine cells fire
(~90 Hz each while stimulated), and nothing downstream can change. In this model with this
instrument, the fly steers with the wiring it was born with. The frozen-weights control
exists to demonstrate that claim rather than assume it.
