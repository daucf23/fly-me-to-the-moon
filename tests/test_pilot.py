import numpy as np
import pandas as pd
import pytest

from flybywire.pilot import Decoder


def annotation():
    return pd.DataFrame(
        {
            "type": ["DNp20", "DNp20", "DNpe017", "DNpe017", "KCg", None],
            "somaSide": ["L", "R", "L", "R", "L", None],
        }
    )


def decoder(**kw):
    defaults = dict(baseline_hz={"L": 10.0, "R": 20.0}, gain_hz=30.0, threshold_hz=3.0, tau_ms=1e-6)
    defaults.update(kw)
    return Decoder(np.arange(100, 106), annotation(), neural_ms=50.0, **defaults)


def test_decoder_reads_named_cells_above_their_own_baseline():
    d = decoder()
    assert d.identities == {"left": ["100", "102"], "right": ["101", "103"]}
    counts = np.zeros(6, dtype=np.int32)
    counts[[1, 3]] = 1  # right cells: 2 spikes / 50 ms = 40 Hz summed; 20 above baseline
    counts[[0, 2]] = 0  # left: 0 Hz; 10 below baseline
    out = d.decode(counts, 0.05)
    assert out["right_hz"] == 40 and out["left_hz"] == 0
    assert out["difference_hz"] == pytest.approx(30)  # (40-20) - (0-10)
    assert out["steer"] == 1.0  # 30 Hz / 30 Hz gain
    counts[:] = 0
    counts[[0, 2]] = 1  # left 40 Hz (30 above), right 0 (20 below): -50 -> full left
    assert d.decode(counts, 0.05)["steer"] == -1.0


def test_decoder_deadband_and_smoothing():
    d = decoder(tau_ms=50.0)  # alpha = 1 - e^-1 ~ 0.63
    counts = np.zeros(6, dtype=np.int32)
    counts[[1, 3]] = 1
    first = d.decode(counts, 0.05)["difference_hz"]
    second = d.decode(counts, 0.05)["difference_hz"]
    assert 0 < first < second < 30  # converging toward the raw 30 Hz difference
    d.reset()
    assert d.smoothed == {"L": 0.0, "R": 0.0}
    quiet = decoder()
    counts[:] = 0
    counts[0] = 0
    counts[1] = 1  # right 20 Hz (baseline) vs left 0 (-10): difference 10 -> steer 1/3
    assert quiet.decode(counts, 0.05)["steer"] == pytest.approx(1 / 3)
    calm = decoder(baseline_hz={"L": 0.0, "R": 0.0})
    counts[:] = 0
    assert calm.decode(counts, 0.05)["steer"] == 0.0  # inside the deadband


def test_decoder_rejects_missing_cells_and_bad_parameters():
    a = annotation()
    with pytest.raises(RuntimeError):
        Decoder(np.arange(6), a.assign(type=a.type.replace("DNp20", "other").replace("DNpe017", "x")))
    with pytest.raises(ValueError):
        Decoder(np.arange(6), a, gain_hz=0)
