import numpy as np

from screensense.core.frame_diff import changed_percent


def test_changed_percent_zero_for_identical_frames() -> None:
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = np.zeros((10, 10, 3), dtype=np.uint8)
    assert changed_percent(a, b) == 0.0


def test_changed_percent_hundred_for_shape_change() -> None:
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = np.zeros((12, 10, 3), dtype=np.uint8)
    assert changed_percent(a, b) == 100.0

