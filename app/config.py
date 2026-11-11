"""Application settings, loaded from the environment only."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Vercel's filesystem is read-only except /tmp, so fall back there."""
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/rang.db"
    return "sqlite:///./rang.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Rang"
    version: str = "1.0.0"

    # Auth
    secret_key: str = "dev-only-insecure-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Storage
    database_url: str = _default_database_url()

    # Image generation
    image_provider: str = "local"  # "local" | "gemini"
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models"

    # Limits
    max_prompt_length: int = 800
    max_negative_prompt_length: int = 400
    max_image_side: int = 1536
    min_image_side: int = 256
    rate_limit_generate: str = "20/minute"
    rate_limit_default: str = "120/minute"

    # CORS: comma separated, "*" allows everything
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
