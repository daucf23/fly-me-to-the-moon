# Ground truth

Measurements from Phase 0 on the development machine (Apple M4 Pro, 12 cores, 48 GB).
Re-run with `uv run flybywire bench`.

## Dataset

`flybywire prepare` downloaded 1,109 MB of MaleCNS v1.0 flat-connectome files from
Google Cloud Storage, verified them against `flybywire/neural/sources.lock.json`, and
compiled the retained graph in 54 s total.

| Quantity | Value |
| --- | --- |
| Retained neurons | 166,700 |
| Directed edges | 25,582,938 |
| Synaptic contacts | 124,177,617 |
| R1–R6 photoreceptors mapped to the panel | 3,335 of 3,377 |
| Neurons with an uncertain transmitter sign | 3,718 |

## Kernel cost

One observation advances 50 ms of neural time in 0.1 ms steps. The kernel is
event-driven, so wall-clock scales with how much of the network is spiking, which in turn
scales with how bright the input is.

| Input (90×160) | Spikes / 50 ms | Wall ms / 50 ms | Brain ticks / s | Real-time ratio |
| --- | --- | --- | --- | --- |
| Black | 13,404 | 75 | 13.4 | 0.67× |
| Uniform noise | 55,932 | 225 | 4.4 | 0.22× |
| Half bright, half dark | 56,224 | 211 | 4.7 | 0.24× |

Brain load from disk: 3.4 s. Kernel compile on first use: a few seconds.

## Consequences for the design

- **The instrument panel should be mostly dark** with a few bright, high-contrast
  elements. That is what the retina responds to anyway, and it buys 2–3× more decisions
  per second.
- **The 2D simulator ticks in lockstep** with neural time (one 50 ms sim step per
  observation), so its wall-clock speed does not matter for correctness.
- **KSP cannot be piloted in real time by this brain.** Expect roughly 5–10 attitude
  decisions per second. Two options for Phase 2: accept a time-dilated fly (KSP runs
  real time, the fly samples it at ~5 Hz), or step KSP by toggling `conn.krpc.paused`
  around each observation for true lockstep. Decide after measuring the panel cost.

## kRPC

kRPC v0.6.0 (`krpc-0.6.0.zip`, SHA-256 `6b4399a8…a17c8`, matches the release
`SHA256SUMS`) is installed at `GameData/kRPC/` in the Steam KSP 1.12.5 install. The
Python client `krpc==0.6.0` is in the `ksp` extra. Connection is verified in Phase 2
once KSP is running with the server started.
