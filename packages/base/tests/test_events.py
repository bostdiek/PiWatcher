"""Event endpoint tests."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from piwatcher_base.models import Event, Frame


@pytest.mark.asyncio()
async def test_given_event_upload_when_create_event_then_stores_event_and_frames(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    classification_calls: list[int] = []

    async def classify_stub(event_id: int, _frame_paths: object) -> None:
        classification_calls.append(event_id)

    monkeypatch.setattr(
        "piwatcher_base.routes.events.classify_event_background",
        classify_stub,
    )
    files = [
        ("frames", ("frame1.jpg", b"jpeg-one", "image/jpeg")),
        ("frames", ("frame2.jpg", b"jpeg-two", "image/jpeg")),
    ]
    data = {
        "camera_id": "feeder-cam",
        "event_start": "2026-06-27T14:32:01Z",
        "battery_pct": "88",
    }

    # Act
    response = await client.post("/api/events", data=data, files=files, headers=auth_headers)

    # Assert
    assert response.status_code == 201
    event = await db_session.scalar(select(Event).where(Event.camera_id == "feeder-cam"))
    assert event is not None
    assert event.frame_count == 2
    frame_paths = (
        await db_session.scalars(select(Frame.file_path).where(Frame.event_id == event.id))
    ).all()
    assert len(frame_paths) == 2
    assert classification_calls == [event.id]


@pytest.mark.asyncio()
async def test_given_stored_event_when_list_events_then_returns_recent_events(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(Event(camera_id="feeder-cam", event_start=datetime.now(UTC), frame_count=1))
    await db_session.commit()

    # Act
    response = await client.get("/api/events")

    # Assert
    assert response.status_code == 200
    assert response.json()[0]["camera_id"] == "feeder-cam"
