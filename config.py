"""
Configuration module for Machine Health Failure Prediction Service.
Uses Pydantic BaseSettings for environment-variable-driven config.
"""

from __future__ import annotations

import os
from typing import List

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application-wide settings, overridable via environment variables."""

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "Machine Health Prediction Service"
    app_version: str = "2.1.0"
    debug: bool = False

    # ── Model metadata ───────────────────────────────────────────────────
    model_version: str = "v2.1.0"
    model_trained_at: str = "2026-02-15"

    # ── Authentication ───────────────────────────────────────────────────
    api_keys: List[str] = Field(
        default=[
            "dev-api-key-001",
            "dev-api-key-002",
        ],
        description="Accepted API keys (set via comma-separated env var API_KEYS)",
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )

    # ── Rate Limiting ────────────────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./feedback.db"

    # ── Server ───────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance used throughout the application
settings = Settings()
