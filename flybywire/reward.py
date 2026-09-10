"""Engineered reinforcement. Not modeled pleasure or pain; a current into named cells.

Two schemes. `attitude` is the default because it is informative at 50 ms resolution:
during a burn the apoapsis rises no matter how badly the rocket is steered, so
`progress` mostly rewards the engine, not the pilot.
"""

import math

REWARD, AVERSIVE, NONE = "reward", "aversive", "none"
SCHEMES = ("attitude", "progress")


def _check(*values):
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite reinforcement input")


def progress_reinforcement(progress_delta, *, deadband, failed=False):
    """Change in mission score (metres of apoapsis) since the last observation."""
    _check(progress_delta, deadband)
    if deadband <= 0:
        raise ValueError("Positive deadband required")
    if failed or progress_delta <= -deadband:
        return AVERSIVE
    if progress_delta >= deadband:
        return REWARD
    return NONE


def attitude_reinforcement(previous_error_deg, error_deg, *, climbing, deadband_deg, failed=False):
    """Reward when the nose moved back toward the needle while the rocket was climbing;
    aversive when it drifted away by more than the deadband, or on any failure."""
    _check(previous_error_deg, error_deg, deadband_deg)
    if deadband_deg <= 0:
        raise ValueError("Positive deadband required")
    if failed:
        return AVERSIVE
    change = abs(error_deg) - abs(previous_error_deg)
    if change >= deadband_deg:
        return AVERSIVE
    if change <= -deadband_deg and climbing:
        return REWARD
    return NONE
