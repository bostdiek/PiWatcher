"""Async database connection and session management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings
from .models import Base

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize the async SQLAlchemy engine and session factory."""

    global SessionLocal, engine

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def close_db() -> None:
    """Dispose of the active database engine."""

    global SessionLocal, engine

    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None


async def create_all_tables() -> None:
    """Create tables for lightweight SQLite test setups."""

    if engine is None:
        await init_db()
    if engine is None:
        raise RuntimeError("Database engine was not initialized")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a database session for FastAPI dependencies."""

    if SessionLocal is None:
        await init_db()
    if SessionLocal is None:
        raise RuntimeError("Database session factory was not initialized")
    session = SessionLocal()
    try:
        yield session
    finally:
        if session.in_transaction():
            await session.rollback()
        await session.close()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a database session for background tasks."""

    if SessionLocal is None:
        await init_db()
    if SessionLocal is None:
        raise RuntimeError("Database session factory was not initialized")
    session = SessionLocal()
    try:
        yield session
    finally:
        if session.in_transaction():
            await session.rollback()
        await session.close()
