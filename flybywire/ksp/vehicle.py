"""Kerbal Space Program through kRPC, wearing the same Vehicle interface as the 2D sim.

The fly has one stick, so it gets one axis: yaw. Pitch is held by a plain proportional
loop with no brain in it, and roll is left alone. Attitude errors are computed from the
target direction expressed in the vessel's own frame, so roll drift does not swap axes.

kRPC frames: the vessel frame has x to the right, y along the nose, z out of the bottom.
The surface frame has x up (zenith), y north, z east. kRPC control: yaw +1 is nose right,
pitch +1 is nose up (toward -z).
"""

import math
import time
from dataclasses import dataclass

from ..vehicle import Command, Telemetry

ESCAPE_APOAPSIS = 6_000_000.0  # reported for unbound trajectories, as in the 2D sim


@dataclass(frozen=True)
class KerbalConfig:
    address: str = "127.0.0.1"
    rpc_port: int = 50000
    stream_port: int = 50001
    craft: str | None = None  # VAB craft name to launch fresh (only if no quicksave)
    crew: tuple[str, ...] = ("Jebediah Kerman",)  # an empty pod has no control at all
    quicksave: str | None = None  # preferred reset: load this save (vessel on the pad, crewed)
    launch_site: str = "LaunchPad"
    dt: float = 0.05  # game seconds per tick in lockstep mode
    lockstep: bool = False  # pause KSP while the brain thinks
    pitch_hold: bool = True
    pitch_gain: float = 0.05  # stick per degree
    pitch_damping: float = 0.4  # stick per degree/tick
    # Control augmentation on the fly's axis, as on a real rocket: the pilot commands
    # attitude, a rate gyro damps. Big stacks have far more authority than the 2D sim.
    yaw_authority: float = 0.3  # fraction of full deflection the pilot may command
    yaw_damping: float = 0.03  # stick per degree/second of yaw-error rate
    tumble_deg: float = 90.0
    timeout: float = 600.0
    invert_yaw: bool = False
    invert_pitch: bool = False
    stage_cooldown: float = 1.5


def vertical_target(altitude):
    return 0.0


def gravity_turn_target(altitude):
    if altitude < 1_000:
        return 0.0
    return min(80.0, 80.0 * (altitude - 1_000) / 44_000)


