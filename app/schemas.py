"""Request/response models. Every input is bounded."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings

AspectRatio = Literal["1:1", "3:2", "2:3", "16:9", "9:16", "4:5"]
StyleName = Literal["cinematic", "neon", "watercolor", "minimal", "retro", "dreamy"]
ProviderName = Literal["local", "gemini"]


# --- auth -----------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    created_at: datetime


# --- generation -----------------------------------------------------------
class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=settings.max_prompt_length)
    negative_prompt: str = Field(default="", max_length=settings.max_negative_prompt_length)
    # None means "read the style out of the prompt"; an explicit value wins.
    style: StyleName | None = None
    aspect_ratio: AspectRatio = "1:1"
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    provider: ProviderName | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("prompt must be at least 3 characters after trimming")
        return cleaned


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt: str
    negative_prompt: str
    style: str
    aspect_ratio: str
    width: int
    height: int
    seed: int
    provider: str
    model: str
    render_ms: int
    is_favourite: bool
    created_at: datetime
    image_url: str
    thumb_url: str


class GenerationList(BaseModel):
    items: list[GenerationOut]
    total: int
    limit: int
    offset: int


class FavouriteRequest(BaseModel):
    is_favourite: bool


class PromptPreview(BaseModel):
    """What the parser understood — shown in the UI so nothing is a black box."""

    palette: str
    subject: str
    style: str
    mood: str
    seed: int
    size: str
    matched_keywords: list[str]


class ProviderInfo(BaseModel):
    name: str
    available: bool
    model: str
    note: str


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    provider: str
