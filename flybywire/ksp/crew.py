"""A crew of flies. Three seats, three brains, three needles.

Jeb flies pitch, Bill flies yaw, Bob works the throttle. Each is a complete, separate
copy of the connectome with its own instrument panel and its own decoder; they share
nothing but the ship. Attitude needles are the same edge-anchored bars as the 2D sim.
Bob's panel shows the burn's remaining delta-v as a bar on the right: his steering
cells fire while it is there and go quiet as it shrinks, and the decoder's deadband
becomes the engine cutoff. Nothing about orbital mechanics reaches any of them.

Three brains on one ship is three authorities on one ship, so the arbitration is
explicit: the flight computer is the only thing that writes to the controls. The flies
produce advisory sticks; a rate gyro damps them; the computer's backstops (engine
inhibit while the nose is off the burn vector, cutoff, MECO) override them; SAS is off.
A brain that stops answering has its stick neutralised by a watchdog rather than left
frozen.

Three kernels run in parallel threads: the C kernel releases the GIL, so a tick costs
about as much wall-clock as one brain.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import numpy as np

from ..instruments import black_panel, render_panel

ROLES = ("pitch", "yaw", "throttle")
NAMES = {"pitch": "Jebediah", "yaw": "Bill", "throttle": "Bob"}


class Panels:
    """How the flight computer's numbers become pixels."""

    def __init__(self, error_scale_deg=5.0, dv_scale=40.0):
        if error_scale_deg <= 0 or dv_scale <= 0:
            raise ValueError("Positive scales required")
        self.error_scale_deg = error_scale_deg
        self.dv_scale = dv_scale

    def render(self, truth):
        """truth: pitch_error_deg, yaw_error_deg (+ = nose must move up / right),
        dv_remaining (m/s, None while the engine should be off)."""
        dv = truth.get("dv_remaining")
        return {
            "pitch": render_panel(truth["pitch_error_deg"] / self.error_scale_deg),
            "yaw": render_panel(truth["yaw_error_deg"] / self.error_scale_deg),
            "throttle": black_panel() if dv is None else render_panel(min(1.0, max(0.0, dv) / self.dv_scale)),
        }


def throttle_from_steer(steer, full_at=0.4):
    """Bob's stick to throttle: a full-width bar reads about +0.5 on the decoder."""
    return float(min(1.0, max(0.0, steer / full_at)))


class FlyCrew:
    name = "flies"

    def __init__(self, *, neural_ms=50.0, decoder_kwargs=None, learning=False, roles=ROLES):
        from ..pilot import FlyPilot

        self.roles = tuple(roles)
        self.pool = ThreadPoolExecutor(max_workers=len(self.roles))
        # Loading three connectomes serially takes a minute; in parallel, a third of that.
        make = lambda role: FlyPilot(neural_ms=neural_ms, learning=learning, decoder_kwargs=decoder_kwargs)
        self.pilots = dict(zip(self.roles, self.pool.map(make, self.roles)))
        self.pending = {}
        self.timeouts = {}

    watchdog_seconds = 2.0

    def act(self, frames, truth=None):
        """frames: role -> panel. Returns role -> (stick, neural dict).

        Watchdog: a brain that does not answer within watchdog_seconds has its stick
        neutralised for this tick and is reported as {"timeout": True}; the ship must
        not fly on with a frozen stick while a thread hangs. The late result is
        discarded when it arrives."""
        out = {}
        for role in self.roles:
            # Never step a brain from two threads: a seat whose last tick is still
            # running stays timed out until it finishes.
            if role not in self.pending or self.pending[role].done():
                self.pending[role] = self.pool.submit(self.pilots[role].act, frames[role], None, "none")
        deadline = time.monotonic() + self.watchdog_seconds
        for role in self.roles:
            try:
                command, neural = self.pending[role].result(timeout=max(0.0, deadline - time.monotonic()))
                out[role] = (command.steer, neural)
            except FuturesTimeout:
                self.timeouts[role] = self.timeouts.get(role, 0) + 1
                out[role] = (0.0, {"timeout": True})
        return out

    def begin_episode(self):
        for p in self.pilots.values():
            p.begin_episode()

    # The panel's route to the stick, in order: photoreceptors, optic lobe, projection
    # neurons into the brain, central brain, descending neurons. A recording keeps a
    # fixed sample of each so the whole path can be shown lighting up.
    BRAIN_STRATA = ("ol_sensory", "ol_intrinsic", "visual_projection", "cb_intrinsic", "descending_neuron")

    def brain_sample(self, per_stratum=200, seed=0):
        """Fixed, seeded, stratified sample of neuron indices (same in every seat: the
        three brains are copies) plus their annotation, for brain_frame()."""
        from ..neural.common import annotations

        pilot = next(iter(self.pilots.values()))
        ids = pilot.brain.ids
        a = annotations(ids)
        superclass = a.superclass.fillna("").to_numpy()
        side = a.somaSide.fillna("").to_numpy()
        types = a.type.fillna("").to_numpy()
        decoder = set(np.concatenate([pilot.decoder.left, pilot.decoder.right]).tolist())
        rng = np.random.default_rng(seed)
        chosen = []
        for stratum in self.BRAIN_STRATA:
            pool = np.flatnonzero(superclass == stratum)
            forced = [i for i in pool if i in decoder]
            rest = np.setdiff1d(pool, forced)
            take = rng.choice(rest, size=min(per_stratum - len(forced), len(rest)), replace=False)
            group = np.concatenate([np.asarray(forced, dtype=int), take]).astype(int)
            # Left cells first, then right: one half of the raster per eye.
            chosen.extend(sorted(group.tolist(), key=lambda i: (side[i] != "L", i)))
        self.brain_columns = np.asarray(chosen, dtype=int)
        return [
            {"bodyId": str(ids[i]), "superclass": superclass[i], "side": side[i], "type": types[i], "decoder": i in decoder}
            for i in chosen
        ]

    def brain_frame(self, role):
        """This seat's spike counts over the last neural window for the sampled neurons,
        one byte each (a count above 255 in 50 ms is not a fly neuron)."""
        counts = self.pilots[role].brain.counts[self.brain_columns]
        return np.minimum(counts, 255).astype(np.uint8).tobytes()

    def provenance(self):
        return {role: {"kerbal": NAMES.get(role), **p.provenance()} for role, p in self.pilots.items()}

    def close(self):
        self.pool.shutdown(wait=False)


