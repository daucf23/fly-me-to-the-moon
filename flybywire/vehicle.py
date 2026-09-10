"""What every rocket, simulated or Kerbal, has to tell the mission loop."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Command:
    steer: float = 0.0  # [-1, 1]; +1 rotates the nose toward +x (right on the panel)
    throttle: float = 1.0  # [0, 1]

    def clipped(self):
        return Command(
            steer=min(1.0, max(-1.0, float(self.steer))),
            throttle=min(1.0, max(0.0, float(self.throttle))),
        )


@dataclass(frozen=True)
class Telemetry:
    time: float
    altitude: float
    vertical_speed: float
    apoapsis: float
    pitch_deg: float  # angle of the nose from vertical; + leans toward +x
    target_pitch_deg: float
    fuel_fraction: float
    stage: int
    failure: str | None = None  # None while flying; "crash" | "tumble" otherwise
    done: bool = False

    @property
    def pitch_error_deg(self):
        return self.target_pitch_deg - self.pitch_deg

    def json(self):
        return asdict(self)
