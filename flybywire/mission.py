"""Ground control to Major Fly: the closed loop, with everything written down."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .instruments import black_panel, render_panel
from .reward import NONE, attitude_reinforcement, progress_reinforcement


@dataclass(frozen=True)
class MissionSettings:
    input: str = "panel"  # panel | black
    reward: str = "attitude"  # attitude | progress | off
    error_scale_deg: float = 10.0  # pitch error that draws the needle at full width
    goal_altitude: float = 70_000.0  # Kerbin's atmosphere ends here
    attitude_deadband_deg: float = 0.3
    progress_deadband_m: float = 20.0
    log_every: int = 1
    image_every: int = 20
    checkpoint: bool = True

    def __post_init__(self):
        if self.input not in ("panel", "black"):
            raise ValueError("input must be panel or black")
        if self.reward not in ("attitude", "progress", "off"):
            raise ValueError("reward must be attitude, progress or off")
        if self.error_scale_deg <= 0 or self.goal_altitude <= 0:
            raise ValueError("Positive scale and goal required")


class Mission:
    def __init__(self, vehicle, pilot, run_dir, settings=MissionSettings()):
        self.vehicle = vehicle
        self.pilot = pilot
        self.s = settings
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.episode_index = self._count_episodes()

    def _count_episodes(self):
        path = self.run_dir / "episodes.jsonl"
        return sum(1 for _ in path.open()) if path.exists() else 0

    def frame(self, telemetry):
        if self.s.input == "black":
            return black_panel()
        error = telemetry.pitch_error_deg / self.s.error_scale_deg
        progress = telemetry.apoapsis / self.s.goal_altitude
        return render_panel(error, progress)

    def reinforcement(self, previous, current):
        if self.s.reward == "off" or previous is None:
            return NONE
        failed = current.failure is not None
        if self.s.reward == "attitude":
            return attitude_reinforcement(
                previous.pitch_error_deg,
                current.pitch_error_deg,
                climbing=current.vertical_speed > 0,
                deadband_deg=self.s.attitude_deadband_deg,
                failed=failed,
            )
        return progress_reinforcement(
            current.apoapsis - previous.apoapsis,
            deadband=self.s.progress_deadband_m,
            failed=failed,
        )

    def fly(self):
        """One launch, from pad to whatever happens next. Returns the episode summary."""
        from PIL import Image

        index = self.episode_index
        telemetry = self.vehicle.reset()
        if hasattr(self.pilot, "begin_episode"):
            self.pilot.begin_episode()
        previous = None
        ticks = 0
        compute = 0.0
        abs_error = []
        stimuli = {"reward": 0, "aversive": 0, "none": 0}
        started = time.time()
        events = (self.run_dir / f"episode-{index:04d}.jsonl").open("w")
        try:
            while not telemetry.done:
                kind = self.reinforcement(previous, telemetry)
                stimuli[kind] += 1
                frame = self.frame(telemetry)
                command, neural = self.pilot.act(frame, telemetry, kind)
                command = command.clipped()
                previous = telemetry
                telemetry = self.vehicle.step(command)
                ticks += 1
                compute += neural.get("compute_seconds", 0.0)
                abs_error.append(abs(telemetry.pitch_error_deg))
                if ticks % self.s.log_every == 0 or telemetry.done:
                    row = {
                        "episode": index,
                        "tick": ticks,
                        "stimulus": kind,
                        "command": {"steer": command.steer, "throttle": command.throttle},
                        "telemetry": telemetry.json(),
                        "neural": neural,
                    }
                    events.write(json.dumps(row, allow_nan=False) + "\n")
                if ticks % self.s.image_every == 0:
                    Image.fromarray(frame).save(self.run_dir / "latest-input.png")
        finally:
            events.close()
        summary = {
            "episode": index,
            "pilot": self.pilot.name,
            "input": self.s.input,
            "reward": self.s.reward,
            "ticks": ticks,
            "flight_seconds": telemetry.time,
            "wall_seconds": round(time.time() - started, 2),
            "compute_seconds": round(compute, 2),
            "outcome": telemetry.failure or "spent",
            "max_altitude_m": round(getattr(self.vehicle, "max_altitude", telemetry.altitude), 1),
            "max_apoapsis_m": round(getattr(self.vehicle, "max_apoapsis", telemetry.apoapsis), 1),
            "mean_abs_pitch_error_deg": round(float(np.mean(abs_error)), 3) if abs_error else None,
            "stimuli": stimuli,
        }
        if hasattr(self.pilot, "brain"):
            summary["memory"] = self.pilot.brain.memory()
            summary["brain_ms"] = self.pilot.brain.sim_ms
            if self.s.checkpoint:
                self.pilot.save(self.run_dir / "brain.npz")
        with (self.run_dir / "episodes.jsonl").open("a") as f:
            f.write(json.dumps(summary, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.episode_index += 1
        return summary
