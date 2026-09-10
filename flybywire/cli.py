"""Ground control. Every subcommand is local; nothing leaves this machine."""

import argparse
import json
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(prog="flybywire")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="Download MaleCNS v1.0 and compile the graph")
    sub.add_parser("verify", help="Check dataset and compiled arrays against locks")
    bench = sub.add_parser("bench", help="Wall-clock cost of one neural observation")
    bench.add_argument("--neural-ms", type=float, default=50.0)
    bench.add_argument("--frames", type=int, default=20)
    cal = sub.add_parser("calibrate", help="Measure which descending neurons lateralise with the bar")
    cal.add_argument("--settle-ms", type=float, default=1000.0)
    cal.add_argument("--record-ms", type=float, default=1000.0)
    cal.add_argument("--top", type=int, default=15)
    cal.add_argument("--out", type=Path, default=Path("runs/calibration.json"))
    launch = sub.add_parser("launch", help="Fly the 2D simulator")
    launch.add_argument(
        "--pilot",
        choices=["fly", "none", "random", "autopilot", "panel-autopilot"],
        default="fly",
    )
    launch.add_argument("--episodes", type=int, default=1)
    launch.add_argument("--run-dir", type=Path, default=None)
    launch.add_argument("--seed", type=int, default=0, help="Gust seed for episode 0; increments per episode")
    launch.add_argument("--input", choices=["panel", "black"], default="panel")
    launch.add_argument("--reward", choices=["attitude", "progress", "off"], default="attitude")
    launch.add_argument("--frozen", action="store_true", help="Freeze plastic weights (control)")
    launch.add_argument("--neural-ms", type=float, default=50.0)
    launch.add_argument("--error-scale-deg", type=float, default=10.0)
    launch.add_argument("--steer-gain-hz", type=float, default=35.0)
    launch.add_argument("--steer-tau-ms", type=float, default=300.0)
    launch.add_argument("--gravity-turn", action="store_true", help="Guidance target follows a turn instead of vertical")
    launch.add_argument("--fresh", action="store_true", help="Ignore an existing brain checkpoint")
    a = p.parse_args()

    if a.command == "prepare":
        from .data import prepare

        prepare()
    elif a.command == "verify":
        from .data import verify

        print(json.dumps(verify()))
    elif a.command == "bench":
        run_bench(a.neural_ms, a.frames)
    elif a.command == "calibrate":
        from .calibrate import main as calibrate_main

        calibrate_main(a)
    elif a.command == "launch":
        run_launch(a)


def run_launch(a):
    from .mission import Mission, MissionSettings
    from .pilot import make_pilot
    from .sim.rocket import Rocket2D, RocketConfig, gravity_turn_target, vertical_target

    if a.episodes < 1:
        raise SystemExit("episodes must be >= 1")
    run_dir = a.run_dir or Path("runs") / (
        f"sim-{a.pilot}" + ("-frozen" if a.frozen else "") + ("-black" if a.input == "black" else "")
    )
    if a.pilot == "fly":
        kwargs = dict(
            neural_ms=a.neural_ms,
            learning=not a.frozen,
            decoder_kwargs={"gain_hz": a.steer_gain_hz, "tau_ms": a.steer_tau_ms},
        )
    else:
        kwargs = {"seed": a.seed}
    pilot = make_pilot(a.pilot, **kwargs)
    checkpoint = run_dir / "brain.npz"
    if a.pilot == "fly" and checkpoint.exists() and not a.fresh:
        pilot.restore(checkpoint)
        print(json.dumps({"resumed": str(checkpoint), "brain_ms": pilot.brain.sim_ms}), flush=True)
    settings = MissionSettings(input=a.input, reward=a.reward, error_scale_deg=a.error_scale_deg)
    config = RocketConfig(dt=a.neural_ms / 1000)
    target = gravity_turn_target if a.gravity_turn else vertical_target
    vehicle = Rocket2D(config, seed=a.seed, target=target)
    mission = Mission(vehicle, pilot, run_dir, settings)
    provenance = {
        "pilot": pilot.name,
        "settings": settings.__dict__,
        "rocket": {**config.__dict__, "stages": [s.__dict__ for s in config.stages]},
        "guidance": target.__name__,
        **({"fly": pilot.provenance()} if a.pilot == "fly" else {}),
    }
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str) + "\n")
    try:
        for i in range(a.episodes):
            vehicle.seed = a.seed + mission.episode_index
            summary = mission.fly()
            print(json.dumps(summary), flush=True)
    except KeyboardInterrupt:
        print("Abort. Run state preserved.", flush=True)


def run_bench(neural_ms, frames):
    import numpy as np

    from .neural.visual import VisualMemoryBrain

    t0 = time.perf_counter()
    brain = VisualMemoryBrain()
    load = time.perf_counter() - t0
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 256, size=(160, 90, 3), dtype=np.uint8)
    # Warm up once so the first-call cost does not skew the mean.
    brain.rgb_step(frame, neural_ms, learning=True)
    walls = []
    spikes = []
    for _ in range(frames):
        t = time.perf_counter()
        counts, kernel = brain.rgb_step(frame, neural_ms, learning=True)
        walls.append(time.perf_counter() - t)
        spikes.append(int(counts.sum()))
    walls = np.asarray(walls)
    print(
        json.dumps(
            {
                "neurons": brain.n,
                "edges": len(brain.post),
                "load_seconds": round(load, 2),
                "neural_ms_per_frame": neural_ms,
                "wall_ms_per_frame_mean": round(1000 * walls.mean(), 1),
                "wall_ms_per_frame_p95": round(1000 * np.percentile(walls, 95), 1),
                "realtime_ratio": round(neural_ms / (1000 * walls.mean()), 3),
                "frames_per_second": round(1 / walls.mean(), 2),
                "spikes_per_frame_mean": int(np.mean(spikes)),
            },
            indent=2,
        )
    )
