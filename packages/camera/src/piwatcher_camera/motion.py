"""Frame differencing motion detection using NumPy on the lores stream."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class MotionResult:
    """Motion detection metrics for a pair of frames."""

    detected: bool
    changed_pct: float
    mean_diff: float


def detect_motion(
    current_frame: NDArray[np.integer],
    previous_frame: NDArray[np.integer],
    threshold: float = 7.0,
    min_changed_pct: float = 2.0,
) -> MotionResult:
    """Compare two grayscale lores frames for motion.

    Args:
        current_frame: Current lores frame as a two-dimensional array.
        previous_frame: Previous lores frame as a two-dimensional array.
        threshold: Per-pixel difference threshold.
        min_changed_pct: Minimum changed pixel percentage to trigger motion.

    Returns:
        Detection result and frame-difference metrics.

    Raises:
        ValueError: If frame shapes differ or frames are empty.
    """
    if current_frame.shape != previous_frame.shape:
        raise ValueError("current_frame and previous_frame must have the same shape")
    if current_frame.size == 0:
        raise ValueError("frames must not be empty")

    diff = np.abs(current_frame.astype(np.int16) - previous_frame.astype(np.int16))
    changed_pixels = int(np.count_nonzero(diff > threshold))
    changed_pct = changed_pixels / diff.size * 100.0
    mean_diff = float(np.mean(diff))

    return MotionResult(
        detected=changed_pct >= min_changed_pct,
        changed_pct=changed_pct,
        mean_diff=mean_diff,
    )
