"""Run 2D-simulator launches for several decoder settings in parallel and tabulate.

Every configuration flies the same seeds. Use different seeds for choosing settings and
for reporting them (e.g. --seeds 0 1 to tune, then --seeds 3 4 5 to report), otherwise
the decoder is tuned to the gusts it is scored on.

    uv run python scripts/sweep.py --seeds 0 1 --jobs 6
"""

import argparse
import itertools
import json
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(config, seed, out_root, extra):
    name = "_".join(f"{k}{v}" for k, v in config.items())
    run_dir = out_root / name / f"seed{seed}"
    cmd = [
        "uv", "run", "flybywire", "launch", "--pilot", "fly", "--frozen", "--fresh",
        "--episodes", "1", "--seed", str(seed), "--run-dir", str(run_dir),
        "--steer-gain-hz", str(config["gain"]),
        "--steer-tau-ms", str(config["tau"]),
        "--error-scale-deg", str(config["scale"]),
        *extra,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode:
        return name, seed, {"error": proc.stderr[-400:]}
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    return name, seed, summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gain", type=float, nargs="+", default=[70.0])
    p.add_argument("--tau", type=float, nargs="+", default=[100.0])
    p.add_argument("--scale", type=float, nargs="+", default=[5.0])
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--out", type=Path, default=ROOT / "runs" / "sweep")
    p.add_argument("--extra", nargs=argparse.REMAINDER, default=[], help="Extra launch flags")
    a = p.parse_args()
    configs = [
        {"gain": g, "tau": t, "scale": s}
        for g, t, s in itertools.product(a.gain, a.tau, a.scale)
    ]
    jobs = [(c, seed) for c in configs for seed in a.seeds]
    results = {}
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for name, seed, summary in pool.map(lambda j: run(j[0], j[1], a.out, a.extra), jobs):
            results.setdefault(name, {})[seed] = summary
            keys = ["outcome", "max_apoapsis_m", "final_periapsis_m", "mean_abs_steer_error_deg", "error"]
            print(json.dumps({"config": name, "seed": seed, **{k: summary.get(k) for k in keys}}), flush=True)
    print()
    print(f"{'config':34s} {'outcomes':18s} {'median apo km':>13s} {'min apo km':>10s} {'median |err|':>12s}")
    rows = []
    for name, by_seed in results.items():
        ok = [s for s in by_seed.values() if "error" not in s]
        if not ok:
            continue
        apo = [s["max_apoapsis_m"] / 1000 for s in ok]
        err = [s["mean_abs_steer_error_deg"] for s in ok]
        rows.append((statistics.median(apo), name, ",".join(s["outcome"] for s in ok), min(apo), statistics.median(err)))
    for apo, name, outcomes, low, err in sorted(rows, reverse=True):
        print(f"{name:34s} {outcomes:18s} {apo:13.1f} {low:10.1f} {err:12.2f}")
    (a.out / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
