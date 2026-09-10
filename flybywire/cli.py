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
    add_flight_arguments(launch)
    launch.add_argument("--seed", type=int, default=0, help="Gust seed for episode 0; increments per episode")
    launch.add_argument("--gust-std", type=float, default=0.06, help="Gust torque noise, rad/s^2 (default 0.06)")

    ksp = sub.add_parser("ksp", help="Fly Kerbal Space Program through kRPC")
    add_flight_arguments(ksp)
    ksp.add_argument("--address", default="127.0.0.1", help="kRPC server host (LAN OK)")
    ksp.add_argument("--rpc-port", type=int, default=50000)
    ksp.add_argument("--stream-port", type=int, default=50001)
    ksp.add_argument("--craft", default=None, help="VAB craft to launch when revert is impossible")
    ksp.add_argument("--lockstep", action="store_true", help="Pause KSP while the brain thinks")
    ksp.add_argument("--no-pitch-hold", action="store_true", help="Nobody holds pitch (not advised)")
    ksp.add_argument("--invert-yaw", action="store_true")
    ksp.add_argument("--invert-pitch", action="store_true")
    ksp.add_argument("--timeout", type=float, default=600.0)
    ksp.add_argument("--check", action="store_true", help="Connect, report the vessel, do not fly")
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
    elif a.command == "ksp":
        run_ksp(a)


def add_flight_arguments(p):
    p.add_argument(
        "--pilot",
        choices=["fly", "none", "random", "autopilot", "panel-autopilot"],
        default="fly",
    )
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--run-dir", type=Path, default=None)
    p.add_argument("--input", choices=["panel", "black"], default="panel")
    p.add_argument("--reward", choices=["attitude", "progress", "off"], default="attitude")
    p.add_argument("--frozen", action="store_true", help="Freeze plastic weights (control)")
    p.add_argument("--neural-ms", type=float, default=50.0)
    p.add_argument("--error-scale-deg", type=float, default=5.0, help="Error that draws a full-width needle")
    p.add_argument("--steer-gain-hz", type=float, default=70.0, help="Rate difference that saturates the stick")
    p.add_argument("--steer-tau-ms", type=float, default=100.0, help="Rate smoothing time constant")
    p.add_argument("--gravity-turn", action="store_true", help="Guidance target follows a turn instead of vertical")
    p.add_argument("--fresh", action="store_true", help="Ignore an existing brain checkpoint")


def build_pilot(a, run_dir, seed=0):
    from .pilot import make_pilot

    if a.pilot == "fly":
        kwargs = dict(
            neural_ms=a.neural_ms,
            learning=not a.frozen,
            decoder_kwargs={"gain_hz": a.steer_gain_hz, "tau_ms": a.steer_tau_ms},
        )
    else:
        kwargs = {"seed": seed}
    pilot = make_pilot(a.pilot, **kwargs)
    checkpoint = run_dir / "brain.npz"
    if a.pilot == "fly" and checkpoint.exists() and not a.fresh:
        pilot.restore(checkpoint)
        print(json.dumps({"resumed": str(checkpoint), "brain_ms": pilot.brain.sim_ms}), flush=True)
    return pilot


def default_run_dir(a, prefix):
    return a.run_dir or Path("runs") / (
        f"{prefix}-{a.pilot}" + ("-frozen" if a.frozen else "") + ("-black" if a.input == "black" else "")
    )


def write_provenance(run_dir, pilot, settings, vehicle_info, a):
    provenance = {
        "pilot": pilot.name,
        "settings": settings.__dict__,
        **vehicle_info,
        **({"fly": pilot.provenance()} if a.pilot == "fly" else {}),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str) + "\n")


def run_launch(a):
    from .mission import Mission, MissionSettings
    from .sim.rocket import Rocket2D, RocketConfig, gravity_turn_target, vertical_target

    if a.episodes < 1:
        raise SystemExit("episodes must be >= 1")
    run_dir = default_run_dir(a, "sim")
    pilot = build_pilot(a, run_dir, seed=a.seed)
    settings = MissionSettings(input=a.input, reward=a.reward, error_scale_deg=a.error_scale_deg)
    config = RocketConfig(dt=a.neural_ms / 1000, gust_std=a.gust_std)
    target = gravity_turn_target if a.gravity_turn else vertical_target
    vehicle = Rocket2D(config, seed=a.seed, target=target)
    mission = Mission(vehicle, pilot, run_dir, settings)
    write_provenance(
        run_dir,
        pilot,
        settings,
        {
            "rocket": {**config.__dict__, "stages": [s.__dict__ for s in config.stages]},
            "guidance": target.__name__,
        },
        a,
    )
    try:
        for _ in range(a.episodes):
            vehicle.seed = a.seed + mission.episode_index
            print(json.dumps(mission.fly()), flush=True)
    except KeyboardInterrupt:
        print("Abort. Run state preserved.", flush=True)


def run_ksp(a):
    from .ksp.vehicle import KerbalConfig, KerbalRocket, gravity_turn_target, vertical_target
    from .mission import Mission, MissionSettings

    config = KerbalConfig(
        address=a.address,
        rpc_port=a.rpc_port,
        stream_port=a.stream_port,
        craft=a.craft,
        dt=a.neural_ms / 1000,
        lockstep=a.lockstep,
        pitch_hold=not a.no_pitch_hold,
        invert_yaw=a.invert_yaw,
        invert_pitch=a.invert_pitch,
        timeout=a.timeout,
    )
    target = gravity_turn_target if a.gravity_turn else vertical_target
    vehicle = KerbalRocket(config, target=target)
    print(json.dumps({"connected": vehicle.server()}), flush=True)
    if a.check:
        v = vehicle.sc.active_vessel
        f = v.flight()
        print(
            json.dumps(
                {
                    "scene": str(vehicle.conn.krpc.current_game_scene),
                    "vessel": v.name,
                    "situation": str(v.situation),
                    "altitude": f.mean_altitude,
                    "pitch": f.pitch,
                    "heading": f.heading,
                    "liquid_fuel": v.resources.amount("LiquidFuel"),
                    "stage": v.control.current_stage,
                    "can_revert_to_launch": vehicle.sc.can_revert_to_launch,
                    "parts": len(v.parts.all),
                    "has_fins": any(
                        "fin" in p.name.lower() or "winglet" in p.name.lower() for p in v.parts.all
                    ),
                },
                indent=2,
            )
        )
        return
    if a.episodes < 1:
        raise SystemExit("episodes must be >= 1")
    run_dir = default_run_dir(a, "ksp")
    pilot = build_pilot(a, run_dir)
    settings = MissionSettings(input=a.input, reward=a.reward, error_scale_deg=a.error_scale_deg)
    mission = Mission(vehicle, pilot, run_dir, settings)
    write_provenance(
        run_dir, pilot, settings, {"ksp": config.__dict__, "guidance": target.__name__, "server": vehicle.server()}, a
    )
    try:
        for _ in range(a.episodes):
            print(json.dumps(mission.fly()), flush=True)
    except KeyboardInterrupt:
        print("Abort. Handing the vessel back with SAS on.", flush=True)
    finally:
        vehicle.release()


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
