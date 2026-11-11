"""Image providers.

`local` renders procedurally with Pillow — no API key, no network, fully
deterministic. `gemini` calls Google's image model when a key is configured.
Both return PNG bytes so the rest of the app never cares which one ran.
"""

from __future__ import annotations

from app.config import settings
from app.prompting import SceneSpec
from app.providers.base import ProviderError, ProviderResult
from app.providers.gemini import GeminiProvider
from app.providers.local import LocalProvider

__all__ = [
    "ProviderError",
    "ProviderResult",
    "GeminiProvider",
    "LocalProvider",
    "get_provider",
]


def get_provider(name: str | None = None):
    """Resolve a provider by name, falling back to the configured default."""
    chosen = (name or settings.image_provider or "local").lower()
    if chosen == "gemini":
        if not settings.gemini_api_key:
            raise ProviderError(
                "Gemini provider selected but GEMINI_API_KEY is not set. "
                "Set it in the environment, or use the local provider."
            )
        return GeminiProvider()
    if chosen == "local":
        return LocalProvider()
    raise ProviderError(f"Unknown provider '{chosen}'. Use 'local' or 'gemini'.")


def render(spec: SceneSpec, provider_name: str | None = None) -> ProviderResult:
    return get_provider(provider_name).generate(spec)
