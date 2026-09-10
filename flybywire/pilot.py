"""Pilots. One of them is a fly; the rest exist so we know what the fly's numbers mean.

The fly sees only the instrument panel. The decoder is a fixed, engineered mapping from
named descending neurons to a stick. The cells were chosen by measurement, not by
assumption: of 474 descending types, only DNp20 and DNpe017 respond to the panel at all
(`flybywire calibrate`). Both have exactly one cell per side. Nothing about the rocket
enters the brain except pixels and the reward/aversive currents.
"""

import hashlib
import math

import numpy as np

from .vehicle import Command

# Measured under a black panel after 1 s of settling (docs/calibration.md). The right
# side is much busier than the left in the dark, so the decoder works in rates above
# each side's own baseline.
DEFAULT_BASELINE_HZ = {"L": 13.0, "R": 28.5}


class Decoder:
    def __init__(
        self,
        ids,
        annotation,
        *,
        types=("DNp20", "DNpe017"),
        baseline_hz=None,
        gain_hz=70.0,
        threshold_hz=3.0,
        tau_ms=100.0,
        neural_ms=50.0,
    ):
        t = annotation.type.fillna("")
        sides = annotation.somaSide.fillna("")
        self.left = np.flatnonzero(t.isin(types) & sides.eq("L"))
        self.right = np.flatnonzero(t.isin(types) & sides.eq("R"))
        if not len(self.left) or not len(self.right):
            raise RuntimeError("Missing annotated steering cells")
        for name, value in [("gain_hz", gain_hz), ("threshold_hz", threshold_hz), ("tau_ms", tau_ms)]:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Positive finite {name} required")
        self.types = tuple(types)
        self.baseline = dict(baseline_hz or DEFAULT_BASELINE_HZ)
        self.gain_hz = gain_hz
        self.threshold_hz = threshold_hz
        self.tau_ms = tau_ms
        # Exponential smoothing across observations: single cells are too sparse to
        # read in one 50 ms window. Lag hurts more than noise: 300 ms oscillated at
        # +/-10 degrees, 500 ms tumbled, 50-150 ms all fly within 1.5 km of the
        # autopilot (docs/results.md, decoder sweep).
        self.alpha = 1 - math.exp(-neural_ms / tau_ms)
        self.smoothed = {"L": 0.0, "R": 0.0}
        self.identities = {
            k: [str(ids[i]) for i in getattr(self, k)] for k in ["left", "right"]
        }

    def reset(self):
        self.smoothed = {"L": 0.0, "R": 0.0}

    def decode(self, counts, seconds):
        # Summed rate of the side's cells, minus that side's dark baseline.
        raw = {
            "L": float(counts[self.left].sum() / seconds) - self.baseline["L"],
            "R": float(counts[self.right].sum() / seconds) - self.baseline["R"],
        }
        for s in raw:
            self.smoothed[s] += self.alpha * (raw[s] - self.smoothed[s])
        difference = self.smoothed["R"] - self.smoothed["L"]
        steer = (
            0.0
            if abs(difference) < self.threshold_hz
            else float(np.clip(difference / self.gain_hz, -1, 1))
        )
        return {
            "steer": steer,
            "left_hz": raw["L"] + self.baseline["L"],
            "right_hz": raw["R"] + self.baseline["R"],
            "left_excess_hz": self.smoothed["L"],
            "right_excess_hz": self.smoothed["R"],
            "difference_hz": difference,
        }

    def describe(self):
        return {
            "steer": "Sum of per-side rates of the listed cells minus each side's dark "
            "baseline, exponentially smoothed, right minus left, deadband, linear to +/-1",
            "types": list(self.types),
            "baseline_hz": self.baseline,
            "gain_hz": self.gain_hz,
            "threshold_hz": self.threshold_hz,
            "tau_ms": self.tau_ms,
            "throttle": "fixed at 1.0; no motor readout responded to the panel",
            "cells": self.identities,
        }


