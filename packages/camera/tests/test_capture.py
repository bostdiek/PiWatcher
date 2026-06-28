from pathlib import Path

from piwatcher_camera.capture import CaptureSession, CaptureState


def test_given_idle_session_when_motion_occurs_then_starts_capturing() -> None:
    # Arrange
    session = CaptureSession(min_duration=60.0, cooldown_duration=5.0)

    # Act
    session.on_motion(now=100.0)

    # Assert
    assert session.state is CaptureState.CAPTURING
    assert session.start_time == 100.0


def test_given_cooldown_when_new_motion_occurs_then_returns_to_capturing() -> None:
    # Arrange
    session = CaptureSession(min_duration=1.0, cooldown_duration=5.0)
    session.on_motion(now=100.0)
    session.tick(now=106.0)

    # Act
    session.on_motion(now=107.0)

    # Assert
    assert session.state is CaptureState.CAPTURING


def test_given_min_duration_not_elapsed_when_tick_then_keeps_capturing() -> None:
    # Arrange
    session = CaptureSession(min_duration=60.0, cooldown_duration=5.0)
    session.on_motion(now=100.0)

    # Act
    state = session.tick(now=110.0)

    # Assert
    assert state is CaptureState.CAPTURING


def test_given_cooldown_complete_when_finish_then_returns_frame_paths() -> None:
    # Arrange
    session = CaptureSession(min_duration=1.0, cooldown_duration=5.0)
    frame_path = Path("frame.jpg")
    session.on_motion(now=100.0)
    session.on_frame_captured(frame_path, now=100.5)
    session.tick(now=106.0)
    session.tick(now=111.0)

    # Act
    frames = session.finish()

    # Assert
    assert frames == [frame_path]
    assert session.state is CaptureState.IDLE