class KerbalRocket:
    def __init__(self, config=KerbalConfig(), *, target=vertical_target):
        import krpc

        self.c = config
        self.target = target
        self.conn = krpc.connect(
            name="flybywire",
            address=config.address,
            rpc_port=config.rpc_port,
            stream_port=config.stream_port,
        )
        self.sc = self.conn.space_center
        self.scenes = self.conn.krpc.GameScene
        self.situations = self.sc.VesselSituation
        self.flights = 0
        self.streams = []

    # --- session -------------------------------------------------------------------

    def server(self):
        status = self.conn.krpc.get_status()
        return {"version": status.version, "address": self.c.address}

    def _clear_streams(self):
        for s in self.streams:
            try:
                s.remove()
            except Exception:
                pass
        self.streams = []

    def _stream(self, *args):
        s = self.conn.add_stream(*args)
        self.streams.append(s)
        return s

    def _wait_for_pad(self, timeout=90.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.conn.krpc.current_game_scene == self.scenes.flight:
                    v = self.sc.active_vessel
                    if v.situation == self.situations.pre_launch:
                        return v
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError("Vessel did not appear on the pad")

    def _staging_ready(self, v, timeout=8.0):
        """After Revert to Launch through kRPC, KSP does not rebuild the staging stack:
        the vessel sits on the pad reporting stage -1 (briefly a stale value first) and
        staging commands do nothing. Require a sane, stable reading."""
        deadline = time.monotonic() + timeout
        good = 0
        while time.monotonic() < deadline:
            try:
                controllable = v.control.state != self.sc.ControlState.none
                good = good + 1 if controllable and v.control.current_stage >= 0 else 0
            except Exception:
                good = 0
            if good >= 4:
                return True
            time.sleep(0.5)
        return False

    def _relaunch(self):
        """Reset the world for the next episode. Preferred: load a quicksave with a crewed
        vessel on the pad. Otherwise launch the named craft from the VAB. Nothing here
        recovers or reverts: reverting through kRPC leaves the staging broken, and
        recovering can strand crew that is still flying."""
        if self.c.quicksave:
            self.sc.load(self.c.quicksave)
        elif self.c.craft:
            self.sc.launch_vessel("VAB", self.c.craft, self.c.launch_site, list(self.c.crew), False)
        else:
            raise RuntimeError(
                "No controllable vessel on the pad and neither --quicksave nor --craft given"
            )
        v = self._wait_for_pad()
        if not self._staging_ready(v):
            raise RuntimeError("Vessel on the pad is not controllable (no crew or probe core?) or has dead staging")
        return v

    def _to_pad(self):
        try:
            if self.conn.krpc.current_game_scene == self.scenes.flight:
                v = self.sc.active_vessel
                if v.situation == self.situations.pre_launch and self.flights == 0:
                    if self._staging_ready(v, timeout=3.0):
                        return v
        except Exception:
            pass
        return self._relaunch()

    def reset(self, _retry=True):
        self._clear_streams()
        if self.c.lockstep:
            self.conn.krpc.paused = False
        self.vessel = v = self._to_pad()
        self.control = v.control
        self.control.sas = False
        self.control.rcs = False
        self.control.throttle = 0.0
        self.control.pitch = 0.0
        self.control.yaw = 0.0
        self.control.roll = 0.0
        surface = v.surface_reference_frame
        body = v.reference_frame
        flight = v.flight()
        # Speeds need a frame the vessel moves in; the default one is fixed to the vessel.
        moving = v.flight(v.orbit.body.reference_frame)
        self.s = {
            "ut": self._stream(getattr, self.sc, "ut"),
            "altitude": self._stream(getattr, flight, "mean_altitude"),
            "vertical_speed": self._stream(getattr, moving, "vertical_speed"),
            "speed": self._stream(getattr, moving, "speed"),
            "q": self._stream(getattr, flight, "dynamic_pressure"),
            "pitch": self._stream(getattr, flight, "pitch"),
            "heading": self._stream(getattr, flight, "heading"),
            "apoapsis": self._stream(getattr, v.orbit, "apoapsis_altitude"),
            "periapsis": self._stream(getattr, v.orbit, "periapsis_altitude"),
            "eccentricity": self._stream(getattr, v.orbit, "eccentricity"),
            "situation": self._stream(getattr, v, "situation"),
            "thrust": self._stream(getattr, v, "thrust"),
            "stage": self._stream(getattr, self.control, "current_stage"),
            "fuel": self._stream(v.resources.amount, "LiquidFuel"),
            "up": self._stream(self.sc.transform_direction, (1.0, 0.0, 0.0), surface, body),
            "east": self._stream(self.sc.transform_direction, (0.0, 0.0, 1.0), surface, body),
        }
        self.fuel_max = max(v.resources.max("LiquidFuel"), 1e-6)
        # Staging stops at the last stage that lights a real engine. Escape towers and
        # parachutes stay untouched: the rocket's business, but not this rocket's.
        engine_stages = [
            e.part.stage
            for e in v.parts.engines
            if e.part.stage >= 0 and "escape" not in e.part.title.lower()
        ]
        self.min_stage = min(engine_stages) if engine_stages else 0
        self.clamped = bool(v.parts.launch_clamps)
        self.t0 = self.s["ut"]()
        self.pad_altitude = self.s["altitude"]()
        self.max_altitude = 0.0  # above the pad
        self.max_apoapsis = 0.0
        self.lifted_off = False
        self.last_stage_ut = -1e9
        self.previous_pitch_error = None
        self.previous_yaw = None
        self.failure = None
        self.done = False
        self.flights += 1
        self.next_tick = time.monotonic()
        self.control.throttle = 1.0
        self.control.activate_next_stage()
        self.last_stage_ut = self.s["ut"]()
        # Ignition must actually happen; a vessel with dead staging just sits there.
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and self.s["thrust"]() < 1.0:
            time.sleep(0.2)
        if self.s["thrust"]() < 1.0:
            if _retry and self.c.craft:
                self._clear_streams()
                self.vessel = self._relaunch()
                self.flights -= 1
                return self.reset(_retry=False)
            raise RuntimeError("Ignition produced no thrust; the vessel has no control or dead staging")
        if self.c.lockstep:
            self.conn.krpc.paused = True
        return self.telemetry()

    def release(self):
        """Hand the vessel back to the player with SAS on; never touch saves."""
        try:
            if self.c.lockstep:
                self.conn.krpc.paused = False
            self.control.yaw = 0.0
            self.control.pitch = 0.0
            self.control.sas = True
        except Exception:
            pass
        self._clear_streams()

    # --- geometry --------------------------------------------------------------------

    def errors(self):
        """Yaw and pitch errors (degrees) from the nose to the target direction, in the
        vessel frame. Yaw + means the target is to the right; pitch + means it is above."""
        a = math.radians(self.target(self.s["altitude"]() - self.pad_altitude))
        ux, uy, uz = self.s["up"]()
        ex, ey, ez = self.s["east"]()
        dx = math.cos(a) * ux + math.sin(a) * ex
        dy = math.cos(a) * uy + math.sin(a) * ey
        dz = math.cos(a) * uz + math.sin(a) * ez
        yaw = math.degrees(math.atan2(dx, dy))
        pitch = math.degrees(math.atan2(-dz, dy))
        return yaw, pitch

    # --- vehicle interface -------------------------------------------------------------

    def step(self, command: Command):
        if self.done:
            return self.telemetry()
        cmd = command.clipped()
        yaw_error, pitch_error = self.errors()
        ut = self.s["ut"]()
        yaw_rate = 0.0
        if self.previous_yaw is not None and ut > self.previous_yaw[1]:
            yaw_rate = (yaw_error - self.previous_yaw[0]) / (ut - self.previous_yaw[1])
        self.previous_yaw = (yaw_error, ut)
        yaw = self.c.yaw_authority * cmd.steer + self.c.yaw_damping * yaw_rate
        yaw = max(-1.0, min(1.0, yaw))
        self.control.yaw = -yaw if self.c.invert_yaw else yaw
        if self.c.pitch_hold:
            rate = 0.0 if self.previous_pitch_error is None else pitch_error - self.previous_pitch_error
            self.previous_pitch_error = pitch_error
            pitch = self.c.pitch_gain * pitch_error + self.c.pitch_damping * rate
            pitch = max(-1.0, min(1.0, pitch))
            self.control.pitch = -pitch if self.c.invert_pitch else pitch
        self.control.throttle = cmd.throttle
        if self.c.lockstep:
            self.conn.krpc.paused = False
            time.sleep(self.c.dt)
            self.conn.krpc.paused = True
        else:
            # Real time: pace the loop to dt so a brainless pilot does not spin at kHz.
            now = time.monotonic()
            time.sleep(max(0.0, self.next_tick - now))
            self.next_tick = max(self.next_tick + self.c.dt, now)
        self._stage_if_needed(cmd.throttle)
        return self.telemetry()

    def _stage_if_needed(self, throttle):
        ut = self.s["ut"]()
        if ut - self.last_stage_ut < self.c.stage_cooldown or self.s["stage"]() <= self.min_stage:
            return
        thrust = self.s["thrust"]()
        if self.clamped:
            # Engines lit and spooled up: let go of the pad.
            available = self.vessel.available_thrust
            if available > 0 and thrust > 0.9 * available:
                self.control.activate_next_stage()
                self.last_stage_ut = ut
                self.clamped = bool(self.vessel.parts.launch_clamps)
            return
        if throttle > 0 and thrust < 1.0 and self.s["fuel"]() > 0.5:
            self.control.activate_next_stage()
            self.last_stage_ut = ut

    def telemetry(self):
        try:
            ut = self.s["ut"]()
            altitude = self.s["altitude"]()
            vs = self.s["vertical_speed"]()
            apoapsis = self.s["apoapsis"]()
            tilt = 90.0 - self.s["pitch"]()
            situation = self.s["situation"]()
            fuel = self.s["fuel"]()
            thrust = self.s["thrust"]()
            yaw_error, pitch_error = self.errors()
        except Exception as e:  # the vessel object is gone: it exploded or was recovered
            self.failure = self.failure or "crash"
            self.done = True
            return Telemetry(
                time=0.0, altitude=self.max_altitude, vertical_speed=0.0,
                apoapsis=self.max_apoapsis, steer_error_deg=0.0, pitch_deg=0.0,
                target_pitch_deg=0.0, fuel_fraction=0.0, stage=0, failure=self.failure,
                done=True, extra={"error": type(e).__name__},
            )
        t = ut - self.t0
        bound = self.s["eccentricity"]() < 1.0
        if not bound or apoapsis < 0:
            apoapsis = ESCAPE_APOAPSIS  # KSP reports a negative apoapsis for hyperbolae
        apoapsis = min(apoapsis, ESCAPE_APOAPSIS)  # and an astronomical one just short of e = 1
        if altitude > self.pad_altitude + 5:
            self.lifted_off = True
        self.max_altitude = max(self.max_altitude, altitude - self.pad_altitude)
        self.max_apoapsis = max(self.max_apoapsis, apoapsis)
        landed = situation in (self.situations.landed, self.situations.splashed)
        if self.lifted_off and landed:
            self.failure = "crash"
        target = self.target(altitude - self.pad_altitude)
        # Attitude lost relative to guidance, not to the vertical: a turn is not a tumble.
        if abs(tilt - target) > self.c.tumble_deg:
            self.failure = "tumble"
        # Spent: no thrust and either no fuel or nothing left that we are willing to stage.
        no_more_stages = int(self.s["stage"]()) <= self.min_stage and ut - self.last_stage_ut > 5.0
        spent = self.lifted_off and thrust < 1.0 and (fuel <= 0.01 or no_more_stages)
        self.done = bool(self.failure or spent or t >= self.c.timeout)
        return Telemetry(
            time=round(t, 3),
            altitude=altitude - self.pad_altitude,
            vertical_speed=vs,
            apoapsis=apoapsis,
            steer_error_deg=yaw_error,
            pitch_deg=tilt,
            target_pitch_deg=target,
            fuel_fraction=fuel / self.fuel_max,
            stage=int(self.s["stage"]()),
            failure=self.failure,
            done=self.done,
            extra={
                "ut": ut,
                "periapsis": self.s["periapsis"](),
                "bound": bound,
                "pitch_error_deg": pitch_error,
                "heading": self.s["heading"](),
                "speed": self.s["speed"](),
                "dynamic_pressure": self.s["q"](),
                "thrust": thrust,
                "situation": str(situation).split(".")[-1],
            },
        )
