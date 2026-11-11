"""Gemini image provider — opt-in, only used when GEMINI_API_KEY is set."""

from __future__ import annotations

import base64
import time

import httpx

from app.config import settings
from app.prompting import SceneSpec
from app.providers.base import ProviderError, ProviderResult


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self.model = settings.gemini_image_model

    def _build_prompt(self, spec: SceneSpec) -> str:
        parts = [spec.prompt.strip()]
        parts.append(f"Style: {spec.style}. Mood: {spec.mood}. Palette: {spec.palette_name}.")
        parts.append(f"Aspect ratio {spec.width}:{spec.height}.")
        if spec.negative_prompt.strip():
            parts.append(f"Avoid: {spec.negative_prompt.strip()}.")
        return " ".join(parts)

    def generate(self, spec: SceneSpec) -> ProviderResult:
        if not settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is not configured.")

        url = f"{settings.gemini_endpoint}/{self.model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": self._build_prompt(spec)}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(
                    url,
                    json=body,
                    headers={
                        "x-goog-api-key": settings.gemini_api_key,
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc

        if resp.status_code != 200:
            raise ProviderError(f"Gemini returned HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise ProviderError("Gemini response had no image parts.") from exc

        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                payload = base64.b64decode(inline["data"])
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                elapsed = int((time.perf_counter() - started) * 1000)
                return ProviderResult(
                    image_bytes=payload,
                    mime=mime,
                    provider=self.name,
                    model=self.model,
                    render_ms=elapsed,
                )

        raise ProviderError("Gemini returned no inline image data.")
