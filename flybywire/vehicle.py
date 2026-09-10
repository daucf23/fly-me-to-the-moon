"""What every rocket, simulated or Kerbal, has to tell the mission loop."""

from dataclasses import asdict, dataclass, field


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
    steer_error_deg: float  # what the needle shows: + means the nose must move right
    pitch_deg: float  # tilt of the nose from vertical, for the record
    target_pitch_deg: float
    fuel_fraction: float
    stage: int
    failure: str | None = None  # None while flying; "crash" | "tumble" otherwise
    done: bool = False
    extra: dict = field(default_factory=dict)

    def json(self):
        return asdict(self)
