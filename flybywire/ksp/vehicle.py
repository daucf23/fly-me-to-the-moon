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


@dataclass(frozen=True)
class KerbalConfig:
    address: str = "127.0.0.1"
    rpc_port: int = 50000
    stream_port: int = 50001
    craft: str | None = None  # VAB craft name to launch when a revert is not possible
    launch_site: str = "LaunchPad"
    dt: float = 0.05  # game seconds per tick in lockstep mode
    lockstep: bool = False  # pause KSP while the brain thinks
    pitch_hold: bool = True
    pitch_gain: float = 0.05  # stick per degree
    pitch_damping: float = 0.4  # stick per degree/tick
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

    def _to_pad(self):
        v = None
        try:
            if self.conn.krpc.current_game_scene == self.scenes.flight:
                v = self.sc.active_vessel
                if v.situation == self.situations.pre_launch and self.flights == 0:
                    return v
        except Exception:
            v = None
        if self.sc.can_revert_to_launch:
            self.sc.revert_to_launch()
            return self._wait_for_pad()
        if self.c.craft:
            self.sc.launch_vessel("VAB", self.c.craft, self.c.launch_site)
            return self._wait_for_pad()
        raise RuntimeError(
            "Cannot revert to launch and no --craft given; put a vessel on the pad first"
        )

    def reset(self):
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
        self.s = {
            "ut": self._stream(getattr, self.sc, "ut"),
            "altitude": self._stream(getattr, flight, "mean_altitude"),
            "vertical_speed": self._stream(getattr, flight, "vertical_speed"),
            "speed": self._stream(getattr, flight, "speed"),
            "q": self._stream(getattr, flight, "dynamic_pressure"),
            "pitch": self._stream(getattr, flight, "pitch"),
            "heading": self._stream(getattr, flight, "heading"),
            "apoapsis": self._stream(getattr, v.orbit, "apoapsis_altitude"),
            "situation": self._stream(getattr, v, "situation"),
            "thrust": self._stream(getattr, v, "thrust"),
            "stage": self._stream(getattr, self.control, "current_stage"),
            "fuel": self._stream(v.resources.amount, "LiquidFuel"),
            "up": self._stream(self.sc.transform_direction, (1.0, 0.0, 0.0), surface, body),
            "east": self._stream(self.sc.transform_direction, (0.0, 0.0, 1.0), surface, body),
        }
        self.fuel_max = max(v.resources.max("LiquidFuel"), 1e-6)
        self.t0 = self.s["ut"]()
        self.pad_altitude = self.s["altitude"]()
        self.max_altitude = 0.0  # above the pad
        self.max_apoapsis = 0.0
        self.lifted_off = False
        self.last_stage_ut = -1e9
        self.previous_pitch_error = None
        self.failure = None
        self.done = False
        self.flights += 1
        self.control.throttle = 1.0
        self.control.activate_next_stage()
        self.last_stage_ut = self.s["ut"]()
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
        self.control.yaw = -cmd.steer if self.c.invert_yaw else cmd.steer
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
        self._stage_if_needed(cmd.throttle)
        return self.telemetry()

    def _stage_if_needed(self, throttle):
        ut = self.s["ut"]()
        if (
            throttle > 0
            and self.s["thrust"]() < 1.0
            and self.s["fuel"]() > 0.5
            and ut - self.last_stage_ut > self.c.stage_cooldown
            and self.s["stage"]() > 0
        ):
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
        if altitude > self.pad_altitude + 5:
            self.lifted_off = True
        self.max_altitude = max(self.max_altitude, altitude - self.pad_altitude)
        self.max_apoapsis = max(self.max_apoapsis, apoapsis)
        landed = situation in (self.situations.landed, self.situations.splashed)
        if self.lifted_off and landed:
            self.failure = "crash"
        if tilt > self.c.tumble_deg:
            self.failure = "tumble"
        spent = fuel <= 0.01 and thrust < 1.0
        self.done = bool(self.failure or spent or t >= self.c.timeout)
        target = self.target(altitude - self.pad_altitude)
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
                "pitch_error_deg": pitch_error,
                "heading": self.s["heading"](),
                "speed": self.s["speed"](),
                "dynamic_pressure": self.s["q"](),
                "thrust": thrust,
                "situation": str(situation).split(".")[-1],
            },
        )