class AutopilotCrew:
    """Reads the flight computer's numbers directly. The ceiling the flies are judged
    against, and the crew that flies every phase first."""

    name = "autopilot"

    def __init__(self, gain=0.08, damping=0.5, roles=ROLES):
        self.gain, self.damping = gain, damping
        self.roles = tuple(roles)
        self.previous = {}

    def act(self, frames, truth=None):
        out = {}
        for axis in ("pitch", "yaw"):
            e = truth[f"{axis}_error_deg"]
            rate = e - self.previous.get(axis, e)
            self.previous[axis] = e
            out[axis] = (float(np.clip(self.gain * e + self.damping * rate, -1, 1)), {})
        dv = truth.get("dv_remaining")
        # Same shape as Bob's channel: full until the last few m/s, then off.
        stick = 0.0 if dv is None else 0.5 * min(1.0, max(0.0, dv) / 40.0)
        out["throttle"] = (stick, {})
        return out

    def begin_episode(self):
        self.previous = {}

    def provenance(self):
        return {"gain": self.gain, "damping": self.damping}

    def close(self):
        pass


def make_crew(name, **kwargs):
    if name == "flies":
        return FlyCrew(**kwargs)
    if name == "autopilot":
        return AutopilotCrew()
    raise ValueError(f"Unknown crew {name!r}")


def angle_errors(direction, rear_signs=None):
    """Pitch and yaw errors (degrees) from the nose to a unit direction expressed in the
    vessel frame (x right, y nose, z down). + pitch: target above; + yaw: target right.

    Behind the nose (dy < 0) the atan2 angles would both sit near +-180 and flip sign
    with the slightest noise: two saturated needles chattering, and a ship that sits
    still (autopilot mission 3 did, for 30 s, at exactly 180). There the needles are
    driven by the lateral components instead, with the turn direction fixed by
    rear_signs, a (pitch_sign, yaw_sign) pair the caller chose on entering the rear
    hemisphere and keeps until the target is back in front. Exactly behind, with no
    lateral component to speak of, the rule is: pull up."""
    dx, dy, dz = direction
    if dy >= 0:
        return math.degrees(math.atan2(-dz, dy)), math.degrees(math.atan2(dx, dy))
    lateral = math.hypot(dx, dz)
    if rear_signs is None:
        rear_signs = choose_rear_signs(direction)
    if lateral < 0.05:
        return 180.0 * rear_signs[0], 180.0 * rear_signs[1]
    return 180.0 * rear_signs[0] * abs(dz) / lateral, 180.0 * rear_signs[1] * abs(dx) / lateral


def choose_rear_signs(direction):
    """Which way to turn toward a target behind the nose: along the larger lateral
    component, pulling up if there is none."""
    dx, _, dz = direction
    if math.hypot(dx, dz) < 0.05:
        return (1.0, 0.0)
    return (1.0 if -dz >= 0 else -1.0, 1.0 if dx >= 0 else -1.0)
