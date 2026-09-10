"""A small 2D rocket on a Kerbin-sized planet.

Point mass plus one rotational degree of freedom. Aerodynamics are deliberately
destabilising (no fins), so a rocket that nobody steers falls over once dynamic pressure
builds. Gusts are seeded so every episode is reproducible. Numbers are plausible, not
calibrated to any real vehicle or to KSP's own physics.
"""

import math
from dataclasses import dataclass

import numpy as np

from ..vehicle import Command, Telemetry

G0 = 9.81
PLANET_RADIUS = 600_000.0  # Kerbin
MU = G0 * PLANET_RADIUS**2
SCALE_HEIGHT = 5_600.0
SEA_LEVEL_DENSITY = 1.225
ESCAPE_APOAPSIS = 10 * PLANET_RADIUS  # reported when the trajectory is unbound


@dataclass(frozen=True)
class Stage:
    dry_mass: float
    fuel_mass: float
    thrust: float
    isp: float

    @property
    def mass_flow(self):
        return self.thrust / (self.isp * G0)


# A sounding rocket, not an orbital one: about 3.5 km/s of vacuum delta-v, so a perfect
# vertical flight reaches a few hundred kilometres and a bad one reaches the ground.
DEFAULT_STAGES = (
    Stage(dry_mass=1_200, fuel_mass=2_000, thrust=90_000, isp=260),
    Stage(dry_mass=400, fuel_mass=300, thrust=25_000, isp=300),
)

# Same booster, an upper stage with a long, gentle burn: about 4.2 km/s. Enough to orbit
# if the pilot follows the turn; the sounding rocket cannot, whatever it does. There is
# no coast or circularisation burn (the fly has no throttle), so burnout is the orbit.
ORBITAL_STAGES = (
    Stage(dry_mass=1_200, fuel_mass=2_000, thrust=90_000, isp=260),
    Stage(dry_mass=400, fuel_mass=550, thrust=15_000, isp=320),
)

VEHICLES = {"sounding": DEFAULT_STAGES, "orbital": ORBITAL_STAGES}


@dataclass(frozen=True)
class RocketConfig:
    stages: tuple[Stage, ...] = DEFAULT_STAGES
    drag_area: float = 0.6  # Cd * A in m^2
    control_authority: float = 0.35  # rad/s^2 at full steer
    aero_instability: float = 2.5e-5  # rad/s^2 per Pa of dynamic pressure, per sin(aoa)
    angular_damping: float = 0.6  # 1/s
    gust_std: float = 0.06  # rad/s^2, white torque noise
    tumble_deg: float = 90.0
    timeout: float = 400.0
    dt: float = 0.05


def vertical_target(altitude):
    """Default guidance: straight up. Maximises apoapsis and asks only for stabilisation."""
    return 0.0


def turn_profile(start_m, end_m, end_pitch_deg):
    """Guidance that pitches linearly with altitude from vertical at `start_m` to
    `end_pitch_deg` at `end_m`, then holds."""

    def target(altitude):
        if altitude < start_m:
            return 0.0
        return min(end_pitch_deg, end_pitch_deg * (altitude - start_m) / (end_m - start_m))

    target.__name__ = f"turn_{start_m:.0f}_{end_m:.0f}_{end_pitch_deg:.0f}"
    return target


# Chosen by sweeping profiles with the PD autopilot on the orbital vehicle (docs/results.md):
# the nose ends 15 degrees below the horizon so burnout lands near apoapsis.
gravity_turn_target = turn_profile(1_000, 80_000, 105.0)


