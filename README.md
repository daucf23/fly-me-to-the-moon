# Fly Me to the Moon

**Literally Fly by Wire.** A fruit-fly connectome at the stick of a rocket.

The full retained **MaleCNS v1.0** wiring diagram (166,700 neurons, 25.6 million
connections) runs as a spiking network. It looks at a synthetic cockpit instrument
panel through modeled photoreceptors. A fixed decoder maps selected descending-neuron
activity to control inputs; the flight computer adds stabilization and safety limits.
The 2D experiments also test engineered reward/aversive stimulation and an experimental
plasticity rule. The recorded Mun mission runs with learning disabled.

Then we ask the only question that matters: **does the fly get to space?**

No living fly is involved. Jebediah is not at risk. The fly, however, is.

## Status

- **Ground truth**: done. Connectome downloaded and verified, kernel benchmarked
([docs/ground-truth.md](docs/ground-truth.md)).
- **Calibration**: done. Of 474 descending neuron types, two respond to the panel; the
needle and decoder were redesigned around them ([docs/calibration.md](docs/calibration.md)).
- **2D simulator**: done. Straight up, the fly reaches 831 km apoapsis vs 832 km for a
cheating autopilot and 6 km hands-off; given an orbital-class vehicle and a gravity turn
to follow, **it reaches an 89 × 964 km orbit on every seed**. Frozen weights fly
identically; blind, it tumbles ([docs/results.md](docs/results.md)). The memory circuit
is two synapses from the stick but cannot be woken without blinding the readout; that is
measured, not assumed ([docs/calibration.md](docs/calibration.md)).
- **Kerbal Space Program**: the fly has flown a 100 t crewed stack off the pad in real
time, staging and all, to 435 km against the autopilot's 443
([docs/ksp.md](docs/ksp.md)).
- **Fly me to the Mun**: **done, with the fly models in the control loop.** Three
separate copies of the connectome: Jeb on pitch, Bill on yaw, Bob on throttle. Their
decoded neural outputs supply control inputs. The flight computer plans burns using
KSP's orbital predictions, adds gyro damping, controls roll, stages, manages warp,
and applies engine/safety overrides. SAS holds attitude during solver pauses and warp;
it is off during active fly control.
The recorded flight (`runs/mun-flies-12-video`, revision `b96bd97`) went from pad to
landing on land in one approximately 34-minute mission with no human piloting:
232.5 km Mun flyby, 4.5 G peak, all three Kerbals home, and no seat timeouts. Learning
was disabled in all three models. Earlier `mun-flies-11-rc` splashed down after
35 minutes, with an 82 km flyby, 27 km entry and 4.8 G; `mun-flies-8` flew by at
194 km / 4.4 G, and `mun-flies-4` at 25 km. After mission 6 hit the Mun, we changed
the planner's scoring to treat impact as fatal. The autopilot crew proved the route
first (300 km flyby). What it took: a rate gyro tuned to the fly's lag, less stick once
the gimbal joins the wheels, and an explicit impact penalty
([docs/ksp.md](docs/ksp.md#fly-me-to-the-mun)). To watch the flies fly:
`scripts/cockpit.py` replays or shows live, per seat, the panel the fly saw, a raster of
1,000 measured neurons from eye to descending cells, the two cells the stick reads, the
fly's stick and what the ship received (`--record-brain` on the flight).

Recorded run logs retain their capture-time commit IDs. The
[revision map](docs/revision-map.json) resolves those IDs after metadata-only history
maintenance; each mapped code snapshot is identical.

**Inspect the recorded flight:** [results, provenance and a 2.8 MB evidence archive](docs/evidence/README.md).
The archive includes telemetry and sampled neural activity for cockpit replay.
The flown Mun vessel still needs to be packaged and validated for fresh-checkout
reproduction; the checked-in craft is the earlier single-seat experiment.

## Flight plan

1. **Ground truth.** Vendor the neural backend, download the connectome, compile the
  kernel, and measure how much wall-clock one 50 ms brain tick costs on this machine.
2. **Simulator.** A small 2D rocket (thrust, gravity, drag, pitch torque, fuel, staging)
  ticks in lockstep with neural time. Instrument panel → retina → brain → decoder →
   controls → reward. Deterministic and headless, so we can run the control conditions
   (live plasticity, frozen weights, black input) and compare apoapsis distributions.
3. **Kerbal Space Program.** Same brain, same decoder, same instrument panel, fed from
  KSP 1.12 telemetry via [kRPC](https://github.com/krpc/krpc) and writing to the
   vessel's controls through the flight computer. Neural seats supply pitch/yaw/throttle
   inputs; the computer supplies roll damping and control augmentation. Episodes end
   in orbit, in the ground, or on a timer, then revert to launch.
4. **Mission control.** A browser view of what the fly sees, what it fires, and how high
  it got. Only after steps 2–3 produce something worth watching.

## The bet

A rocket ascent is three sub-tasks. Two of them are foreign to a fly. One is not.


| Sub-task                       | Fly-brain fit                                                                                                                                             |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Keep the nose up / on prograde | Flies stabilise against the horizon; steering descending neurons like `DNa02` exist for exactly this. We render a horizon that tilts with attitude error. |
| Throttle                       | A motor-rate readout. Decodable, not natural.                                                                                                             |
| Staging                        | No biological analogue. Fires on fuel-empty so the fly is not blamed for it.                                                                              |


That is why the fly sees a **synthetic instrument panel** rather than raw game pixels.

## What the fly is, and is not

The wiring is reconstructed from a real animal. The physiology is a leaky
integrate-and-fire approximation with declared, unvalidated assumptions. The decoder is a
fixed, engineered mapping chosen by us. The reward and aversive currents are engineered
reinforcement, not modeled pleasure or pain. Weight changes are not evidence of learning
until the control conditions say otherwise. All of this is inherited from, and documented
by, the upstream backend in [THIRD_PARTY.md](THIRD_PARTY.md).

## Run it

You need Python 3.11/3.12 via [uv](https://docs.astral.sh/uv/), a C++17 compiler
(`xcode-select --install` on macOS), several GB of disk, and 16 GB RAM or more.

```sh
uv sync --extra test --extra ksp
uv run flybywire prepare                      # ~1.1 GB MaleCNS download, verified, compiled
uv run flybywire bench                        # brain ticks per second on this machine
uv run flybywire calibrate                    # which descending neurons see the needle
uv run flybywire launch --pilot fly           # one launch in the 2D simulator, straight up
uv run flybywire launch --pilot fly --vehicle orbital --gravity-turn   # to orbit
uv run flybywire launch --pilot autopilot     # ...and the baselines: none, random, autopilot
./scripts/phase1_controls.sh                  # the whole Phase 1 protocol
uv run python scripts/sweep.py --tau 50 300   # decoder settings, six flights in parallel
uv run python scripts/probe_regimes.py        # why the memory circuit stays asleep
uv run flybywire ksp --check                  # talk to a running KSP with kRPC
uv run flybywire ksp --quicksave "quicksave #1" --gravity-turn   # one fly, one axis, KSP
uv run flybywire mun --crew flies --quicksave "quicksave #1"     # three flies, to the Mun and back
```

Datasets, the compiled kernel, brain checkpoints, and working run telemetry stay in
ignored `data/` and `runs/`. The selected recorded-mission evidence is archived in
`docs/evidence/`.

## License

Original project code: [MIT](LICENSE). The neural backend, wiring dataset and
soundtrack samples retain their notices in [THIRD_PARTY.md](THIRD_PARTY.md).

## Credits

Neural backend adapted from [nftechie/stonkfly](https://github.com/nftechie/stonkfly) (MIT),
itself descended from DOOMFLY. Wiring from the
[MaleCNS v1.0](https://male-cns.janelia.org/) connectome (HHMI Janelia, Cambridge, Google
Research) under CC BY 4.0. Inspired by everyone who, within a week of the map dropping,
made the fly [trade crypto](https://github.com/nftechie/stonkfly),
[doomscroll](https://github.com/mattyhempstead/fly-wirehead), and play Doom. This fly gets
a rocket.