class FlyPilot:
    """166,700 neurons, one stick."""

    name = "fly"

    def __init__(
        self,
        *,
        neural_ms=50.0,
        bin_ms=10.0,
        pulse_current_mv=20.0,
        learning=True,
        decoder_kwargs=None,
    ):
        from .neural.common import annotations
        from .neural.visual import VisualMemoryBrain

        for name, value in [("neural_ms", neural_ms), ("bin_ms", bin_ms)]:
            if not math.isfinite(value) or value <= 0 or abs(value * 10 - round(value * 10)) > 1e-7:
                raise ValueError(f"{name} must be a positive multiple of 0.1 ms")
        if bin_ms > 10:
            raise ValueError("Plasticity rate bins must be <= 10 ms")
        self.neural_ms = neural_ms
        self.bin_ms = bin_ms
        self.pulse_current_mv = pulse_current_mv
        self.learning = learning
        self.brain = VisualMemoryBrain()
        self.brain.weights_frozen = not learning
        self.decoder = Decoder(
            self.brain.ids,
            annotations(self.brain.ids),
            neural_ms=neural_ms,
            **(decoder_kwargs or {}),
        )

    def observe(self, frame, reinforcement):
        """Advance neural_ms of brain time under this frame. The reinforcement current, if
        any, is applied for the whole window, as in fly-wirehead."""
        if reinforcement not in ("none", "reward", "aversive"):
            raise ValueError("Unknown reinforcement")
        b = self.brain
        counts = np.zeros(b.n, dtype=np.int32)
        wall = 0.0
        remaining = round(self.neural_ms / b.dt)
        stimulus = (
            None
            if reinforcement == "none"
            else (b.circuit[reinforcement], self.pulse_current_mv)
        )
        while remaining:
            n = min(remaining, round(self.bin_ms / b.dt))
            c, elapsed = b.rgb_step(
                frame, n * b.dt, learning=self.learning, stimulation=stimulus
            )
            counts += c
            wall += elapsed
            remaining -= n
        b.counts[:] = counts
        return {
            **self.decoder.decode(counts, self.neural_ms / 1000),
            "brain_ms": b.sim_ms,
            "compute_seconds": wall,
            "stimulus": reinforcement,
            "reward_spikes": int(counts[b.circuit["reward"]].sum()),
            "aversive_spikes": int(counts[b.circuit["aversive"]].sum()),
            "KC_spikes": int(counts[b.circuit["kc"]].sum()),
            "total_spikes": int(counts.sum()),
            "spike_sha256": hashlib.sha256(counts.tobytes()).hexdigest(),
            "input_sha256": hashlib.sha256(np.asarray(frame).tobytes()).hexdigest(),
            "memory": b.memory(),
        }

    def act(self, frame, telemetry, reinforcement):
        neural = self.observe(frame, reinforcement)
        return Command(steer=neural["steer"], throttle=1.0), neural

    def begin_episode(self):
        # The brain keeps its state and memory across launches; only the stick's
        # smoothing filter starts fresh.
        self.decoder.reset()

    def save(self, path):
        self.brain.checkpoint(path)

    def restore(self, path):
        self.brain.restore(path)

    def provenance(self):
        return {
            "neural_ms": self.neural_ms,
            "bin_ms": self.bin_ms,
            "pulse_current_mv": self.pulse_current_mv,
            "learning": self.learning,
            "decoder": self.decoder.describe(),
            "circuit": self.brain.circuit["report"],
            "vision": self.brain.visual_report,
        }


class NullPilot:
    """Hands off. Shows what the aerodynamics do on their own."""

    name = "none"

    def act(self, frame, telemetry, reinforcement):
        return Command(steer=0.0, throttle=1.0), {}


class RandomPilot:
    """A stick wiggled at random. If the fly cannot beat this, the fly is not flying."""

    name = "random"

    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)

    def act(self, frame, telemetry, reinforcement):
        return Command(steer=float(self.rng.uniform(-1, 1)), throttle=1.0), {}


class Autopilot:
    """A proportional-derivative controller on the true pitch error. Upper bound."""

    name = "autopilot"

    def __init__(self, gain=0.08, damping=0.5):
        self.gain = gain
        self.damping = damping
        self.previous = None

    def act(self, frame, telemetry, reinforcement):
        error = telemetry.steer_error_deg
        rate = 0.0 if self.previous is None else error - self.previous
        self.previous = error
        return Command(steer=self.gain * error + self.damping * rate, throttle=1.0), {}


class PanelAutopilot:
    """Reads the same panel the fly reads, with a perfect eye: what an ideal decoder of
    this instrument could achieve. Steer equals the drawn bar's signed width fraction."""

    name = "panel-autopilot"

    def act(self, frame, telemetry, reinforcement):
        from .instruments import MAX_BAR_WIDTH, WIDTH

        bright = frame[:, :, 0].max(axis=0) == 255
        left = int(bright[: WIDTH // 2].sum())
        right = int(bright[WIDTH // 2 :].sum())
        return Command(steer=(right - left) / MAX_BAR_WIDTH, throttle=1.0), {}


def make_pilot(name, **kwargs):
    if name == "fly":
        return FlyPilot(**kwargs)
    if name == "none":
        return NullPilot()
    if name == "random":
        return RandomPilot(seed=kwargs.get("seed", 0))
    if name == "autopilot":
        return Autopilot()
    if name == "panel-autopilot":
        return PanelAutopilot()
    raise ValueError(f"Unknown pilot: {name}")
