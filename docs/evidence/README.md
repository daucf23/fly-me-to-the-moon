# Recorded Mun mission

The 75-second v6 edit condenses `mun-flies-12-video`, one continuous mission
with no human piloting. The computer supplies planning, roll control, gyro damping,
staging, warp and safety overrides. The three fixed-weight neural models supply
pitch, yaw and throttle inputs. SAS holds attitude during solver pauses and warp;
it is off during active fly control. See [the control breakdown](../ksp.md).

| Measurement | Recorded result |
| --- | --- |
| Wall-clock duration | 2,032 seconds (33 min 52 sec) |
| Mun periapsis | 232,506 m |
| Peak acceleration | 4.5 G |
| Outcome | Landed on Kerbin; all three Kerbals home |
| Telemetry | 10,489 rows; 530 events |
| Seat timeouts | None |
| Neural learning | Disabled for all three seats |

[Summary](summary.json) and [provenance](provenance.json) are readable directly.
[Download the evidence archive](mun-flies-12-video.zip) for the original telemetry,
events, configuration, sampled neural activity, neuron index and instrument images.
These are byte-for-byte copies of the selected run files. The archive includes
checksums for its contents; [SHA256SUMS](SHA256SUMS) verifies the archive itself.
The raw game recording, rendered cockpit video and full connectome are not bundled.

The recording used revision `b96bd974195fe11bf3ecbb2a97f7277c4844bd39`.
After commit-message cleanup, the identical source snapshot is
`14d06d8d106a0820a898f4eefe93911f5204e0ae`;
the [revision map](../revision-map.json) preserves the correspondence.

From the repository root:

```sh
cd docs/evidence
shasum -a 256 -c SHA256SUMS
cd ../..
unzip docs/evidence/mun-flies-12-video.zip -d runs
cd runs/mun-flies-12-video
shasum -a 256 -c SHA256SUMS
cd ../..
uv run python scripts/cockpit.py replay runs/mun-flies-12-video --out cockpit.mp4
```

Replay requires FFmpeg. It renders one logged row per frame at 5 fps by default;
logging intervals and solver pauses vary, so this is not an exact wall-clock replay.
KSP simulation time, wall time and edited playback speed are distinct. The neural
recording contains 1,000 sampled neurons per seat, not every neuron's full state.
Dataset-derived neuron annotations retain the attribution in
[THIRD_PARTY.md](../../THIRD_PARTY.md).

## Reproduction boundary

These files let readers inspect and replay the recorded evidence. A fresh launch
still needs the flown Mun vessel and its staging/action-group setup in KSP 1.12.5
with kRPC. The checked-in `craft/Fly By Wire.craft` is the earlier single-seat test
vehicle, not the Mun stack. Packaging and validating the Mun setup on a fresh
checkout remains open; this archive is not a ready-to-launch save.
