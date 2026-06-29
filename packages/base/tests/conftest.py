"""Shared fixtures for base station tests."""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from piwatcher_base.config import Settings, get_settings
from piwatcher_base.db import close_db, get_db
from piwatcher_base.main import app
from piwatcher_base.models import Base


@pytest.fixture(autouse=True)
def test_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Override settings for isolated tests."""

    settings = Settings(
        api_key="test-token",
        database_url="sqlite+aiosqlite:///:memory:",
        frame_storage_path=tmp_path / "frames",
        inference_gap_seconds=0,
    )
    monkeypatch.setattr("piwatcher_base.config.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.auth.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.db.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.routes.events.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.routes.dashboard.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.inference.get_settings", lambda: settings)
    monkeypatch.setattr("piwatcher_base.routes.heartbeat.get_settings", lambda: settings)
    asyncio.run(close_db())
    get_settings.cache_clear()
    yield settings
    asyncio.run(close_db())
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest_asyncio.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """Provide an isolated SQLite database session."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Provide an ASGI test client with DB override."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Return valid test auth headers."""

    return {"Authorization": "Bearer test-token"}
