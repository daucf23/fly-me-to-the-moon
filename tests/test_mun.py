import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from flybywire.ksp.mun import MunConfig, MunMission


def ascent_mission(prograde_pitch, speed=300):
    """Surface-frame velocity fixture; pitch is measured away from vertical."""
    p = math.radians(prograde_pitch)
    flight = SimpleNamespace(velocity=(speed * math.cos(p), 0, speed * math.sin(p)))
    body = SimpleNamespace(reference_frame='surface')
    m = object.__new__(MunMission)
    m.c = MunConfig()
    m.v = SimpleNamespace(orbit=SimpleNamespace(body=body), surface_reference_frame='surface', flight=lambda frame: flight)
    m.sc = SimpleNamespace(transform_direction=lambda vector, source, destination: vector)
    return m


def test_ascent_does_not_follow_a_falling_velocity_vector_into_the_sea():
    # Failed fly-8 at 16.2 km: program 52 deg from vertical, velocity 83.5 deg.
    m = ascent_mission(83.5)
    program = m.program_pitch(16_200)
    assert m.ascent_pitch(16_200) <= program + m.c.max_aoa_deg


@pytest.mark.parametrize('altitude,prograde,cap', [(8_000, 15, 3), (30_000, 40, 10)])
def test_normal_gravity_turn_still_limits_the_command_ahead_of_prograde(altitude, prograde, cap):
    m = ascent_mission(prograde)
    assert m.ascent_pitch(altitude) == pytest.approx(prograde + cap)


def test_ascent_program_is_unrestricted_above_the_atmospheric_guidance_limit():
    m = ascent_mission(20)
    assert m.ascent_pitch(50_000) == m.program_pitch(50_000)


def test_low_speed_velocity_noise_does_not_steer_the_launch():
    m = ascent_mission(160, speed=10)
    assert m.ascent_pitch(100) == 0


@pytest.mark.parametrize('phase,altitude,expected', [
    ('prelaunch', 100, .7), ('ascent', 10_000, .7),
    ('ascent', 45_000, .5), ('burn', 100_000, .5), ('entry', 10_000, .5),
])
def test_extra_authority_is_confined_to_atmospheric_ascent(phase, altitude, expected):
    m = ascent_mission(20)
    m.c = replace(m.c, authority=.5)
    m.phase = phase
    assert m.attitude_authority(altitude) == expected


def return_mission():
    m = object.__new__(MunMission)
    m.c = MunConfig()
    return m


def test_first_return_look_corrects_a_wide_miss_with_a_survival_budget():
    look, off, max_dv = return_mission().return_look({}, 20_000, 55_117)
    assert (look, off, max_dv) == ("corrected_back", True, 250.0)


def test_trim_is_not_refused_on_cost_and_is_judged_on_the_executed_periapsis():
    # Fly 9b: 46.3 km after the correction, 35 m/s trim refused at the old 30 m/s cap, skip.
    look, off, max_dv = return_mission().return_look({"corrected_back": True}, 1_540, 46_342)
    assert look == "trimmed_back" and off and max_dv >= 35.0


def test_trim_looks_again_after_each_burn_up_to_three_times():
    m = return_mission()
    assert m.return_look({"corrected_back": True, "trimmed_back": False, "trims_back": 1}, 1_300, 43_500)[1] is True
    assert m.return_look({"corrected_back": True, "trimmed_back": False, "trims_back": 3}, 1_300, 43_500) is None


def test_no_return_look_inside_the_last_ten_minutes_or_when_on_target():
    m = return_mission()
    assert m.return_look({"corrected_back": True}, 500, 46_000) is None
    assert m.return_look({"corrected_back": True}, 1_500, 36_000)[1] is False


def test_a_return_routed_via_the_mun_again_counts_as_off_target():
    assert return_mission().return_look({"corrected_back": True}, 1_500, None)[1] is True
