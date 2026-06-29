from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import requests


class _DummyResponse:
    def raise_for_status(self) -> None:
        return None


def test_given_event_end_when_upload_event_then_includes_end_and_camera_event_id(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_camera.transfer import upload_event

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _DummyResponse()

    monkeypatch.setattr("piwatcher_camera.transfer.requests.post", fake_post)

    # Act
    result = upload_event(
        frames=[frame_path],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        battery_pct=74,
        event_start=datetime(2026, 6, 28, 16, 0, 0, tzinfo=UTC),
        event_end=datetime(2026, 6, 28, 16, 0, 5, tzinfo=UTC),
        camera_event_id="20260628T160000000000Z-camera-a",
    )

    # Assert
    assert result is True
    assert captured["url"] == "http://pi5.local:8000/api/events"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["timeout"] == 60.0
    data = cast("dict[str, str]", captured["data"])
    assert data["camera_id"] == "camera-a"
    assert data["battery_pct"] == "74"
    assert data["event_start"] == "2026-06-28T16:00:00+00:00"
    assert data["event_end"] == "2026-06-28T16:00:05+00:00"
    assert data["camera_event_id"] == "20260628T160000000000Z-camera-a"


def test_given_missing_event_end_and_id_when_upload_event_then_omits_optional_fields(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_camera.transfer import upload_event

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _DummyResponse()

    monkeypatch.setattr("piwatcher_camera.transfer.requests.post", fake_post)

    # Act
    result = upload_event(
        frames=[frame_path],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )

    # Assert
    assert result is True
    data = cast("dict[str, str]", captured["data"])
    assert "event_end" not in data
    assert "camera_event_id" not in data


def test_given_request_failure_when_upload_event_then_returns_false(monkeypatch, tmp_path) -> None:
    # Arrange
    import requests

    from piwatcher_camera.transfer import upload_event

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")

    def fail_post(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr("piwatcher_camera.transfer.requests.post", fail_post)

    # Act
    result = upload_event(
        frames=[frame_path],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )

    # Assert
    assert result is False


def test_given_empty_frames_when_upload_event_then_returns_false() -> None:
    # Arrange
    from piwatcher_camera.transfer import upload_event

    # Act
    result = upload_event(
        frames=[],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )

    # Assert
    assert result is False


def test_given_http_503_error_when_classify_upload_error_then_marks_retryable() -> None:
    # Arrange
    from piwatcher_camera.transfer import classify_upload_error

    response = requests.Response()
    response.status_code = 503
    response.url = "http://pi5.local:8000/api/events"
    error = requests.HTTPError("server error", response=response)

    # Act
    classification = classify_upload_error(error)

    # Assert
    assert classification.retryable is True
    assert classification.terminal is False
    assert "503" in classification.reason


def test_given_http_400_error_when_classify_upload_error_then_marks_terminal() -> None:
    # Arrange
    from piwatcher_camera.transfer import classify_upload_error

    response = requests.Response()
    response.status_code = 400
    response.url = "http://pi5.local:8000/api/events"
    error = requests.HTTPError("bad request", response=response)

    # Act
    classification = classify_upload_error(error)

    # Assert
    assert classification.retryable is False
    assert classification.terminal is True
    assert "invalid upload payload" in classification.reason


def test_given_http_401_error_when_classify_upload_error_then_marks_terminal_auth() -> None:
    # Arrange
    from piwatcher_camera.transfer import classify_upload_error

    response = requests.Response()
    response.status_code = 401
    response.url = "http://pi5.local:8000/api/events"
    error = requests.HTTPError("unauthorized", response=response)

    # Act
    classification = classify_upload_error(error)

    # Assert
    assert classification.retryable is False
    assert classification.terminal is True
    assert "authorization failed" in classification.reason


def test_given_request_timeout_when_upload_event_result_then_returns_retryable_failure(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_camera.transfer import upload_event_result

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")

    def fail_post(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr("piwatcher_camera.transfer.requests.post", fail_post)

    # Act
    result = upload_event_result(
        frames=[frame_path],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )

    # Assert
    assert result.success is False
    assert result.classification is not None
    assert result.classification.retryable is True
    assert result.classification.terminal is False


def test_given_empty_frames_when_upload_event_result_then_returns_terminal_failure() -> None:
    # Arrange
    from piwatcher_camera.transfer import upload_event_result

    # Act
    result = upload_event_result(
        frames=[],
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )

    # Assert
    assert result.success is False
    assert result.classification is not None
    assert result.classification.retryable is False
    assert result.classification.terminal is True
