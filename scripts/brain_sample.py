"""Choose the neurons the cockpit raster shows, by measurement.

A random sample of the connectome is almost dark: the network fires ~1.8 Hz per neuron
on average, so a cell rarely spikes in a 50 ms window. This probe shows one brain the
three panels a seat can see (dark, full bar left, full bar right), each settled 1 s and
recorded 2 s, and keeps per pathway stratum the cells whose rate moves most with the
needle. The decoder's four cells are always kept. Output: flybywire/neural/brain_sample.json,
read by FlyCrew.brain_sample(); the same 1,000 cells in every recording.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flybywire.instruments import black_panel, render_panel  # noqa: E402
from flybywire.ksp.crew import FlyCrew  # noqa: E402
from flybywire.neural.common import annotations  # noqa: E402
from flybywire.pilot import FlyPilot  # noqa: E402

SETTLE_S, RECORD_S = 1.0, 2.0
PER_STRATUM = 200
OUT = Path(__file__).resolve().parents[1] / "flybywire" / "neural" / "brain_sample.json"


def mean_rate(pilot, panel):
    """Hz per neuron over RECORD_S after SETTLE_S under this panel."""
    windows = round((SETTLE_S + RECORD_S) * 1000 / pilot.neural_ms)
    settle = round(SETTLE_S * 1000 / pilot.neural_ms)
    total = np.zeros(pilot.brain.n, dtype=np.int64)
    for k in range(windows):
        pilot.act(panel, None, "none")
        if k >= settle:
            total += pilot.brain.counts
    return total / RECORD_S


def main():
    t = time.time()
    pilot = FlyPilot(learning=False)
    pilot.begin_episode()
    print(f"brain loaded in {time.time() - t:.0f} s", file=sys.stderr)
    stimuli = {"dark": black_panel(), "left": render_panel(-1.0), "right": render_panel(1.0)}
    rates = {}
    for name, panel in stimuli.items():
        pilot.begin_episode()
        rates[name] = mean_rate(pilot, panel)
        print(f"{name}: {rates[name].sum() / 1000:.0f} k spikes/s whole network", file=sys.stderr)
    modulation = np.maximum(np.abs(rates["left"] - rates["dark"]), np.abs(rates["right"] - rates["dark"]))

    ids = pilot.brain.ids
    a = annotations(ids)
    superclass = a.superclass.fillna("").to_numpy()
    side = a.somaSide.fillna(a.rootSide).fillna("").to_numpy()  # photoreceptors carry their eye in rootSide
    types = a.type.fillna("").to_numpy()
    decoder = set(np.concatenate([pilot.decoder.left, pilot.decoder.right]).tolist())
    chosen = []
    for stratum in FlyCrew.BRAIN_STRATA:
        stratum_pool = np.flatnonzero(superclass == stratum)
        responding = int((modulation[stratum_pool] > 1.0).sum())
        print(f"{stratum}: {len(stratum_pool)} cells, {responding} move > 1 Hz with the needle", file=sys.stderr)
        # Half the block per eye, each side's cells ordered by how much the needle moves them.
        for eye in ("L", "R"):
            pool = stratum_pool[(side[stratum_pool] == eye) if eye == "L" else (side[stratum_pool] != "L")]
            forced = [i for i in pool if i in decoder]
            rest = [i for i in pool[np.argsort(-modulation[pool], kind="stable")] if i not in decoder]
            chosen.extend(forced + rest[: PER_STRATUM // 2 - len(forced)])
    neurons = [
        {
            "bodyId": str(ids[i]),
            "superclass": superclass[i],
            "side": side[i],
            "type": types[i],
            "decoder": i in decoder,
            "dark_hz": round(float(rates["dark"][i]), 2),
            "left_hz": round(float(rates["left"][i]), 2),
            "right_hz": round(float(rates["right"][i]), 2),
        }
        for i in chosen
    ]
    OUT.write_text(json.dumps({"method": __doc__.strip(), "settle_s": SETTLE_S, "record_s": RECORD_S, "neurons": neurons}, indent=1) + "\n")
    print(f"{len(neurons)} neurons -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
