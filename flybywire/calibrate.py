"""Which descending neurons actually see the needle?

Present the instrument panel with the bar left, centre and right, hold each long enough
for the network to settle, and measure every descending-neuron type by soma side. The
decoder should read cells that this measurement says are lateralised, not cells we
assumed would be. Frozen weights, no reinforcement: pure sensory response.
"""

import json

import numpy as np

from .instruments import black_panel, render_panel


def stimuli():
    return {
        "black": black_panel(),
        "bar_left": render_panel(-1.0),
        "bar_half_left": render_panel(-0.5),
        "bar_centre": render_panel(0.0),
        "bar_half_right": render_panel(0.5),
        "bar_right": render_panel(1.0),
    }


def measure(brain, frame, *, settle_ms, record_ms, step_ms=50.0):
    for _ in range(round(settle_ms / step_ms)):
        brain.rgb_step(frame, step_ms)
    total = np.zeros(brain.n, dtype=np.int64)
    wall = 0.0
    for _ in range(round(record_ms / step_ms)):
        counts, elapsed = brain.rgb_step(frame, step_ms)
        total += counts
        wall += elapsed
    return total / (record_ms / 1000), wall / round(record_ms / step_ms)  # Hz per cell


def calibrate(*, settle_ms=1000.0, record_ms=1000.0, top=15, focus=None):
    from .neural.common import annotations
    from .neural.visual import VisualMemoryBrain

    brain = VisualMemoryBrain()
    brain.weights_frozen = True
    a = annotations(brain.ids)
    types = a.type.fillna("").to_numpy()
    sides = a.somaSide.fillna("").to_numpy()
    descending = np.char.startswith(types.astype(str), "DN") | np.isin(
        types, focus or []
    )
    rates = {}
    walls = {}
    for name, frame in stimuli().items():
        brain.reset()
        rates[name], walls[name] = measure(
            brain, frame, settle_ms=settle_ms, record_ms=record_ms
        )

    table = {}
    for t in sorted(set(types[descending]) - {""}):
        cells = {s: np.flatnonzero((types == t) & (sides == s)) for s in ["L", "R"]}
        if not len(cells["L"]) or not len(cells["R"]):
            continue  # unpaired cells cannot report a left/right difference
        entry = {
            n: {s: float(r[ix].mean()) for s, ix in cells.items()} for n, r in rates.items()
        }
        asym = {n: entry[n]["R"] - entry[n]["L"] for n in rates}
        entry["lateralisation_hz"] = asym["bar_right"] - asym["bar_left"]
        entry["peak_hz"] = max(max(entry[n].values()) for n in rates)
        table[t] = entry

    ranked = sorted(
        table.items(), key=lambda kv: abs(kv[1]["lateralisation_hz"]), reverse=True
    )
    report = {
        "settle_ms": settle_ms,
        "record_ms": record_ms,
        "wall_ms_per_50ms": {n: round(1000 * w, 1) for n, w in walls.items()},
        "descending_types_measured": len(table),
        "top_lateralised": [
            {
                "type": t,
                "lateralisation_hz": round(e["lateralisation_hz"], 2),
                "peak_hz": round(e["peak_hz"], 2),
                "bar_left": {s: round(v, 2) for s, v in e["bar_left"].items()},
                "bar_centre": {s: round(v, 2) for s, v in e["bar_centre"].items()},
                "bar_right": {s: round(v, 2) for s, v in e["bar_right"].items()},
                "black": {s: round(v, 2) for s, v in e["black"].items()},
            }
            for t, e in ranked[:top]
        ],
        "focus": {
            t: {n: {s: round(v, 2) for s, v in table[t][n].items()} for n in rates}
            for t in (focus or [])
            if t in table
        },
        "whole_network_hz_per_cell": {
            n: round(float(r.mean()), 3) for n, r in rates.items()
        },
    }
    return report


def main(args):
    report = calibrate(
        settle_ms=args.settle_ms,
        record_ms=args.record_ms,
        top=args.top,
        focus=["DNa02", "DNp20", "DNpe017", "DNp09", "MN9", "DNa01", "DNb01"],
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
