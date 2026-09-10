"""Fetch released MaleCNS inputs and verify both sources and prepared arrays.

Adapted from stonkfly/data.py (MIT); the DOOMFLY reuse path is removed.
"""

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

import numpy as np

from .neural.common import DATA, GRAPH, digest

PACKAGE = Path(__file__).with_name("neural")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify():
    lock = json.loads((PACKAGE / "sources.lock.json").read_text())
    if sha(DATA / "annotations.feather") != lock["annotations.feather"]["sha256"]:
        raise RuntimeError("Annotation checksum mismatch")
    expected = json.loads((PACKAGE / "arrays.lock.json").read_text())
    with np.load(GRAPH, allow_pickle=False) as a:
        if set(a.files) != set(expected):
            raise RuntimeError("Graph fields mismatch")
        for k, h in expected.items():
            if digest(a[k]) != h:
                raise RuntimeError("Graph array checksum mismatch: " + k)
        if len(a["ids"]) != 166700 or len(a["post"]) != 25582938:
            raise RuntimeError("Wrong retained graph")
    import pyarrow.feather as f

    if not (DATA / "normalized/neurons.feather").exists():
        raise RuntimeError("Normalized neuron metadata missing")
    n = f.read_table(DATA / "normalized/neurons.feather").to_pandas()
    transmitter_values = json.dumps(
        n.neurotransmitter.fillna("").astype(str).tolist(), separators=(",", ":")
    ).encode()
    nt_expected = json.loads((PACKAGE / "neurons.lock.json").read_text())[
        "neurotransmitter_values_sha256"
    ]
    if hashlib.sha256(transmitter_values).hexdigest() != nt_expected:
        raise RuntimeError("Normalized transmitter values mismatch")
    with np.load(GRAPH, allow_pickle=False) as a:
        if not np.array_equal(n.source_id.to_numpy(), a["ids"]):
            raise RuntimeError("Normalized neuron order mismatch")
    return {
        "release": "MaleCNS v1.0",
        "neurons": 166700,
        "directed_edges": 25582938,
        "arrays_verified": True,
    }


def _download(url, target, expected_sha):
    tmp = target.with_suffix(".partial")
    done = [0]

    def hook(blocks, block_size, total):
        got = blocks * block_size
        if total > 0 and got - done[0] >= 64 * 1024 * 1024:
            done[0] = got
            print(f"  {min(got, total) / 1e6:8.0f} / {total / 1e6:.0f} MB", flush=True)

    urllib.request.urlretrieve(url, tmp, hook)
    if sha(tmp) != expected_sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Downloaded checksum mismatch: " + target.name)
    tmp.replace(target)


def prepare():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = json.loads((PACKAGE / "sources.lock.json").read_text())
    for name, info in lock.items():
        path = DATA / name
        if not path.exists():
            print(f"Downloading {name} ({info['bytes'] / 1e6:.0f} MB)", flush=True)
            _download(info["url"], path, info["sha256"])
        if sha(path) != info["sha256"]:
            raise RuntimeError("Source checksum mismatch: " + name)
    shutil.copyfile(PACKAGE / "sources.lock.json", DATA / "source.lock.json")
    if not GRAPH.exists():
        from .neural.connectome import import_graph
        from .neural.prepare import prepare as compile_graph

        print("Normalizing released graph", flush=True)
        import_graph()
        print("Compiling CSR graph and retinal projection", flush=True)
        compile_graph()
    print(json.dumps(verify()), flush=True)
