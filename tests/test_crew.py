import math

import numpy as np

from flybywire.ksp.crew import AutopilotCrew, Panels, angle_errors, choose_rear_signs, throttle_from_steer


def test_angle_errors_front_hemisphere_are_signed_angles():
    assert angle_errors((0, 1, 0)) == (0.0, 0.0)
    pitch, yaw = angle_errors((0.0, math.cos(math.radians(10)), -math.sin(math.radians(10))))
    assert abs(pitch - 10) < 1e-6 and abs(yaw) < 1e-6  # target above the nose: + pitch
    pitch, yaw = angle_errors((math.sin(math.radians(10)), math.cos(math.radians(10)), 0.0))
    assert abs(yaw - 10) < 1e-6 and abs(pitch) < 1e-6  # target to the right: + yaw


def test_angle_errors_behind_the_nose_do_not_chatter():
    # Straight behind with a whisker of lateral noise: atan2 would give ~180 on both
    # axes with random signs, and the ship would sit still. The rule is: pull up.
    assert angle_errors((1e-6, -1.0, 0.0)) == (180.0, 0.0)
    assert angle_errors((-1e-6, -1.0, 0.0)) == (180.0, 0.0)
    # With a clear lateral component the needle saturates along it...
    pitch, yaw = angle_errors((0.0, -0.5, -0.3))
    assert pitch == 180.0 and yaw == 0.0  # target above and behind: pull up, full scale
    # ...and the caller's remembered turn direction wins over the instantaneous sign,
    # so noise cannot reverse a turn that has begun.
    signs = choose_rear_signs((0.3, -0.9, 0.0))
    assert signs == (1.0, 1.0)
    pitch, yaw = angle_errors((-0.02, -0.99, 0.0), signs)
    assert yaw > 0
    # Continuous through the 90 degree boundary.
    just_front = angle_errors((0.0, 1e-9, -1.0))
    just_behind = angle_errors((0.0, -1e-9, -1.0))
    assert abs(just_front[0] - 90) < 1e-3 and abs(just_behind[0] - 180) < 1e-3


def test_throttle_from_steer_is_a_clipped_ramp_with_cutoff():
    assert throttle_from_steer(0.4) == 1.0
    assert throttle_from_steer(0.9) == 1.0
    assert throttle_from_steer(0.2) == 0.5
    assert throttle_from_steer(0.0) == 0.0
    assert throttle_from_steer(-0.3) == 0.0  # the decoder deadband is the cutoff


def test_panels_render_three_instruments_and_bob_sees_the_dv_bar_on_the_right():
    frames = Panels(error_scale_deg=5.0, dv_scale=40.0).render(
        {"pitch_error_deg": 2.5, "yaw_error_deg": -5.0, "dv_remaining": 40.0}
    )
    assert set(frames) == {"pitch", "yaw", "throttle"}
    for f in frames.values():
        assert f.shape == (160, 90, 3) and f.dtype == np.uint8
    # Engine inhibited or no burn: a dark panel, nothing for Bob's cells to respond to.
    dark = Panels().render({"pitch_error_deg": 0.0, "yaw_error_deg": 0.0, "dv_remaining": None})
    assert dark["throttle"].sum() == 0
    # The bar sits on the right; the left half carries only the panel's fixed markings.
    idle = Panels().render({"pitch_error_deg": 0.0, "yaw_error_deg": 0.0, "dv_remaining": 0.0})
    assert frames["throttle"][:, 45:].sum() > idle["throttle"][:, 45:].sum()
    assert frames["throttle"][:, :45].sum() == idle["throttle"][:, :45].sum()
    # A smaller remaining delta-v draws a narrower bar.
    small = Panels().render({"pitch_error_deg": 0.0, "yaw_error_deg": 0.0, "dv_remaining": 10.0})
    assert 0 < small["throttle"].sum() < frames["throttle"].sum()


def test_autopilot_crew_has_the_same_shape_as_the_flies():
    crew = AutopilotCrew()
    out = crew.act(None, {"pitch_error_deg": 5.0, "yaw_error_deg": -5.0, "dv_remaining": 40.0})
    assert set(out) == {"pitch", "yaw", "throttle"}
    assert out["pitch"][0] > 0 and out["yaw"][0] < 0
    assert throttle_from_steer(out["throttle"][0]) == 1.0
    out = crew.act(None, {"pitch_error_deg": 0.0, "yaw_error_deg": 0.0, "dv_remaining": None})
    assert throttle_from_steer(out["throttle"][0]) == 0.0
