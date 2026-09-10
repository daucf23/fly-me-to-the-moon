"""The cockpit as the fly sees it: a dark 90x160 panel with a needle at the edge.

Calibration (`flybywire calibrate`, docs/calibration.md) showed that the only descending
neurons this retina drives respond to the far lateral field, monotonically with the area
lit, and saturate in brightness. So the needle is a full-height bar anchored to the panel
edge on the side the nose must move toward, and its width grows with the error. Above
about 25 px the network changes regime, so the bar is capped at MAX_BAR_WIDTH.
"""

import numpy as np

HEIGHT, WIDTH = 160, 90
MAX_BAR_WIDTH = 20
BAR_VALUE = 255
PROGRESS_VALUE = 70


def render_panel(steer_error, progress=0.0, *, max_width=MAX_BAR_WIDTH):
    """steer_error in [-1, 1]: +1 means the nose must move right (toward +x); the bar
    appears on the right edge. progress in [0, 1]: fraction of the altitude goal, a dim
    line that rises with it."""
    if not np.isfinite(steer_error) or not np.isfinite(progress):
        raise ValueError("Nonfinite instrument value")
    if not 0 < max_width <= WIDTH // 3:
        raise ValueError("Bar width must stay within the lateral third of the panel")
    panel = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    e = float(np.clip(steer_error, -1, 1))
    width = int(round(abs(e) * max_width))
    if width:
        if e > 0:
            panel[:, WIDTH - width :] = BAR_VALUE
        else:
            panel[:, :width] = BAR_VALUE
    row = HEIGHT - 1 - int(round(float(np.clip(progress, 0, 1)) * (HEIGHT - 1)))
    panel[row, :, 1] = np.maximum(panel[row, :, 1], PROGRESS_VALUE)
    return panel


def black_panel():
    """Control condition: the fly flies blind."""
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
