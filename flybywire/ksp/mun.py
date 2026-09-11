"""Fly Me to the Mun: a free-return flyby of the Mun with the needles flown by flies.

Division of labour, Apollo style. The flight computer (this file) knows orbital
mechanics: it plans burns as maneuver nodes with KSP's own patched conics, decides when
to burn, stages, works the action groups, and time-warps the coasts. The crew flies the
needles: Jeb holds the pitch needle, Bill the yaw needle, Bob the remaining-delta-v bar
that is the throttle. Every attitude and every throttle in the mission passes through
a connectome; no timing or geometry does.

Phases: prelaunch -> ascent -> coast_to_apoapsis -> circularize (burn) -> plan_tmi ->
tmi (burn) -> coast_to_mun [-> correction (burn)] -> mun_flyby -> return_coast
[-> correction (burn)] -> entry -> done.

The vessel is whatever is on the pad or in the quicksave. This was written for a stack
with a Mainsail booster, a Poodle upper stage, a Mk1-3 pod with heat shield and chutes,
action group 1 bound to the escape tower, Lights to the solar panels and Abort to
"separate the capsule and arm the parachutes".
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .crew import Panels, angle_errors, choose_rear_signs, throttle_from_steer
from .vehicle import ESCAPE_APOAPSIS

# Control augmentation per crew: (authority, damping). The autopilot crew damps itself.
# A fly is a 0.13 stick/deg proportional controller with a 0.3 s lag that saturates near
# 5 deg (measured on fly mission 1); on the Poodle stage the wheels give about 21 deg/s^2
# per unit stick, so at 0.7 / 0.03 the loop had a damping ratio of 0.2 and sat in a
# +-8 deg limit cycle for the whole mission. 0.5 / 0.12 settles a 20 deg error in ~6 s
# and stays damped from the booster (with gimbal) to the bare upper stage.
CREW_AUGMENTATION = {"flies": (0.5, 0.12), "autopilot": (0.7, 0.03)}


@dataclass(frozen=True)
class MunConfig:
    address: str = "127.0.0.1"
    rpc_port: int = 50000
    stream_port: int = 50001
    quicksave: str | None = None
    dt: float = 0.05
    parking_altitude: float = 100_000.0
    turn_start: float = 2_000.0  # pitch program: vertical below this (about 100 m/s)...
    turn_end: float = 40_000.0  # ...square-root ramp to turn_pitch at this altitude, then hold
    turn_pitch: float = 85.0
    max_aoa_deg: float = 3.0  # thick air (below aoa_altitude): program stays this close to surface prograde
    aoa_altitude: float = 25_000.0
    max_aoa_high_deg: float = 10.0  # thin air up to aoa_free_altitude: allowed to pull ahead this much
    aoa_free_altitude: float = 45_000.0
    les_altitude: float = 55_000.0  # eject the escape tower above this (action group 1)
    mun_periapsis: float = 60_000.0  # flyby altitude
    return_periapsis: float = 40_000.0  # Kerbin entry altitude (32 km executed to 25.7 km gave 11.9 G)
    correction_tolerance: float = 15_000.0  # fix the return periapsis if further off
    entry_altitude: float = 90_000.0  # separate the capsule, arm chutes (Abort) here
    drogue_altitude: float = 5_000.0  # drogue full deployment; armed at separation
    main_altitude: float = 3_000.0  # mains full deployment; armed once the drogue is out
    authority: float = 0.7  # fraction of deflection the crew may command per axis
    damping: float = 0.03  # rate gyro, stick per deg/s
    # On the upper stage the Poodle's gimbal at full throttle more than doubles what the
    # wheels do (62-77 vs 31 deg/s^2 per unit stick, fly missions 2-3, rising as the
    # tanks empty), and a loop tuned for the wheels chatters against the stops the
    # moment the engine lights. Authority and damping are both divided by
    # (1 + thrust_authority * throttle) there; 2.0 keeps the loop where the coast has it
    # up to ~95 deg/s^2. Not on the booster: the Mainsail's gimbal is the whole
    # authority, and the loop was tuned with it lit.
    thrust_authority: float = 2.0
    roll_damping: float = 0.1  # computer holds roll rate: stick per deg/s
    error_scale_deg: float = 5.0
    dv_scale: float = 40.0
    warp_lead: float = 45.0  # come out of warp this many seconds before an event
    inhibit_deg: float = 5.0  # engine inhibit: blank Bob's bar when the nose is further off than this...
    permit_deg: float = 2.0  # ...and light it again only once it is back within this
    lost_seat_ticks: int = 40  # consecutive watchdog timeouts before the computer takes an axis
    rcs: str = "off"  # off: reaction wheels and gimbal only. turns: armed for large reorientations. always.
    rcs_arm_deg: float = 20.0
    rcs_disarm_deg: float = 5.0
    stop_after: str | None = None  # end the run when this phase begins (shakedowns)
    save_milestones: bool = False  # quicksave after circularization and TMI, to restart from
    wall_timeout: float = 3 * 3600.0


MILESTONE_SAVES = {"plan_tmi": "flybywire-orbit", "coast_to_mun": "flybywire-tmi"}


class MunMission:
    def __init__(self, config, crew, run_dir):
        import krpc

        self.c = config
        self.crew = crew
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.panels = Panels(config.error_scale_deg, config.dv_scale)
        self.conn = krpc.connect(name="flybywire-mun", address=config.address, rpc_port=config.rpc_port, stream_port=config.stream_port)
        self.sc = self.conn.space_center
        self.events = []
        self.phase = "prelaunch"
        self.node = None
        self.after_burn = None
        self.burn_started = False
        self.previous = {}
        self.flags = {"les": False, "panels": False, "abort": False, "warned": set()}
        self.engine_permitted = True
        self.burn_direction = None  # the node's burn vector in an inertial frame, fixed for the burn
        self.lost = {}  # role -> consecutive watchdog timeouts
        self.rear_signs = None  # turn direction chosen while the target is behind the nose
        self.log = None
        self.tick = 0
        self.t_wall0 = time.time()

    # --- bookkeeping ---------------------------------------------------------------

    def event(self, kind, **data):
        row = {"ut": round(self.sc.ut, 1), "phase": self.phase, "event": kind, **data}
        self.events.append(row)
        print(json.dumps(row, default=str), flush=True)
        (self.run_dir / "events.jsonl").open("a").write(json.dumps(row, default=str) + "\n")

    def go(self, phase):
        self.event("phase", to=phase)
        if phase not in ("prelaunch", "ascent"):
            self.flags["upper"] = True  # whatever is left to burn is the upper stage
        if self.c.save_milestones and phase in MILESTONE_SAVES and self.tick > 0:
            self.save_milestone(MILESTONE_SAVES[phase])
        if phase == self.c.stop_after:
            self.event("stop", reason=f"--stop-after {phase}")
            phase = "done"
        self.phase = phase
        self.previous = {}

    def save_milestone(self, name):
        """A quicksave to restart the mission from (to_pad recognises an orbiting vessel).
        Only in vacuum with the engine off; KSP refuses to save under acceleration."""
        try:
            self.v.control.throttle = 0.0
            self.sc.save(name)
            self.event("quicksave", name=name)
        except Exception as e:
            self.event("quicksave", name=name, error=str(e)[:80])

    # --- geometry ------------------------------------------------------------------

    def in_vessel(self, direction, frame):
        d = self.sc.transform_direction(tuple(direction), frame, self.v.reference_frame)
        n = math.sqrt(sum(x * x for x in d))
        return tuple(x / n for x in d) if n else (0.0, 1.0, 0.0)

    def surface_direction(self, pitch_deg, heading_deg=90.0):
        p, h = math.radians(pitch_deg), math.radians(heading_deg)
        # surface frame: x up, y north, z east
        return self.in_vessel((math.cos(p), math.sin(p) * math.cos(h), math.sin(p) * math.sin(h)), self.v.surface_reference_frame)

    def prograde(self, surface=False):
        body = self.v.orbit.body
        frame = body.reference_frame if surface else body.non_rotating_reference_frame
        return self.in_vessel(self.v.flight(frame).prograde, frame)

    def retrograde_surface(self):
        frame = self.v.orbit.body.reference_frame
        return self.in_vessel(self.v.flight(frame).retrograde, frame)

    def program_pitch(self, altitude):
        """Pitch from vertical the ascent program asks for, before the angle-of-attack cap."""
        c = self.c
        if altitude < c.turn_start:
            return 0.0
        frac = min(1.0, (altitude - c.turn_start) / (c.turn_end - c.turn_start))
        return c.turn_pitch * math.sqrt(frac)

    def ascent_pitch(self, altitude):
        """The program, held within max_aoa_deg of surface prograde while the air is thick.
        A heavy pod on top is aerodynamically unstable: the nose ahead of the velocity
        vector at max Q is what flipped the first shakedown 40 degrees. This is what a
        gravity turn is."""
        c = self.c
        program = self.program_pitch(altitude)
        self.ascent_debug = {"program": round(program, 1), "prograde": None}
        if altitude > c.aoa_free_altitude:
            return program
        body = self.v.orbit.body
        vel = self.v.flight(body.reference_frame).velocity
        if math.sqrt(sum(x * x for x in vel)) < 50.0:
            return program
        up, north, east = self.sc.transform_direction(vel, body.reference_frame, self.v.surface_reference_frame)
        prograde_pitch = math.degrees(math.atan2(math.hypot(north, east), up))
        self.ascent_debug["prograde"] = round(prograde_pitch, 1)
        cap = c.max_aoa_deg if altitude < c.aoa_altitude else c.max_aoa_high_deg
        return min(max(program, prograde_pitch - cap), prograde_pitch + cap)

    def upper_engine(self):
        """The main engine with the lowest stage number, excluding the escape tower.
        Looked up every time: KSP renumbers stages when a part leaves (ejecting the
        tower moved the Poodle from stage 4 to 3 and broke a cached number)."""
        engines = [e for e in self.v.parts.engines if e.part.stage >= 0 and "escape" not in e.part.title.lower()]
        return min(engines, key=lambda e: e.part.stage) if engines else None

    @property
    def on_upper_stage(self):
        e = self.upper_engine()
        return e is None or e.active or self.v.control.current_stage <= e.part.stage

    def burn_seconds(self, dv):
        thrust = max(self.v.available_thrust, 1.0)
        isp = max(self.v.specific_impulse, 1.0)
        m0 = self.v.mass
        mdot = thrust / (isp * 9.80665)
        m1 = m0 * math.exp(-dv / (isp * 9.80665))
        return (m0 - m1) / mdot

    # --- maneuver planning ------------------------------------------------------------

    def circularization_node(self):
        o = self.v.orbit
        mu = o.body.gravitational_parameter
        r = o.apoapsis
        v_apo = math.sqrt(mu * (2 / r - 1 / o.semi_major_axis))
        dv = math.sqrt(mu / r) - v_apo
        ut = self.sc.ut + o.time_to_apoapsis
        node = self.v.control.add_node(ut, prograde=dv)
        self.event("node", purpose="circularize", dv=round(dv, 1), ut=round(ut, 1))
        return node

    def patches(self, node_or_orbit):
        """(Mun periapsis, Kerbin return periapsis) along the patched-conic chain from a
        node's post-burn orbit or from a current orbit. None where the chain does not
        go there. Works from Kerbin orbit before the encounter, from inside the Mun's
        sphere, and on the way home (Mun periapsis then None)."""
        try:
            o = getattr(node_or_orbit, "orbit", node_or_orbit)
            if o.body.name == "Kerbin":
                nxt = o.next_orbit
                if nxt is None or nxt.body.name != "Mun":
                    return None, o.periapsis_altitude if self.flags.get("flyby_done") else None
                o = nxt
            if o.body.name != "Mun":
                return None, None
            mun = o.periapsis_altitude
            back = o.next_orbit
            if back is None or back.body.name != "Kerbin":
                return mun, None
            return mun, back.periapsis_altitude
        except Exception:
            return None, None

    def trajectory_score(self, mun, back, score_mun=True):
        """Lower is better. The return periapsis is the survival number and weighs ten
        times the flyby altitude: 10 km off on the return costs what 30 km off at the
        Mun costs. No return at all (captured, escaped, no encounter) is far worse."""
        c = self.c
        if back is None and mun is None:
            return 1e6
        s = 400.0 if back is None else ((back - c.return_periapsis) / 1e4) ** 2
        if score_mun:
            if mun is None:
                return 1e6
            s += 0.1 * ((mun - c.mun_periapsis) / 1e4) ** 2
            if mun < 15_000:
                s += 100.0  # too close to the Mun's mountains
        return s

    def pattern_search(self, node, params, best, steps, floor, budget=300, score_mun=True):
        """Coordinate pattern search on node attributes (e.g. ("ut", "prograde")).
        Bounded score, no derivatives: the patched-conic response is discontinuous
        wherever an encounter appears or vanishes. best = (score, values, mun, back)."""
        steps = np.array(steps, dtype=float)
        evals = 0
        while np.any(steps > floor) and evals < budget:
            improved = False
            for i in range(len(params)):
                for sign in (1, -1):
                    values = list(best[1])
                    values[i] += sign * steps[i]
                    for p, x in zip(params, values):
                        setattr(node, p, float(x))
                    mun, back = self.patches(node)
                    s = self.trajectory_score(mun, back, score_mun)
                    evals += 1
                    if s < best[0] - 1e-9:
                        best, improved = (s, values, mun, back), True
                        break
                if improved:
                    break
            if not improved:
                steps /= 2
        for p, x in zip(params, best[1]):
            setattr(node, p, float(x))
        return best, evals

    def solve_free_return(self):
        """Search burn time and prograde delta-v for a Mun flyby that comes back to a
        Kerbin periapsis at the entry altitude, using KSP's own patched conics through
        a maneuver node. The encounter band is a few minutes wide in one orbit and the
        free-return corridor inside it is about 8 s by 2 m/s wide, so: coarse grid to
        find the band, fine grid inside it, pattern search to the corridor. The burn
        cannot be executed to that precision by anyone; the mid-course correction is
        part of the plan, not a repair."""
        o = self.v.orbit
        now = self.sc.ut
        self.hands_off()
        node = self.v.control.add_node(now + 300, prograde=860)
        evals = 0

        def grid(uts, dvs, best=None):
            nonlocal evals
            for ut in uts:
                for dv in dvs:
                    node.ut, node.prograde = float(ut), float(dv)
                    mun, back = self.patches(node)
                    s = self.trajectory_score(mun, back)
                    evals += 1
                    if best is None or s < best[0]:
                        best = (s, [float(ut), float(dv)], mun, back)
            return best

        best = grid(now + 240 + np.arange(0, o.period, 20.0), (845.0, 860.0, 875.0, 890.0))
        if best is None or best[0] >= 1e6:
            node.remove()
            self.hands_on()
            raise RuntimeError("No Mun encounter found in one orbit of burn times")
        self.event("tmi_coarse", ut=round(best[1][0]), dv=best[1][1], mun_periapsis=round(best[2]), return_periapsis=best[3], evals=evals)
        best = grid(best[1][0] + np.arange(-60, 61, 4.0), np.arange(848.0, 872.1, 1.0), best)
        self.event("tmi_fine", ut=round(best[1][0]), dv=best[1][1], mun_periapsis=round(best[2]), return_periapsis=best[3], evals=evals)
        best, n = self.pattern_search(node, ("ut", "prograde"), best, steps=(2.0, 0.5), floor=0.02)
        s, (ut, dv), mun, back = best
        self.event(
            "node", purpose="tmi", dv=round(dv, 3), ut=round(ut, 2), mun_periapsis=round(mun),
            return_periapsis=None if back is None else round(back), free_return=back is not None and back > 0,
            score=round(s, 3), evals=evals + n,
        )
        self.hands_on()
        return node

    def correction_node(self, score_mun=True, max_dv=60.0, span=20.0):
        """Mid-course correction: a small burn 120 s from now in the prograde/radial
        plane that moves the predicted trajectory back onto the targets, found by the
        same pattern search. Outbound it targets both periapses; homebound only the
        entry corridor. Returns None if it would not help or would cost too much."""
        self.hands_off()
        ut = self.sc.ut + 120.0
        node = self.v.control.add_node(ut, prograde=0.0, radial=0.0)
        mun, back = self.patches(node)
        before = self.trajectory_score(mun, back, score_mun)
        best = (before, [0.0, 0.0], mun, back)
        # Coarse look first: the corridor may be several m/s away in either axis, and
        # on the way home, after a wide flyby, a couple of hundred.
        span, step_p, step_r = (span, span / 10, span / 5) if score_mun else (max_dv, max_dv / 15, max_dv / 8)
        for p in np.arange(-span, span + 0.1, step_p):
            for r in np.arange(-span, span + 0.1, step_r):
                node.prograde, node.radial = float(p), float(r)
                mun, back = self.patches(node)
                s = self.trajectory_score(mun, back, score_mun)
                if s < best[0]:
                    best = (s, [float(p), float(r)], mun, back)
        best, evals = self.pattern_search(node, ("prograde", "radial"), best, steps=(1.0, 1.0), floor=0.005, score_mun=score_mun)
        s, (p, r), mun, back = best
        dv = math.hypot(p, r)
        self.hands_on()
        if dv > max_dv or s >= before - 1e-6 or dv < 0.05:
            node.remove()
            self.event("no_correction", reason="too expensive" if dv > max_dv else "no improvement", dv=round(dv, 2), score_before=round(before, 3), score_after=round(s, 3))
            return None
        self.event(
            "node", purpose="correction", prograde=round(p, 3), radial=round(r, 3), dv=round(dv, 3),
            mun_periapsis=None if mun is None else round(mun), return_periapsis=None if back is None else round(back),
            score_before=round(before, 3), score_after=round(s, 3), evals=evals,
        )
        return node

    # --- the loop --------------------------------------------------------------------

    def to_pad(self):
        """Load the quicksave if asked or if nothing controllable sits on the pad. Never
        reverts, never recovers. A save made in orbit (save_milestone) is accepted too;
        fly() then picks the phase up from there."""
        sc = self.sc

        def ready():
            try:
                v = sc.active_vessel
                return (
                    self.conn.krpc.current_game_scene == self.conn.krpc.GameScene.flight
                    and v.situation in (sc.VesselSituation.pre_launch, sc.VesselSituation.orbiting, sc.VesselSituation.escaping)
                    and v.control.state != sc.ControlState.none
                    and v.control.current_stage >= 0
                )
            except Exception:
                return False

        if self.c.quicksave or not ready():
            if not self.c.quicksave:
                raise RuntimeError("No controllable vessel on the pad and no --quicksave given")
            self.event("load", quicksave=self.c.quicksave)
            ut_before = sc.ut
            t_load = time.monotonic()
            sc.load(self.c.quicksave)
            good = 0
            while time.monotonic() - t_load < 120 and good < 4:
                time.sleep(0.5)
                # The vessel we are leaving behind may itself look ready (in orbit,
                # say) for the moment before KSP starts loading; a loaded save has a
                # clock that real time since the load cannot explain.
                loaded = abs(sc.ut - ut_before) > 5 * (time.monotonic() - t_load) + 1
                good = good + 1 if ready() and loaded else 0
            if good < 4:
                raise RuntimeError("Quicksave did not produce a controllable vessel on the pad")
        return sc.active_vessel

    def fly(self):
        self.v = self.to_pad()
        self.crew.begin_episode()
        self.log = (self.run_dir / "mission.jsonl").open("w")
        # One writer. SAS on the same axis as a fly is two hands on one stick.
        self.v.control.sas = False
        self.v.control.rcs = self.c.rcs == "always"
        self.v.control.throttle = 0.0
        self.last_stage_ut = -1e9
        self.event("start", vessel=self.v.name, crew=[k.name for k in self.v.crew], mass=round(self.v.mass), sas=self.v.control.sas, rcs=self.c.rcs, monopropellant=round(self.v.resources.amount("MonoPropellant"), 1))
        if self.v.situation != self.sc.VesselSituation.pre_launch:
            self.resume_in_space()
        try:
            while self.phase != "done":
                if time.time() - self.t_wall0 > self.c.wall_timeout:
                    self.event("abort", reason="wall timeout")
                    break
                self.step()
            return self.summary()
        finally:
            self.log.close()
            try:
                self.v.control.throttle = 0.0
                self.v.control.sas = True
            except Exception:
                pass

    def resume_in_space(self):
        """Pick the mission up from a save made in flight: in a low Kerbin orbit that is
        plan_tmi; flung out toward the Mun's distance, with or without an encounter, it
        is coast_to_mun (which corrects a lost encounter); inside the Mun's sphere the
        flyby; homebound, periapsis already in the air, the return coast. The
        ascent-only jobs (tower, panels) are marked done; the action groups are harmless
        if repeated."""
        o = self.v.orbit
        self.flags["les"] = self.flags["panels"] = True
        for n in self.v.control.nodes:
            n.remove()
        high = o.apoapsis_altitude > 3e6 or o.apoapsis_altitude < 0  # out to the Mun's distance, or escaping
        if o.body.name == "Mun":
            phase = "mun_flyby"
        elif high and o.periapsis_altitude < 70_000:
            self.flags["flyby_done"] = True
            phase = "return_coast"
        elif high or (o.next_orbit is not None and o.next_orbit.body.name == "Mun"):
            phase = "coast_to_mun"
        else:
            phase = "plan_tmi"
        self.event("resume", situation=str(self.v.situation).split(".")[-1], body=o.body.name, apoapsis=round(min(o.apoapsis_altitude, ESCAPE_APOAPSIS)), periapsis=round(o.periapsis_altitude))
        self.go(phase)

    def truth(self):
        """What the flight computer knows this tick; the crew sees only its needles."""
        c = self.c
        v = self.v
        alt = v.flight().mean_altitude
        o = v.orbit
        ph = self.phase
        target, dv = (0.0, 1.0, 0.0), None
        if ph in ("prelaunch", "ascent"):
            target = self.surface_direction(self.ascent_pitch(alt))
            if ph == "ascent":
                # The first stage never shuts down (engine off means no gimbal and a
                # 100 t stack the wheels cannot turn): Bob sees a full bar until the
                # Poodle is lit, then the apoapsis shortfall, 10 km reading as full.
                shortfall = c.parking_altitude - o.apoapsis_altitude
                if self.on_upper_stage:
                    dv = max(0.0, shortfall) / 250.0
                else:
                    dv = None if "booster_sep" in self.flags else c.dv_scale
        elif ph in ("coast_to_apoapsis", "coast_to_mun", "return_coast"):
            target = self.prograde()
        elif ph == "burn" and self.node is not None:
            # Fixed burn attitude: the node's full vector, held in an inertial frame.
            # The remaining vector swings wildly in the last metres per second and
            # would have Jeb and Bill chasing it while Bob is still burning.
            frame = o.body.non_rotating_reference_frame
            dv = None
            try:
                if self.burn_direction is None:
                    self.burn_direction = self.node.direction(frame)
                target = self.in_vessel(self.burn_direction, frame)
                if self.burn_started:
                    # Velocity-to-be-gained, signed along the burn attitude. Past the node
                    # the remaining vector reverses; Bob must see nothing then, or he
                    # relights into the overshoot (autopilot mission 2 burned 850 m/s
                    # extra that way).
                    remaining = self.node.remaining_burn_vector(frame)
                    self.burn_along = float(np.dot(remaining, self.burn_direction))
                    dv = max(0.0, self.burn_along)
            except RuntimeError:
                target = self.prograde()  # node gone; burn_logic ends the mission this tick
        elif ph == "mun_flyby":
            target = self.prograde()
        elif ph == "entry":
            target = self.retrograde_surface()
        # Target behind the nose: pick the turn direction once, hold it until it is in front.
        if target[1] < 0:
            if self.rear_signs is None:
                self.rear_signs = choose_rear_signs(target)
                self.event("turn_around", signs=self.rear_signs)
        else:
            self.rear_signs = None
        pitch, yaw = angle_errors(target, self.rear_signs)
        # Engine inhibit: during orbital burns Bob's bar is blank while the nose is off
        # the vector, with hysteresis so it does not flicker. The first stage is exempt;
        # a Mainsail cut at 10 km is the worse failure.
        off = math.hypot(pitch, yaw)
        if ph == "burn":
            if self.engine_permitted and off > c.inhibit_deg:
                self.engine_permitted = False
                self.event("engine_inhibit", off_deg=round(off, 1))
            elif not self.engine_permitted and off < c.permit_deg:
                self.engine_permitted = True
                self.event("engine_permit", off_deg=round(off, 1))
            if not self.engine_permitted:
                dv = None
        return {"pitch_error_deg": pitch, "yaw_error_deg": yaw, "dv_remaining": dv, "altitude": alt, "off_deg": off}

    def step(self):
        c = self.c
        v = self.v
        ut = self.sc.ut
        truth = self.truth()
        frames = self.panels.render(truth)
        sticks = dict(self.crew.act(frames, truth))

        # A seat that keeps timing out is flown by the computer, and said so.
        for role in sticks:
            if sticks[role][1].get("timeout"):
                self.lost[role] = self.lost.get(role, 0) + 1
                if self.lost[role] == c.lost_seat_ticks:
                    self.event("seat_lost", role=role)
            else:
                if self.lost.get(role, 0) >= c.lost_seat_ticks:
                    self.event("seat_recovered", role=role)
                self.lost[role] = 0
            if self.lost[role] >= c.lost_seat_ticks:
                if role == "throttle":
                    d = truth["dv_remaining"]
                    sticks[role] = (0.0 if d is None else 0.5 * min(1.0, d / c.dv_scale), {"computer": True})
                else:
                    sticks[role] = (float(np.clip(0.08 * truth[f"{role}_error_deg"], -1, 1)), {"computer": True})

        # Control augmentation: the crew commands attitude, a rate gyro damps. Both are
        # scaled down for the gimbal's share of the authority once the upper stage is
        # burning (see MunConfig.thrust_authority); the throttle used is last tick's,
        # which is what the engine is doing now.
        scale = 1.0 / (1.0 + c.thrust_authority * getattr(self, "last_throttle", 0.0)) if self.flags.get("upper") else 1.0
        controls = {}
        for axis in ("pitch", "yaw"):
            e = truth[f"{axis}_error_deg"]
            rate = 0.0
            if axis in self.previous and ut > self.previous[axis][1]:
                de = e - self.previous[axis][0]
                # A jump of tens of degrees in one tick is a needle convention change
                # (rear hemisphere in or out), not a rotation; the gyro ignores it.
                rate = 0.0 if abs(de) > 45 else de / (ut - self.previous[axis][1])
            self.previous[axis] = (e, ut)
            controls[axis] = float(np.clip(scale * (c.authority * sticks[axis][0] + c.damping * rate), -1, 1))
            if self.flags.get("power_low"):
                controls[axis] = 0.0
        v.control.pitch = controls["pitch"]
        v.control.yaw = controls["yaw"]
        controls["roll"] = self.roll_damping()
        v.control.roll = controls["roll"]
        if c.rcs == "turns":
            # Thrusters only for big reorientations; a fly's twitches are not worth monopropellant.
            if not v.control.rcs and truth["off_deg"] > c.rcs_arm_deg:
                v.control.rcs = True
                self.event("rcs", armed=True, off_deg=round(truth["off_deg"], 1))
            elif v.control.rcs and truth["off_deg"] < c.rcs_disarm_deg:
                v.control.rcs = False
                self.event("rcs", armed=False, monopropellant=round(v.resources.amount("MonoPropellant"), 1))
        throttle = throttle_from_steer(sticks["throttle"][0]) if truth["dv_remaining"] is not None else 0.0
        v.control.throttle = throttle
        self.last_throttle = throttle

        self.phase_logic(truth, throttle)

        self.tick += 1
        row = {
            "tick": self.tick,
            "ut": round(ut, 2),
            "phase": self.phase,
            "altitude": round(truth["altitude"], 1),
            "body": v.orbit.body.name,
            "apoapsis": round(min(v.orbit.apoapsis_altitude, ESCAPE_APOAPSIS), 1),
            "periapsis": round(v.orbit.periapsis_altitude, 1),
            "pitch_error_deg": round(truth["pitch_error_deg"], 3),
            "yaw_error_deg": round(truth["yaw_error_deg"], 3),
            "dv_remaining": None if truth["dv_remaining"] is None else round(truth["dv_remaining"], 2),
            "pitch": round(v.flight().pitch, 1),
            "roll_rate": round(getattr(self, "roll_rate", 0.0), 2),
            "ascent": getattr(self, "ascent_debug", None) if self.phase == "ascent" else None,
            "sticks": {r: round(s[0], 4) for r, s in sticks.items()},
            "controls": {**{k: round(x, 4) for k, x in controls.items()}, "throttle": round(throttle, 3)},
            "neural": {r: {k: s[1][k] for k in ("left_hz", "right_hz", "steer", "compute_seconds") if k in s[1]} for r, s in sticks.items()},
        }
        if self.phase == "entry":
            g = v.flight().g_force
            row["g_force"] = round(g, 2)
            self.flags["max_g"] = max(self.flags.get("max_g", 0.0), g)
        self.log.write(json.dumps(row) + "\n")
        if self.tick % 20 == 0:
            from PIL import Image

            for role, frame in frames.items():
                Image.fromarray(frame).save(self.run_dir / f"panel-{role}.png")
        time.sleep(c.dt)

    # --- phases ----------------------------------------------------------------------

    def phase_logic(self, truth, throttle):
        c = self.c
        v = self.v
        ctl = v.control
        o = v.orbit
        alt = truth["altitude"]
        ph = self.phase

        if ph == "prelaunch":
            if not self.flags.get("lit"):
                ctl.throttle = 1.0
                ctl.activate_next_stage()
                self.flags["lit"] = True
                self.flags["lit_at"] = time.monotonic()
                self.event("ignition")
                return
            ctl.throttle = 1.0
            if v.parts.launch_clamps and v.available_thrust > 0 and v.thrust > 0.9 * v.available_thrust:
                ctl.activate_next_stage()
                self.event("liftoff")
                self.go("ascent")
            elif time.monotonic() - self.flags["lit_at"] > 8:
                raise RuntimeError("No thrust after ignition; vessel uncontrollable or staging dead")
            return

        # The escape tower comes off above les_altitude whatever phase we are in (Bob's
        # MECO came under 55 km once and the tower rode the whole mission to splashdown),
        # and in any case before entry: it sits over the capsule.
        if not self.flags["les"] and (alt > c.les_altitude or ph == "entry"):
            self.eject_escape_tower()

        # Back in the air with the mission still ahead of us: the orbit was never made
        # (fly mission 1 planned TMI on the way down and hit the ground with the node up).
        if ph not in ("ascent", "entry") and o.body.name == "Kerbin" and alt < 70_000 and v.flight(o.body.reference_frame).vertical_speed < -50:
            self.event("abort", reason="fell back into the atmosphere", altitude=round(alt), periapsis=round(o.periapsis_altitude))
            self.go("done")
            return

        if ph == "ascent":
            self.stage_if_needed(throttle)
            at_target = o.apoapsis_altitude >= c.parking_altitude - 1_500
            # Once begun, the separation sequence runs to completion whatever the
            # apoapsis does (drag took it under the threshold half-way through once).
            if "booster_sep" in self.flags and not self.on_upper_stage or at_target and not self.on_upper_stage:
                # The booster has done its job early. Never coast on it (no gimbal, and
                # the wheels cannot turn 100 t) and never separate it under thrust (it
                # rams the upper stage: shakedown 2). MECO, let it settle, decouple,
                # then bring the upper stage on line.
                seq = self.flags.setdefault("booster_sep", {"t": self.sc.ut, "step": 0})
                elapsed = self.sc.ut - seq["t"]
                if seq["step"] == 0:
                    ctl.throttle = 0.0
                    self.event("meco", by="computer", reason="apoapsis reached on the booster", apoapsis=round(o.apoapsis_altitude))
                    seq["step"] = 1
                elif seq["step"] == 1 and elapsed > 1.5 and v.thrust < 1.0:
                    ctl.activate_next_stage()
                    self.last_stage_ut = self.sc.ut
                    self.event("stage", now=ctl.current_stage, reason="booster separation")
                    seq["step"] = 2
                elif seq["step"] == 2 and elapsed > 3.0:
                    while not self.on_upper_stage:
                        ctl.activate_next_stage()
                    self.last_stage_ut = self.sc.ut
                    self.flags["upper"] = True
                    self.event("stage", now=ctl.current_stage, reason="upper stage on line")
                return
            # Bob cuts the engine as the bar shrinks; the computer only backs him up.
            if o.apoapsis_altitude >= c.parking_altitude + 3_000:
                ctl.throttle = 0.0
                self.event("meco", by="computer backstop", apoapsis=round(o.apoapsis_altitude))
                self.go("coast_to_apoapsis")
            elif at_target and throttle < 0.05:
                ctl.throttle = 0.0
                self.event("meco", by="Bob", apoapsis=round(o.apoapsis_altitude))
                self.go("coast_to_apoapsis")
            return

        if ph == "coast_to_apoapsis":
            self.deploy_panels_if_clear(alt)
            # Plan the burn once the air is thin enough not to move the apoapsis much;
            # the burn phase handles alignment, lead time and warp from there.
            if alt > 60_000 or o.time_to_apoapsis < 90:
                self.node = self.circularization_node()
                self.after_burn = "plan_tmi"
                self.go("burn")
            return

        if ph == "burn":
            self.burn_logic(truth, throttle)
            return

        if ph == "plan_tmi":
            self.deploy_panels_if_clear(alt)
            try:
                self.node = self.solve_free_return()
            except RuntimeError as e:
                self.event("abort", reason=str(e))
                self.go("done")
                return
            self.after_burn = "coast_to_mun"
            self.go("burn")
            return

        if ph == "coast_to_mun":
            if o.body.name == "Mun":
                self.event("soi", body="Mun", periapsis=round(o.periapsis_altitude))
                self.go("mun_flyby")
                return
            t_soi = o.time_to_soi_change
            encounter = not math.isnan(t_soi) and t_soi > 0 and o.next_orbit is not None and o.next_orbit.body.name == "Mun"
            corrections = self.flags.get("corrections_out", 0)
            # Two kinds of look. The free-return corridor is 2 m/s wide and a crew's
            # burn is good to ten (fly mission 3 left no encounter at all: apoapsis
            # 13,400 km against the Mun's 12,000), so a lost encounter is corrected at
            # once, while it is cheap, up to twice. With an encounter, one look a third
            # of the way out: is the return still on target?
            look = None
            if not encounter:
                if corrections >= 2:
                    self.event("abort", reason="no Mun encounter after corrections", apoapsis=round(min(o.apoapsis_altitude, ESCAPE_APOAPSIS)))
                    self.go("done")
                    return
                look = "lost_encounter"
            elif not self.flags.get("midcourse_looked"):
                if t_soi < 0.66 * self.flags.setdefault("t_soi0", t_soi):
                    look = "midcourse"
            if look:
                if look == "midcourse":
                    self.flags["midcourse_looked"] = True
                mun, back = self.patches(o)
                off_target = (
                    back is None or mun is None
                    or abs(back - c.return_periapsis) > c.correction_tolerance
                    or abs(mun - c.mun_periapsis) > 3 * c.correction_tolerance
                )
                self.event("midcourse_check", look=look, mun_periapsis=mun, return_periapsis=back, correcting=off_target)
                if off_target:
                    node = self.correction_node(score_mun=True, max_dv=60.0 if encounter else 150.0, span=20.0 if encounter else 40.0)
                    if node is not None:
                        self.flags["corrections_out"] = corrections + 1
                        self.flags.pop("t_soi0", None)  # the encounter moves; measure the leg afresh
                        self.node, self.after_burn = node, "coast_to_mun"
                        self.go("burn")
                        return
                    if not encounter:
                        self.event("abort", reason="no correction restores the Mun encounter")
                        self.go("done")
                        return
            if encounter and t_soi > c.warp_lead + 30:
                aligned = abs(truth["pitch_error_deg"]) < 10 and abs(truth["yaw_error_deg"]) < 10
                if aligned:
                    target_ut = self.sc.ut + (t_soi * 0.34 if not self.flags.get("midcourse_looked") else t_soi) - c.warp_lead
                    self.warp_to(max(target_ut, self.sc.ut + 60))
            return

        if ph == "mun_flyby":
            if o.body.name != "Mun":
                self.flags["flyby_done"] = True
                self.event("soi", body=o.body.name, periapsis=round(o.periapsis_altitude), apoapsis=round(min(o.apoapsis_altitude, ESCAPE_APOAPSIS)))
                self.go("return_coast")
                return
            t_soi = o.time_to_soi_change
            if o.time_to_periapsis < t_soi and o.time_to_periapsis > c.warp_lead + 30:
                self.warp_to(self.sc.ut + o.time_to_periapsis - c.warp_lead)
            elif o.time_to_periapsis < 5:
                self.event("mun_periapsis", altitude=round(o.periapsis_altitude), speed=round(o.speed))
                if t_soi > c.warp_lead + 30:
                    self.warp_to(self.sc.ut + t_soi - c.warp_lead + 60)
            elif o.time_to_periapsis > t_soi and t_soi > c.warp_lead + 30:
                self.warp_to(self.sc.ut + t_soi - c.warp_lead + 60)
            return

        if ph == "return_coast":
            # Two looks at the entry corridor: one right after the flyby, one inside the
            # last hour when a small burn moves the periapsis by little and precisely.
            t_peri = o.time_to_periapsis
            look = None
            if not self.flags.get("corrected_back") and t_peri > 1_800:
                look, tolerance = "corrected_back", c.correction_tolerance
            elif not self.flags.get("trimmed_back") and 600 < t_peri < 3_000:
                look, tolerance = "trimmed_back", 3_000.0
            if look:
                self.flags[look] = True
                off = abs(o.periapsis_altitude - c.return_periapsis) > tolerance
                self.event("return_check", look=look, periapsis=round(o.periapsis_altitude), correcting=off)
                if off:
                    # Survival burn: worth most of what is left in the tank.
                    node = self.correction_node(score_mun=False, max_dv=250.0 if look == "corrected_back" else 30.0)
                    if node is not None:
                        self.node, self.after_burn = node, "return_coast"
                        self.go("burn")
                        return
            if alt < c.entry_altitude and v.flight(o.body.reference_frame).vertical_speed < 0:
                self.go("entry")
                return
            # Warp down in shrinking steps until the air is a minute away.
            if alt > 150_000 and o.time_to_periapsis > 300:
                self.warp_to(self.sc.ut + max(60.0, 0.7 * (o.time_to_periapsis - 240)))
            return

        if ph == "entry":
            if not self.flags["abort"]:
                ctl.abort = True
                self.flags["abort"] = True
                self.flags["abort_ut"] = self.sc.ut
                self.event("action_group", group="abort", purpose="separate capsule, arm parachutes")
            elif not self.flags.get("chutes_checked") and self.sc.ut - self.flags["abort_ut"] > 3.0:
                # The action group separates the capsule; the chutes are the computer's.
                self.flags["chutes_checked"] = True
                self.v = self.sc.active_vessel
                self.set_chute_altitudes()
            elif self.flags.get("chutes_checked") and not self.flags.get("main_released") and alt < 15_000 and self.tick % 10 == 0:
                self.release_chutes(alt)
            if self.tick % 40 == 0:
                # The capsule alone runs its wheels off one battery; the panels left with
                # the Poodle. Low charge: hands off, the heat shield end is the stable end.
                ec, ec_max = v.resources.amount("ElectricCharge"), v.resources.max("ElectricCharge")
                if ec_max > 0 and ec / ec_max < 0.2 and not self.flags.get("power_low"):
                    self.flags["power_low"] = True
                    self.event("power_low", charge=round(ec), of=round(ec_max), vessel=v.name, parts=len(v.parts.all), action="attitude hands off")
            if v.situation in (self.sc.VesselSituation.landed, self.sc.VesselSituation.splashed):
                self.event("landed", situation=str(v.situation).split(".")[-1], altitude=round(alt))
                self.go("done")
            elif self.tick % 20 == 0 and (v.crew_count == 0 or not v.parts.all):
                self.event("abort", reason="vessel lost", altitude=round(alt), parts=len(v.parts.all), crew=v.crew_count)
                self.go("done")
            return

    def burn_logic(self, truth, throttle):
        c = self.c
        v = self.v
        node = self.node
        try:
            remaining = node.remaining_delta_v
        except RuntimeError as e:
            # KSP drops the node when the vessel is lost or the game reloads under us
            # (fly mission 1 hit the ground with a node up). End with a summary, not a
            # traceback.
            self.event("abort", reason="maneuver node lost", detail=str(e).splitlines()[0][:80], altitude=round(truth["altitude"]))
            self.go("done")
            return
        self.deploy_panels_if_clear(truth["altitude"])
        initial = self.flags.get("burn_dv0", remaining)
        if self.sc.ut > node.ut + 240 and remaining > 0.9 * initial:
            # Long past the node with nothing burned: the ship cannot hold the vector
            # or the engine will not light. Do not hang here for ever.
            self.event("abort", reason="burn never progressed", remaining=round(remaining, 1), off_deg=round(truth["off_deg"], 1))
            self.go("done")
            return
        if not self.burn_started:
            lead = self.burn_seconds(remaining) / 2
            t_go = node.ut - self.sc.ut - lead
            aligned = abs(truth["pitch_error_deg"]) < 2 and abs(truth["yaw_error_deg"]) < 2
            if t_go > c.warp_lead + 20 and aligned:
                self.warp_to(node.ut - lead - c.warp_lead)
            elif t_go <= 0 and aligned:
                self.burn_started = True
                self.flags["burn_dv0"] = remaining
                self.event("burn_start", dv=round(remaining, 1), seconds=round(2 * lead, 1))
            elif t_go <= -30:
                self.burn_started = True  # late is better than never
                self.flags["burn_dv0"] = remaining
                self.event("burn_start", dv=round(remaining, 1), late=True)
            return
        # No staging here: the upper stage is the last engine, and a freshly relit
        # throttle reads zero thrust for a tick (autopilot mission 5 jettisoned the
        # Poodle that way, mid-correction).
        along = remaining if getattr(self, "burn_along", None) is None else self.burn_along
        # Overshoot is judged on the velocity still to be gained along the burn attitude.
        # The remaining vector's magnitude also grows with every degree the nose wanders
        # off the vector while burning; that is lateral error for the correction burns,
        # not a reason to stop (fly mission 1 was cut at 374 m/s to go that way).
        least = self.flags["burn_min"] = min(self.flags.get("burn_min", along), along)
        # Done when Bob has let go with little left, or a computer backstop trips.
        by = None
        if along < 2.0 and throttle < 0.1:
            by = "Bob"
        elif along <= 0.0:
            by = "computer backstop: velocity-to-be-gained reversed"
        elif remaining < 0.3:
            by = "computer backstop: cutoff"
        elif along > least + 3.0:
            by = "computer backstop: overshoot"
        if by:
            v.control.throttle = 0.0
            self.event("burn_end", remaining=round(remaining, 2), by=by)
            node.remove()
            self.node = None
            self.burn_started = False
            self.burn_direction = None
            self.burn_along = None
            self.flags.pop("burn_min", None)
            self.flags.pop("burn_dv0", None)
            self.engine_permitted = True
            nxt = self.after_burn
            self.after_burn = None
            self.go(nxt)

    # --- helpers -----------------------------------------------------------------------

    def stage_if_needed(self, throttle):
        v = self.v
        ctl = v.control
        ut = self.sc.ut
        if self.on_upper_stage or ut - self.last_stage_ut < 1.5:
            return
        # Flameout means no thrust for half a second at open throttle, not one reading.
        if throttle > 0 and v.thrust < 1.0:
            since = self.flags.setdefault("no_thrust_since", ut)
            if ut - since >= 0.5:
                ctl.activate_next_stage()
                self.last_stage_ut = ut
                self.flags.pop("no_thrust_since", None)
                if self.on_upper_stage:
                    self.flags["upper"] = True
                self.event("stage", now=ctl.current_stage)
        else:
            self.flags.pop("no_thrust_since", None)

    def roll_damping(self):
        """The computer holds roll rate at zero. Nobody flies roll: a rolling ship swaps
        Jeb's needle with Bill's, and that coupling is the one interaction between the
        two attitude seats worth removing. Sign established in flight (autopilot
        mission 3): +roll_damping x (angular velocity about the nose, kRPC vessel frame)
        damps; the opposite sign spun the ship to 198 deg/s in three seconds."""
        v = self.v
        frame = v.orbit.body.non_rotating_reference_frame
        w = self.sc.transform_direction(v.angular_velocity(frame), frame, v.reference_frame)
        rate = math.degrees(w[1])  # about the nose axis, deg/s
        self.roll_rate = rate
        return float(np.clip(self.c.roll_damping * rate, -1, 1))

    def eject_escape_tower(self):
        ctl = self.v.control
        ctl.set_action_group(1, True)
        self.flags["les"] = True
        time.sleep(0.5)
        still = [p.title for p in self.v.parts.all if "escape" in p.title.lower()]
        if still:
            # The group did not take (already toggled, or the tower is on its own
            # stage): fire the tower's own decoupler/engine directly.
            for p in self.v.parts.all:
                if "escape" in p.title.lower():
                    if p.engine is not None:
                        p.engine.active = True
                    if p.decoupler is not None:
                        p.decoupler.decouple()
            time.sleep(0.5)
            still = [p.title for p in self.v.parts.all if "escape" in p.title.lower()]
        self.event("action_group", group=1, purpose="eject escape tower", ejected=not still)

    # Parachutes go through the generic part-module interface. kRPC's Parachute class
    # throws on every call when the RealChute mod is installed, even for stock chutes
    # (autopilot missions 4 and 7 splashed down with every chute stowed).
    def parachutes(self):
        """[(part, ModuleParachute module, is_drogue)] on the current vessel."""
        out = []
        try:
            for p in self.v.parts.all:
                for m in p.modules:
                    if m.name == "ModuleParachute":
                        out.append((p, m, "drogue" in p.title.lower()))
                        break
        except Exception as e:
            self.event("parachutes", error=str(e)[:80])
        return out

    @staticmethod
    def deploy_event(m):
        return next((e for e in m.event_list if e.gui_name == "Deploy Chute"), None)

    @staticmethod
    def chute_field(m, name):
        try:
            return next((f.value for f in m.field_list if f.gui_name == name), None)
        except Exception:
            return None

    def chute_status(self, m):
        """'stowed', 'released' (Deploy Chute already triggered) or 'error'."""
        try:
            return "stowed" if self.deploy_event(m) is not None else "released"
        except Exception:
            return "error"

    def chute_safe(self, m):
        return self.chute_field(m, "Safe to deploy?") == "Safe"

    def set_chute_altitudes(self):
        """After Abort: full deployment altitudes, drogue drogue_altitude, mains
        main_altitude. Nothing is released here; release_chutes does that on the way down.
        The module's field list can be empty for a few seconds after separation, so the
        read-back is reported separately from the set."""
        c = self.c
        chutes = self.parachutes()
        states = {}
        for p, m, drogue in chutes:
            try:
                m.set_field_float("Altitude", c.drogue_altitude if drogue else c.main_altitude)
                result = "set"
            except Exception as e:
                result = f"set error: {str(e)[:40]}"
            states[p.title] = f"{result} {self.chute_status(m)} alt={self.chute_field(m, 'Altitude')} safe={self.chute_field(m, 'Safe to deploy?')}"
        self.event("parachutes", count=len(chutes), drogue_altitude=c.drogue_altitude, main_altitude=c.main_altitude, states=states)
        if not chutes:
            self.event("abort", reason="no parachutes on the vessel after Abort")

    def release_chutes(self, alt):
        """Drogue first, then mains. Each group is released once the module reports it
        safe below its release altitude, or unconditionally 2 km lower. A released stock
        chute semi-deploys at its minimum pressure and opens fully at its Altitude field."""
        c = self.c
        for group, release_alt in (("drogue", c.drogue_altitude + 5_000), ("main", c.main_altitude + 2_000)):
            flag = f"{group}_released"
            if self.flags.get(flag) or alt > release_alt:
                continue
            chutes = [(p, m) for p, m, d in self.parachutes() if d == (group == "drogue")]
            if not chutes:
                self.flags[flag] = True
                self.event("parachutes", group=group, released=[], reason="none on the vessel", altitude=round(alt))
                continue
            safe = all(self.chute_safe(m) for _, m in chutes)
            if not safe and alt > release_alt - 2_000:
                continue
            released = []
            for p, m in chutes:
                if self.chute_status(m) == "released":
                    continue
                try:  # a failed status read is no reason to keep the chute stowed
                    e = self.deploy_event(m)
                    if e is None:
                        m.trigger_event("Deploy Chute")
                    else:
                        e.trigger()
                    released.append(p.title)
                except Exception as e:
                    released.append(f"{p.title}: error {str(e)[:40]}")
            self.flags[flag] = True
            self.event("parachutes", group=group, released=released, safe=safe, altitude=round(alt),
                       status={p.title: self.chute_status(m) for p, m in chutes})

    def deploy_panels_if_clear(self, alt):
        if alt > 70_000 and not self.flags["panels"]:
            self.v.control.lights = True
            self.flags["panels"] = True
            self.event("action_group", group="lights", purpose="deploy solar panels")

    def hands_off(self):
        """Nothing stale may be on the controls while nobody is watching them: before a
        warp, and before a solver that blocks the loop for half a minute (autopilot
        mission 5 spun up during one). Sticks to zero, and the ship holds its attitude
        under SAS until the loop is back; still one writer, since the crew's sticks are
        zero for the duration."""
        ctl = self.v.control
        ctl.throttle, ctl.pitch, ctl.yaw, ctl.roll = 0.0, 0.0, 0.0, 0.0
        ctl.sas = True

    def hands_on(self):
        self.v.control.sas = False
        self.previous = {}

    def warp_to(self, ut):
        if ut <= self.sc.ut + 5:
            return
        if self.v.orbit.body.name == "Kerbin" and self.v.flight().mean_altitude < 70_000:
            return  # physics warp in air lets the aerodynamics fly the ship; wait for vacuum
        self.hands_off()
        self.event("warp", to=round(ut, 1), seconds=round(ut - self.sc.ut))
        self.sc.warp_to(ut)
        self.hands_on()

    def summary(self):
        o = self.v.orbit
        phases = [e["to"] for e in self.events if e["event"] == "phase"]
        return {
            "crew": self.crew.name,
            "ticks": self.tick,
            "wall_seconds": round(time.time() - self.t_wall0),
            "phases": phases,
            "reached_mun": any(e.get("body") == "Mun" for e in self.events if e["event"] == "soi"),
            "free_return": next((e.get("free_return") for e in self.events if e.get("purpose") == "tmi"), None),
            "mun_periapsis": next((e.get("altitude") for e in self.events if e["event"] == "mun_periapsis"), None),
            "landed": any(e["event"] == "landed" for e in self.events),
            "max_g": round(self.flags.get("max_g", 0.0), 1),
            "final_body": o.body.name,
            "final_periapsis": round(o.periapsis_altitude),
            "monopropellant": round(self.v.resources.amount("MonoPropellant"), 1),
            "seat_timeouts": getattr(self.crew, "timeouts", {}),
            "events": len(self.events),
        }