class Rocket2D:
    def __init__(self, config=RocketConfig(), *, seed=0, target=vertical_target):
        self.c = config
        self.seed = seed
        self.target = target
        self.reset()

    def reset(self):
        self.rng = np.random.default_rng(self.seed)
        self.t = 0.0
        # Inertial frame with the planet's centre at the origin; the pad is at (0, R).
        # theta is the nose angle from *local* vertical, positive toward local east
        # (+x at the pad), so the instrument and guidance never see the frame.
        self.px = 0.0
        self.py = PLANET_RADIUS
        self.vx = 0.0
        self.vy = 0.0
        self.theta = 0.0
        self.omega = 0.0
        self.stage_index = 0
        self.fuel = self.c.stages[0].fuel_mass
        self.max_altitude = 0.0
        self.max_apoapsis = 0.0
        self.failure = None
        self.done = False
        return self.telemetry()

    # --- physics -----------------------------------------------------------------

    @property
    def radius(self):
        return math.hypot(self.px, self.py)

    @property
    def altitude(self):
        return self.radius - PLANET_RADIUS

    def local_frame(self):
        """Unit vectors (up, east) at the rocket's position."""
        r = self.radius
        ux, uy = self.px / r, self.py / r
        return (ux, uy), (uy, -ux)

    def gravity(self):
        return MU / self.radius**2

    def density(self):
        return SEA_LEVEL_DENSITY * math.exp(-max(self.altitude, 0.0) / SCALE_HEIGHT)

    def mass(self):
        remaining = self.c.stages[self.stage_index :]
        return sum(s.dry_mass for s in remaining) + sum(
            s.fuel_mass for s in remaining[1:]
        ) + self.fuel

    def orbit(self):
        """Osculating orbit: (apoapsis altitude, periapsis altitude). Unbound
        trajectories report ESCAPE_APOAPSIS. Vertical flight has zero angular
        momentum, so this reduces to the radial vis-viva apex."""
        r = self.radius
        energy = 0.5 * (self.vx**2 + self.vy**2) - MU / r
        if energy >= 0:
            return ESCAPE_APOAPSIS, self.altitude
        a = -MU / (2 * energy)
        h = self.px * self.vy - self.py * self.vx
        e = math.sqrt(max(0.0, 1 + 2 * energy * h * h / (MU * MU)))
        apoapsis = a * (1 + e) - PLANET_RADIUS
        periapsis = a * (1 - e) - PLANET_RADIUS
        return max(self.altitude, apoapsis), periapsis

    def apoapsis(self):
        return self.orbit()[0]

    def step(self, command: Command):
        if self.done:
            return self.telemetry()
        cmd = command.clipped()
        c = self.c
        dt = c.dt
        stage = c.stages[self.stage_index]

        # Propulsion and staging.
        throttle = cmd.throttle if self.fuel > 0 else 0.0
        burn = min(self.fuel, throttle * stage.mass_flow * dt)
        thrust = stage.thrust * (burn / (stage.mass_flow * dt)) if burn > 0 else 0.0
        self.fuel -= burn
        if self.fuel <= 0 and self.stage_index + 1 < len(c.stages):
            self.stage_index += 1
            self.fuel = c.stages[self.stage_index].fuel_mass

        # Translational dynamics in the inertial frame.
        (ux, uy), (ex, ey) = self.local_frame()
        m = self.mass()
        speed = math.hypot(self.vx, self.vy)
        q = 0.5 * self.density() * speed**2
        drag = q * c.drag_area
        tx = math.cos(self.theta) * ux + math.sin(self.theta) * ex
        ty = math.cos(self.theta) * uy + math.sin(self.theta) * ey
        g = self.gravity()
        ax = thrust * tx / m - g * ux
        ay = thrust * ty / m - g * uy
        if speed > 0:
            ax -= drag * self.vx / speed / m
            ay -= drag * self.vy / speed / m

        # Rotational dynamics: control, destabilising aero moment, damping, gusts.
        alpha = c.control_authority * cmd.steer
        if speed > 1.0:
            v_up = self.vx * ux + self.vy * uy
            v_east = self.vx * ex + self.vy * ey
            aoa = self.theta - math.atan2(v_east, v_up)
            alpha += c.aero_instability * q * math.sin(aoa)
        alpha -= c.angular_damping * self.omega
        alpha += self.rng.normal(0.0, c.gust_std)

        self.vx += ax * dt
        self.vy += ay * dt
        self.px += self.vx * dt
        self.py += self.vy * dt
        self.omega += alpha * dt
        self.theta += self.omega * dt
        self.t += dt

        # Sitting on the pad before liftoff is not a crash.
        if self.altitude < 0:
            v_up = self.vx * ux + self.vy * uy
            if self.t < 2.0 and v_up <= 0:
                self.px, self.py = ux * PLANET_RADIUS, uy * PLANET_RADIUS
                self.vx, self.vy = 0.0, 0.0
            else:
                self.failure = "crash"
        # Attitude lost relative to guidance, not to the vertical: a turn is not a tumble.
        if abs(self.target(self.altitude) - math.degrees(self.theta)) > c.tumble_deg:
            self.failure = "tumble"

        self.max_altitude = max(self.max_altitude, self.altitude)
        self.max_apoapsis = max(self.max_apoapsis, self.apoapsis())
        # Burnout fixes the orbit; there is nothing left for a pilot to do.
        out_of_fuel = self.fuel <= 0 and self.stage_index + 1 >= len(c.stages)
        self.done = bool(self.failure or self.t >= c.timeout or out_of_fuel)
        return self.telemetry()

    # --- reporting -----------------------------------------------------------------

    def telemetry(self):
        pitch = math.degrees(self.theta)
        altitude = self.altitude
        target = self.target(altitude)
        (ux, uy), (ex, ey) = self.local_frame()
        apoapsis, periapsis = self.orbit()
        return Telemetry(
            time=round(self.t, 3),
            altitude=altitude,
            vertical_speed=self.vx * ux + self.vy * uy,
            apoapsis=apoapsis,
            steer_error_deg=target - pitch,
            pitch_deg=pitch,
            target_pitch_deg=target,
            fuel_fraction=self.fuel / self.c.stages[self.stage_index].fuel_mass,
            stage=self.stage_index,
            failure=self.failure,
            done=self.done,
            extra={
                "periapsis": periapsis,
                "bound": apoapsis < ESCAPE_APOAPSIS,
                "horizontal_speed": self.vx * ex + self.vy * ey,
            },
        )
