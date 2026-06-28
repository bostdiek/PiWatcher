"""Authentication tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_given_missing_token_when_post_event_then_returns_422(
    client: AsyncClient,
) -> None:
    # Act
    response = await client.post("/api/heartbeat", params={"camera_id": "feeder"})

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio()
async def test_given_invalid_token_when_post_heartbeat_then_returns_401(
    client: AsyncClient,
) -> None:
    # Act
    response = await client.post(
        "/api/heartbeat",
        params={"camera_id": "feeder"},
        headers={"Authorization": "Bearer wrong"},
    )

    # Assert
    assert response.status_code == 401
