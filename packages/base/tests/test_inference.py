"""Inference pipeline tests."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from piwatcher_base.inference import (
    WildlifeClassification,
    choose_classification,
    classify_event_background,
    sample_frame_paths,
)
from piwatcher_base.models import Event


def test_given_many_frames_when_sample_frame_paths_then_returns_even_sample(
    tmp_path,
) -> None:
    # Arrange
    paths = [tmp_path / f"frame_{index}.jpg" for index in range(10)]

    # Act
    sampled = sample_frame_paths(paths, sample_count=5)

    # Assert
    assert sampled == [paths[0], paths[2], paths[4], paths[7], paths[9]]


def test_given_mixed_results_when_choose_classification_then_returns_majority_label() -> None:
    # Arrange
    results = [
        WildlifeClassification(label="deer", confidence=0.6, description="deer"),
        WildlifeClassification(label="deer", confidence=0.8, description="deer"),
        WildlifeClassification(label="empty", confidence=0.9, description="empty"),
    ]

    # Act
    selected = choose_classification(results)

    # Assert
    assert selected.label == "deer"


@pytest.mark.asyncio()
async def test_given_hot_cpu_when_wait_for_safe_temperature_then_sleeps_until_cool(
    monkeypatch: pytest.MonkeyPatch,
    test_settings,
) -> None:
    # Arrange
    from piwatcher_base import inference

    monkeypatch.setattr(test_settings, "max_inference_temp_c", 72.0)
    monkeypatch.setattr(test_settings, "cooldown_temp_c", 60.0)
    temperatures = iter([75.0, 70.0, 59.0])
    sleep_calls: list[int] = []

    async def sleep_stub(seconds: int) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(inference, "get_cpu_temp", lambda: next(temperatures))
    monkeypatch.setattr(inference.asyncio, "sleep", sleep_stub)

    # Act
    await inference.wait_for_safe_temperature(test_settings)

    # Assert
    assert sleep_calls == [5]


@pytest.mark.asyncio()
async def test_given_inference_disabled_when_classify_event_then_leaves_event_unclassified(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_base import inference

    event = Event(camera_id="feeder-cam", event_start=datetime.now(UTC), frame_count=1)
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    settings = inference.get_settings()
    monkeypatch.setattr(settings, "inference_enabled", False)
    monkeypatch.setattr(inference, "get_settings", lambda: settings)

    # Act
    await classify_event_background(event.id, [tmp_path / "frame.jpg"])
    await db_session.refresh(event)

    # Assert
    assert event.label is None
    assert event.classified_at is None
