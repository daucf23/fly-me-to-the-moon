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
    a = p.parse_args()

    if a.command == "prepare":
        from .data import prepare

        prepare()
    elif a.command == "verify":
        from .data import verify

        print(json.dumps(verify()))
    elif a.command == "bench":
        run_bench(a.neural_ms, a.frames)


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
