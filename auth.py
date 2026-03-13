"""
API Key authentication dependency for FastAPI.
Validates the X-API-Key header against the configured list of accepted keys.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings

# Header scheme — auto-documented in OpenAPI
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """
    FastAPI dependency that enforces API key authentication.

    Returns the validated key string so downstream handlers can use it
    for tenant-level auditing or rate-limit bucketing.

    Raises:
        HTTPException 401 if the key is missing or not recognised.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it via the X-API-Key header.",
        )
    if api_key not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return api_key
