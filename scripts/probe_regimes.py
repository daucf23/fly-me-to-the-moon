"""Reproduce the "two regimes" measurements in docs/calibration.md.

    uv run python scripts/probe_regimes.py            # everything (~3 min)
    uv run python scripts/probe_regimes.py wiring     # graph distances only (seconds)
"""

import collections
import sys

import numpy as np

from flybywire.instruments import render_panel
from flybywire.neural.common import annotations
from flybywire.neural.visual import VisualMemoryBrain

STEER_TYPES = ["DNp20", "DNpe017"]


def bfs(b, sources, max_depth=6, min_w=0.0):
    dist = np.full(b.n, -1, np.int32)
    parent = np.full(b.n, -1, np.int64)
    frontier = np.asarray(sources)
    dist[frontier] = 0
    for d in range(1, max_depth + 1):
        nxt = []
        for i in frontier:
            sl = slice(b.ptr[i], b.ptr[i + 1])
            post = b.post[sl][np.abs(b.weight[sl]) >= min_w]
            new = post[dist[post] < 0]
            dist[new] = d
            parent[new] = i
            nxt.append(new)
        frontier = np.unique(np.concatenate(nxt)) if nxt else np.array([], int)
        if not len(frontier):
            break
    return dist, parent


def wiring(b, types, sides):
    label = lambda i: f"{types[i] or '?'}{sides[i]}"
    targets = np.flatnonzero(np.isin(types, STEER_TYPES))
    print("== shortest paths from MBON07/MBON11 to the steering cells ==")
    for min_w, note in [(0.0, "all edges"), (1.0, ">= 4 synapses"), (2.75, ">= 10 synapses")]:
        dist, parent = bfs(b, b.circuit["mb"], min_w=min_w)
        print(f"-- {note} --")
        for t in targets:
            path, i = [], t
            while i >= 0:
                path.append(label(i))
                i = parent[i]
            print(f"  {label(t)}: {dist[t]} hops  {' -> '.join(reversed(path))}")
    dist, _ = bfs(b, b.retina, max_depth=8)
    kc = b.circuit["kc"]
    print("retina -> KC hops:", dict(sorted(collections.Counter(dist[kc][dist[kc] > 0].tolist()).items())))


def measure(b, cells, frame, settle=20, record=20):
    b.reset()
    for _ in range(settle):
        b.rgb_step(frame, 50)
    tot, wall = np.zeros(b.n, np.int64), 0.0
    for _ in range(record):
        c, w = b.rgb_step(frame, 50)
        tot += c
        wall += w
    kc = b.circuit["kc"]
    return dict(
        wall_ms=1000 * wall / record,
        L=int(tot[cells["L"]].sum()),
        R=int(tot[cells["R"]].sum()),
        kc_active=int((tot[kc] > 0).sum()),
        network=int(tot.sum()),
    )


def report(name, m):
    print(f"{name:30s} wall={m['wall_ms']:6.1f}ms  L{m['L']:4d}/R{m['R']:4d} Hz  KCs active {m['kc_active']:4d}  network {m['network']:8d}/s", flush=True)


def backgrounds(b, cells):
    print("== uniform background under the needle ==")
    for value in [15, 25, 40, 60]:
        for err, tag in [(0.0, "none"), (-1.0, "left"), (1.0, "right")]:
            frame = np.maximum(render_panel(err), np.uint8(value))
            report(f"bg {value} needle {tag}", measure(b, cells, frame))
    print("== inverted: white field, dark needle ==")
    for err, tag in [(0.0, "none"), (-1.0, "left"), (1.0, "right"), (-0.5, "half left"), (0.5, "half right")]:
        frame = np.full((160, 90, 3), 255, np.uint8)
        w = int(round(abs(err) * 20))
        if w and err > 0:
            frame[:, 90 - w:] = 0
        elif w:
            frame[:, :w] = 0
        report(f"inverted needle {tag}", measure(b, cells, frame))


def flash(b, cells):
    print("== white flash during a steady left needle (per 50 ms tick) ==")
    kc = b.circuit["kc"]
    bar, white = render_panel(-1.0), np.full((160, 90, 3), 255, np.uint8)
    for flash_ms in [50, 200]:
        b.reset()
        for _ in range(20):
            b.rgb_step(bar, 50)
        seq = [("bar", bar)] * 2 + [("FLASH", white)] * (flash_ms // 50) + [("bar", bar)] * 6
        print(f"-- {flash_ms} ms flash --")
        for tag, frame in seq:
            c, _ = b.rgb_step(frame, 50)
            print(f"  {tag:5s} L{int(c[cells['L']].sum()) * 20:4d}/R{int(c[cells['R']].sum()) * 20:4d} Hz  KC spikes {int(c[kc].sum()):3d}  network {int(c.sum()):6d}")


def main(argv):
    b = VisualMemoryBrain()
    b.weights_frozen = True
    a = annotations(b.ids)
    types, sides = a.type.fillna("").to_numpy(), a.somaSide.fillna("").to_numpy()
    cells = {s: np.flatnonzero(np.isin(types, STEER_TYPES) & (sides == s)) for s in "LR"}
    which = set(argv) or {"wiring", "backgrounds", "flash"}
    if "wiring" in which:
        wiring(b, types, sides)
    if "backgrounds" in which:
        backgrounds(b, cells)
    if "flash" in which:
        flash(b, cells)


if __name__ == "__main__":
    main(sys.argv[1:])
