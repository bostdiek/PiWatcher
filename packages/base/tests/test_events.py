"""Event endpoint tests."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


@pytest.mark.asyncio()
async def test_given_duplicate_camera_event_id_when_create_event_then_returns_existing_event(
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
    files = [("frames", ("frame1.jpg", b"jpeg-one", "image/jpeg"))]
    data = {
        "camera_id": "feeder-cam",
        "event_start": "2026-06-27T14:32:01Z",
        "camera_event_id": "20260627T143201000000Z-feeder-cam",
    }

    # Act
    first = await client.post("/api/events", data=data, files=files, headers=auth_headers)
    second = await client.post("/api/events", data=data, files=files, headers=auth_headers)

    # Assert
    assert first.status_code == 201
    assert second.status_code == 201
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["event_id"] == second_payload["event_id"]

    events = (await db_session.scalars(select(Event).where(Event.camera_id == "feeder-cam"))).all()
    assert len(events) == 1
    assert events[0].camera_event_id == "20260627T143201000000Z-feeder-cam"
    assert classification_calls == [events[0].id]


@pytest.mark.asyncio()
async def test_given_legacy_upload_without_camera_event_id_when_retried_then_creates_new_event(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def classify_stub(_event_id: int, _frame_paths: object) -> None:
        return None

    monkeypatch.setattr(
        "piwatcher_base.routes.events.classify_event_background",
        classify_stub,
    )
    files = [("frames", ("frame1.jpg", b"jpeg-one", "image/jpeg"))]
    data = {
        "camera_id": "feeder-cam",
        "event_start": "2026-06-27T14:32:01Z",
    }

    # Act
    first = await client.post("/api/events", data=data, files=files, headers=auth_headers)
    second = await client.post("/api/events", data=data, files=files, headers=auth_headers)

    # Assert
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["event_id"] != second.json()["event_id"]

    events = (await db_session.scalars(select(Event).where(Event.camera_id == "feeder-cam"))).all()
    assert len(events) == 2


@pytest.mark.asyncio()
async def test_given_commit_time_idempotency_race_when_create_event_then_returns_existing_event(
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

    files = [("frames", ("frame1.jpg", b"jpeg-one", "image/jpeg"))]
    data = {
        "camera_id": "feeder-cam",
        "event_start": "2026-06-27T14:32:01Z",
        "camera_event_id": "20260627T143201000000Z-feeder-cam",
    }

    first = await client.post("/api/events", data=data, files=files, headers=auth_headers)
    assert first.status_code == 201
    first_event_id = first.json()["event_id"]

    real_commit = db_session.commit
    commit_call_count = 0

    async def commit_with_one_integrity_error() -> None:
        nonlocal commit_call_count
        commit_call_count += 1
        if commit_call_count == 1:
            raise IntegrityError(
                statement="duplicate key",
                params=None,
                orig=Exception("duplicate key"),
            )
        await real_commit()

    monkeypatch.setattr(db_session, "commit", commit_with_one_integrity_error)

    # Act
    second = await client.post("/api/events", data=data, files=files, headers=auth_headers)

    # Assert
    assert second.status_code == 201
    assert second.json()["event_id"] == first_event_id
    events = (await db_session.scalars(select(Event).where(Event.camera_id == "feeder-cam"))).all()
    assert len(events) == 1
    assert classification_calls == [first_event_id]
