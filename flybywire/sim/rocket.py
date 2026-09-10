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


def gravity_turn_target(altitude):
    """Optional profile for later orbit attempts: vertical to 1 km, 80 degrees by 45 km."""
    if altitude < 1_000:
        return 0.0
    return min(80.0, 80.0 * (altitude - 1_000) / 44_000)


class Rocket2D:
    def __init__(self, config=RocketConfig(), *, seed=0, target=vertical_target):
        self.c = config
        self.seed = seed
        self.target = target
        self.reset()

    def reset(self):
        self.rng = np.random.default_rng(self.seed)
        self.t = 0.0
        self.x = 0.0
        self.y = 0.0
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

    def gravity(self):
        r = PLANET_RADIUS + max(self.y, 0.0)
        return G0 * (PLANET_RADIUS / r) ** 2

    def density(self):
        return SEA_LEVEL_DENSITY * math.exp(-max(self.y, 0.0) / SCALE_HEIGHT)

    def mass(self):
        remaining = self.c.stages[self.stage_index :]
        return sum(s.dry_mass for s in remaining) + sum(
            s.fuel_mass for s in remaining[1:]
        ) + self.fuel

    def apoapsis(self):
        """Altitude the rocket would coast to with the engine off. Radial vis-viva:
        the apex radius of a bound trajectory is -mu / specific orbital energy."""
        r = PLANET_RADIUS + max(self.y, 0.0)
        energy = 0.5 * (self.vx**2 + self.vy**2) - MU / r
        if energy >= 0:
            return ESCAPE_APOAPSIS
        return max(self.y, -MU / energy - PLANET_RADIUS)

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

        # Translational dynamics.
        m = self.mass()
        speed = math.hypot(self.vx, self.vy)
        q = 0.5 * self.density() * speed**2
        drag = q * c.drag_area
        ax = thrust * math.sin(self.theta) / m
        ay = thrust * math.cos(self.theta) / m - self.gravity()
        if speed > 0:
            ax -= drag * self.vx / speed / m
            ay -= drag * self.vy / speed / m

        # Rotational dynamics: control, destabilising aero moment, damping, gusts.
        alpha = c.control_authority * cmd.steer
        if speed > 1.0:
            flight_path = math.atan2(self.vx, self.vy)
            aoa = self.theta - flight_path
            alpha += c.aero_instability * q * math.sin(aoa)
        alpha -= c.angular_damping * self.omega
        alpha += self.rng.normal(0.0, c.gust_std)

        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.omega += alpha * dt
        self.theta += self.omega * dt
        self.t += dt

        # Sitting on the pad before liftoff is not a crash.
        if self.y < 0:
            if self.t < 2.0 and self.vy <= 0:
                self.y, self.vy = 0.0, 0.0
            else:
                self.failure = "crash"
        if abs(math.degrees(self.theta)) > c.tumble_deg:
            self.failure = "tumble"

        self.max_altitude = max(self.max_altitude, self.y)
        self.max_apoapsis = max(self.max_apoapsis, self.apoapsis())
        # Burnout fixes the apoapsis; there is nothing left for a pilot to do.
        out_of_fuel = self.fuel <= 0 and self.stage_index + 1 >= len(c.stages)
        self.done = bool(self.failure or self.t >= c.timeout or out_of_fuel)
        return self.telemetry()

    # --- reporting -----------------------------------------------------------------

    def telemetry(self):
        pitch = math.degrees(self.theta)
        target = self.target(self.y)
        return Telemetry(
            time=round(self.t, 3),
            altitude=self.y,
            vertical_speed=self.vy,
            apoapsis=self.apoapsis(),
            steer_error_deg=target - pitch,
            pitch_deg=pitch,
            target_pitch_deg=target,
            fuel_fraction=self.fuel / self.c.stages[self.stage_index].fuel_mass,
            stage=self.stage_index,
            failure=self.failure,
            done=self.done,
        )
