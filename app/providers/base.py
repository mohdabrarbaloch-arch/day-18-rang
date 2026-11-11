"""Shared provider contract."""

from __future__ import annotations

from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request."""


@dataclass
class ProviderResult:
    image_bytes: bytes
    mime: str
    provider: str
    model: str
    render_ms: int
