"""FastAPI application for PiWatcher base station."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from importlib import import_module

from fastapi import FastAPI

from .config import get_settings
from .db import close_db, init_db
from .routes import events, heartbeat


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up application resources."""

    await init_db()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(title="PiWatcher", lifespan=lifespan)
app.include_router(events.router, prefix="/api")
app.include_router(heartbeat.router, prefix="/api")

with suppress(ModuleNotFoundError, AttributeError):
    dashboard = import_module("piwatcher_base.routes.dashboard")
    app.include_router(dashboard.router)


def run() -> None:
    """Run the PiWatcher API server with uvicorn."""

    import uvicorn

    get_settings()
    uvicorn.run(app, host="0.0.0.0", port=8000)
