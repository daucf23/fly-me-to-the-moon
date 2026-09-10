import numpy as np
import pytest

from flybywire.instruments import HEIGHT, MAX_BAR_WIDTH, WIDTH, black_panel, render_panel
from flybywire.pilot import Autopilot, NullPilot, PanelAutopilot, RandomPilot
from flybywire.reward import (
    AVERSIVE,
    NONE,
    REWARD,
    attitude_reinforcement,
    progress_reinforcement,
)
from flybywire.sim.rocket import Rocket2D, RocketConfig
from flybywire.vehicle import Command


def fly(pilot, seed=0, config=RocketConfig()):
    rocket = Rocket2D(config, seed=seed)
    t = rocket.reset()
    while not t.done:
        command, _ = pilot.act(None, t, "none")
        t = rocket.step(command)
    return rocket


def test_rocket_is_deterministic_per_seed():
    a = fly(RandomPilot(seed=3), seed=7)
    b = fly(RandomPilot(seed=3), seed=7)
    assert a.max_apoapsis == b.max_apoapsis and a.t == b.t
    c = fly(RandomPilot(seed=3), seed=8)
    assert c.max_apoapsis != a.max_apoapsis


def test_unsteered_rocket_falls_over_and_autopilot_does_not():
    hands_off = fly(NullPilot())
    steered = fly(Autopilot())
    assert hands_off.failure == "tumble"
    assert steered.failure is None
    assert steered.max_apoapsis > 3 * hands_off.max_apoapsis
    assert steered.max_apoapsis > 70_000  # leaves Kerbin's atmosphere


def test_panel_autopilot_flies_from_the_needle_alone():
    """The instrument carries enough information to fly, read perfectly."""
    rocket = Rocket2D(seed=0)
    pilot = PanelAutopilot()
    t = rocket.reset()
    while not t.done:
        command, _ = pilot.act(render_panel(t.pitch_error_deg / 10.0), t, "none")
        t = rocket.step(command)
    assert t.failure is None and rocket.max_apoapsis > 70_000


def test_random_pilot_is_no_better_than_autopilot():
    random = fly(RandomPilot(seed=1))
    steered = fly(Autopilot())
    assert random.max_apoapsis < steered.max_apoapsis


def test_command_is_clipped_and_pad_is_not_a_crash():
    rocket = Rocket2D(seed=0)
    rocket.reset()
    t = rocket.step(Command(steer=5.0, throttle=0.0))
    assert t.altitude == 0.0 and t.failure is None
    for _ in range(20):
        t = rocket.step(Command(steer=0.0, throttle=1.0))
    assert t.altitude > 0 and t.stage == 0


def test_staging_happens_when_first_stage_is_dry():
    rocket = Rocket2D(seed=0)
    pilot = Autopilot()
    t = rocket.reset()
    while t.stage == 0 and not t.done:
        command, _ = pilot.act(None, t, "none")
        t = rocket.step(command)
    assert t.stage == 1 and t.failure is None
    assert t.fuel_fraction == pytest.approx(1.0)


def bright_columns(panel):
    return np.flatnonzero(panel[:, :, 0].max(axis=0) == 255)


def test_panel_needle_sits_on_the_edge_of_the_error_side():
    left = bright_columns(render_panel(-1.0))
    right = bright_columns(render_panel(1.0))
    assert left.min() == 0 and left.max() < 0.4 * WIDTH  # left eye only
    assert right.max() == WIDTH - 1 and right.min() > 0.6 * WIDTH  # right eye only
    assert len(bright_columns(render_panel(0.0))) == 0  # no error, no needle
    assert render_panel(0.0).shape == (HEIGHT, WIDTH, 3)
    assert black_panel().max() == 0


def test_panel_needle_width_grows_with_error_and_is_capped():
    widths = [len(bright_columns(render_panel(e))) for e in [0.1, 0.25, 0.5, 0.75, 1.0, 3.0]]
    assert widths == sorted(widths)
    assert widths[-1] == widths[-2] == MAX_BAR_WIDTH
    assert widths[0] > 0
    assert render_panel(-1.0)[:, 0, 0].min() == 255  # full height


def test_panel_progress_line_rises():
    low = np.flatnonzero(render_panel(0.0, 0.0)[:, 0, 1])
    high = np.flatnonzero(render_panel(0.0, 1.0)[:, 0, 1])
    assert low.min() > high.min()
    with pytest.raises(ValueError):
        render_panel(float("nan"))


def test_attitude_reinforcement():
    kw = dict(climbing=True, deadband_deg=0.3)
    assert attitude_reinforcement(5.0, 4.0, **kw) == REWARD
    assert attitude_reinforcement(-5.0, -4.0, **kw) == REWARD
    assert attitude_reinforcement(4.0, 5.0, **kw) == AVERSIVE
    assert attitude_reinforcement(4.0, 4.1, **kw) == NONE
    assert attitude_reinforcement(5.0, 4.0, climbing=False, deadband_deg=0.3) == NONE
    assert attitude_reinforcement(5.0, 4.0, failed=True, **kw) == AVERSIVE
    with pytest.raises(ValueError):
        attitude_reinforcement(0.0, 0.0, climbing=True, deadband_deg=0.0)


def test_progress_reinforcement():
    assert progress_reinforcement(50.0, deadband=20) == REWARD
    assert progress_reinforcement(-50.0, deadband=20) == AVERSIVE
    assert progress_reinforcement(5.0, deadband=20) == NONE
    assert progress_reinforcement(50.0, deadband=20, failed=True) == AVERSIVE
