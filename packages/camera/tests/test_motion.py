import numpy as np
import pytest

from piwatcher_camera.motion import detect_motion


def test_given_identical_frames_when_detect_motion_then_no_motion_detected() -> None:
    # Arrange
    previous_frame = np.zeros((10, 10), dtype=np.uint8)
    current_frame = np.zeros((10, 10), dtype=np.uint8)

    # Act
    result = detect_motion(current_frame, previous_frame)

    # Assert
    assert result.detected is False
    assert result.changed_pct == 0.0


def test_given_significant_frame_change_when_detect_motion_then_motion_detected() -> None:
    # Arrange
    previous_frame = np.zeros((10, 10), dtype=np.uint8)
    current_frame = previous_frame.copy()
    current_frame[:3, :] = 50

    # Act
    result = detect_motion(current_frame, previous_frame, threshold=7.0, min_changed_pct=2.0)

    # Assert
    assert result.detected is True
    assert result.changed_pct == 30.0


@pytest.mark.parametrize(("changed_pixels", "expected"), [(2, True), (1, False)])
def test_given_threshold_boundary_when_detect_motion_then_uses_minimum_changed_pct(
    changed_pixels: int,
    expected: bool,
) -> None:
    # Arrange
    previous_frame = np.zeros((10, 10), dtype=np.uint8)
    current_frame = previous_frame.copy().reshape(-1)
    current_frame[:changed_pixels] = 25
    current_frame = current_frame.reshape(10, 10)

    # Act
    result = detect_motion(current_frame, previous_frame, threshold=7.0, min_changed_pct=2.0)

    # Assert
    assert result.detected is expected
