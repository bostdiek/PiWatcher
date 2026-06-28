"""API authentication helpers."""

import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings


async def verify_api_key(authorization: str = Header(...)) -> None:
    """Verify pre-shared bearer token using constant-time comparison."""

    expected = f"Bearer {get_settings().api_key}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
