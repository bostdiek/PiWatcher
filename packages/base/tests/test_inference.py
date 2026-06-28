"""Inference pipeline tests."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from piwatcher_base.inference import (
    WildlifeClassification,
    choose_classification,
    classification_prompt_text,
    classify_event_background,
    normalize_label,
    parse_classification_content,
    response_format_json_schema,
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


def test_given_fenced_json_when_parsed_then_returns_valid_classification() -> None:
    # Arrange
    content = """```json
{
  \"label\": \"person\",
  \"confidence\": 0.8,
  \"description\": \"A silhouette near the window.\"
}
```"""

    # Act
    classification = parse_classification_content(content)

    # Assert
    assert classification.label == "human"
    assert classification.confidence == pytest.approx(0.8)


def test_given_unknown_model_label_when_normalize_label_then_returns_unknown() -> None:
    # Act
    label = normalize_label("wildlife")

    # Assert
    assert label == "unknown"


def test_given_response_format_json_schema_when_built_then_contains_strict_schema() -> None:
    # Act
    response_format = response_format_json_schema()

    # Assert
    assert response_format["type"] == "json_schema"
    json_schema = response_format["json_schema"]
    assert json_schema["name"] == "frame_classification"
    assert json_schema["strict"] is True
    schema = json_schema["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["label", "confidence", "description"]
    assert schema["properties"]["label"]["enum"][-1] == "empty"


def test_given_classification_prompt_when_built_then_keeps_guidance_minimal() -> None:
    # Act
    prompt = classification_prompt_text()

    # Assert
    assert prompt.startswith("What is the main thing visible in this image?")
    assert "describe only what you actually see" in prompt
    assert "Use unknown if the subject is unclear" in prompt
    assert "empty if nothing relevant is visible" in prompt


@pytest.mark.asyncio()
async def test_given_classify_frame_when_called_then_sends_schema_constrained_response_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_base import inference

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg")
    captured_payload: dict[str, Any] = {}

    class ResponseStub:
        status_code = 200
        text = '{"ok": true}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"label":"deer","confidence":0.8,"description":"deer"}'
                        }
                    }
                ]
            }

    class AsyncClientStub:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]):
            captured_payload.update(json)
            return ResponseStub()

    monkeypatch.setattr(inference.httpx, "AsyncClient", AsyncClientStub)
    classifier = inference.LlamaSwapClassifier()

    # Act
    result = await classifier.classify_frame(frame_path)

    # Assert
    assert result.label == "deer"
    assert captured_payload["response_format"]["type"] == "json_schema"
    assert captured_payload["response_format"]["json_schema"]["strict"] is True
    assert captured_payload["messages"][0]["content"][0]["text"] == classification_prompt_text()


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


@pytest.mark.asyncio()
async def test_given_successful_inference_when_classify_event_then_logs_start_and_finish(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_base import inference

    event = Event(camera_id="feeder-cam", event_start=datetime.now(UTC), frame_count=1)
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg")

    settings = inference.get_settings()
    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "inference_gap_seconds", 0)
    monkeypatch.setattr(inference, "get_settings", lambda: settings)
    monkeypatch.setattr(
        inference,
        "wait_for_safe_temperature",
        lambda _settings: inference.asyncio.sleep(0),
    )

    async def classify_stub(_self, _frame_path):
        return WildlifeClassification(label="deer", confidence=0.9, description="deer")

    monkeypatch.setattr(
        inference.LlamaSwapClassifier,
        "classify_frame",
        classify_stub,
    )
    monkeypatch.setattr(
        inference,
        "notify_detection",
        lambda *args, **kwargs: inference.asyncio.sleep(0),
    )
    caplog.set_level("INFO", logger="piwatcher_base.inference")

    # Act
    await classify_event_background(event.id, [frame_path])

    # Assert
    assert "Starting inference for event" in caplog.text
    assert "Finished inference for event" in caplog.text
