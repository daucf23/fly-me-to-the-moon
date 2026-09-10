"""Tabulate episodes.jsonl across run directories."""

import json
import statistics
import sys
from pathlib import Path


def load(run_dir):
    path = Path(run_dir) / "episodes.jsonl"
    return [json.loads(line) for line in path.open()] if path.exists() else []


def main(run_dirs):
    print(
        f"{'run':22s} {'n':>2s} {'outcomes':24s} {'apoapsis km (median)':>21s} "
        f"{'periapsis km':>13s} {'max alt km':>11s} {'|steer err| deg':>16s} {'edges changed':>13s}"
    )
    for run_dir in run_dirs:
        rows = load(run_dir)
        if not rows:
            continue
        outcomes = ",".join(r["outcome"] for r in rows)
        apo = statistics.median(r["max_apoapsis_m"] for r in rows) / 1000
        peris = [r["final_periapsis_m"] for r in rows if r.get("final_periapsis_m") is not None]
        peri = f"{statistics.median(peris) / 1000:13.1f}" if peris else f"{'-':>13s}"
        alt = statistics.median(r["max_altitude_m"] for r in rows) / 1000
        err = statistics.median(r["mean_abs_steer_error_deg"] or 0 for r in rows)
        changed = rows[-1].get("memory", {}).get("changed_edges", "-")
        print(
            f"{Path(run_dir).name:22s} {len(rows):2d} {outcomes:24s} {apo:21.1f} {peri} "
            f"{alt:11.1f} {err:16.2f} {str(changed):>13s}"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
