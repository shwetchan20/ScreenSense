from __future__ import annotations

import numpy as np


def changed_percent(previous: np.ndarray, current: np.ndarray, tolerance: int = 20) -> float:
    if previous.shape != current.shape:
        return 100.0
    delta = np.abs(current.astype(np.int16) - previous.astype(np.int16))
    changed = np.any(delta > tolerance, axis=2)
    return float(changed.mean() * 100.0)

