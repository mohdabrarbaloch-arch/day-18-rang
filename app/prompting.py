"""Turn a free-text prompt into a structured, renderable scene description.

The parser is deliberately simple and explainable: it looks for known
keywords and maps them onto palettes, subjects and moods. Everything it
decides is returned in the spec, so the UI can show the user *why* an
image came out the way it did. No hidden model, no black box.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# --- palettes -------------------------------------------------------------
# Each palette is a list of RGB stops, dark -> light.
PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "sunset": [(28, 16, 48), (120, 40, 90), (222, 96, 74), (255, 186, 112)],
    "ocean": [(6, 24, 48), (12, 62, 96), (32, 128, 158), (150, 220, 226)],
    "forest": [(10, 26, 18), (24, 62, 40), (58, 118, 66), (176, 208, 140)],
    "desert": [(48, 28, 20), (128, 78, 44), (206, 148, 88), (246, 220, 176)],
    "neon": [(8, 4, 24), (72, 12, 120), (216, 32, 160), (64, 232, 232)],
    "mono": [(12, 12, 14), (58, 58, 64), (140, 140, 148), (238, 238, 242)],
    "pastel": [(226, 214, 236), (246, 206, 214), (250, 226, 196), (214, 240, 226)],
    "ember": [(16, 8, 8), (86, 20, 16), (188, 62, 28), (250, 176, 72)],
    "arctic": [(14, 22, 38), (46, 78, 112), (128, 176, 208), (238, 248, 252)],
    "rose": [(40, 12, 28), (110, 30, 62), (196, 78, 108), (250, 196, 200)],
}

PALETTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sunset": ("sunset", "dusk", "golden hour", "sunrise", "evening", "shaam", "twilight"),
    "ocean": ("ocean", "sea", "water", "wave", "beach", "underwater", "samundar", "river"),
    "forest": ("forest", "tree", "jungle", "leaf", "green", "moss", "ban", "nature"),
    "desert": ("desert", "sand", "dune", "camel", "registan", "arid", "sahara"),
    "neon": ("neon", "cyberpunk", "synthwave", "futuristic", "glow", "electric", "vaporwave"),
    "mono": ("black and white", "monochrome", "noir", "grayscale", "b&w", "minimal"),
    "pastel": ("pastel", "soft", "gentle", "dreamy", "cute", "kawaii", "light"),
    "ember": ("fire", "lava", "volcano", "ember", "burn", "aag", "inferno", "red"),
    "arctic": ("snow", "ice", "winter", "arctic", "frost", "glacier", "baraf", "cold"),
    "rose": ("rose", "pink", "flower", "blossom", "romantic", "gulab", "love"),
}

# --- subjects -------------------------------------------------------------
SUBJECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mountain": ("mountain", "peak", "range", "alps", "himalaya", "pahar", "cliff", "summit"),
    "city": ("city", "skyline", "urban", "building", "street", "town", "karachi", "lahore"),
    "portrait": ("portrait", "face", "person", "man", "woman", "girl", "boy", "chehra", "human"),
    "ocean": ("ocean", "sea", "wave", "beach", "coast", "shore", "samundar"),
    "forest": ("forest", "tree", "woods", "jungle", "grove", "ban"),
    "space": ("space", "galaxy", "nebula", "star", "planet", "cosmos", "moon", "astronaut"),
    "abstract": ("abstract", "pattern", "geometric", "shape", "texture", "fractal"),
    "animal": ("cat", "dog", "bird", "horse", "tiger", "lion", "fish", "animal", "janwar"),
    "architecture": ("architecture", "mosque", "temple", "bridge", "tower", "dome", "masjid"),
    "road": ("road", "highway", "street", "path", "route", "drive", "sarak", "motorway"),
}

# --- styles ---------------------------------------------------------------
STYLES: dict[str, tuple[str, ...]] = {
    "cinematic": ("cinematic", "film", "movie", "dramatic", "epic", "anamorphic"),
    "neon": ("neon", "cyberpunk", "synthwave", "glow", "vaporwave"),
    "watercolor": ("watercolor", "painting", "brush", "aquarelle", "ink"),
    "minimal": ("minimal", "clean", "simple", "flat", "negative space"),
    "retro": ("retro", "vintage", "80s", "90s", "film grain", "analog", "polaroid"),
    "dreamy": ("dreamy", "ethereal", "soft focus", "hazy", "fantasy", "magical"),
}

MOODS: dict[str, tuple[str, ...]] = {
    "calm": ("calm", "peaceful", "serene", "quiet", "still", "sukoon"),
    "energetic": ("energetic", "dynamic", "fast", "powerful", "bold", "strong"),
    "melancholy": ("melancholy", "sad", "lonely", "moody", "dark", "gloomy"),
    "joyful": ("joyful", "happy", "bright", "cheerful", "playful", "khushi"),
    "mysterious": ("mysterious", "eerie", "unknown", "hidden", "secret", "shadow"),
}

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:5": (4, 5),
}


@dataclass
class SceneSpec:
    """Everything the renderer needs, plus the reasoning behind it."""

    prompt: str
    negative_prompt: str = ""
    palette_name: str = "sunset"
    palette: list[tuple[int, int, int]] = field(default_factory=list)
    subject: str = "abstract"
    style: str = "cinematic"
    mood: str = "calm"
    seed: int = 0
    width: int = 1024
    height: int = 1024
    matched_keywords: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "palette": self.palette_name,
            "subject": self.subject,
            "style": self.style,
            "mood": self.mood,
            "seed": self.seed,
            "size": f"{self.width}x{self.height}",
            "matched_keywords": self.matched_keywords,
        }


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _first_match(text: str, table: dict[str, tuple[str, ...]]) -> tuple[str | None, str | None]:
    """Return (key, keyword) for the earliest keyword hit in the text."""
    best: tuple[int, str, str] | None = None
    for key, keywords in table.items():
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0 and (best is None or idx < best[0]):
                best = (idx, key, kw)
    if best is None:
        return None, None
    return best[1], best[2]


def _hash_palette(prompt: str) -> str:
    """Deterministic fallback so an unmatched prompt still gets a stable look."""
    names = sorted(PALETTES)
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return names[digest[0] % len(names)]


def derive_seed(prompt: str, explicit: int | None = None) -> int:
    if explicit is not None:
        return explicit
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 2_147_483_647


def resolve_size(aspect_ratio: str, long_side: int) -> tuple[int, int]:
    """Fit the requested ratio inside a square of `long_side`, rounded to /8."""
    ratio = ASPECT_RATIOS.get(aspect_ratio, (1, 1))
    rw, rh = ratio
    if rw >= rh:
        width = long_side
        height = round(long_side * rh / rw)
    else:
        height = long_side
        width = round(long_side * rw / rh)
    # Round to a multiple of 8 — keeps the renderer's grid maths clean.
    width = max(8, (width // 8) * 8)
    height = max(8, (height // 8) * 8)
    return width, height


def parse_prompt(
    prompt: str,
    *,
    negative_prompt: str = "",
    style: str | None = None,
    aspect_ratio: str = "1:1",
    long_side: int = 1024,
    seed: int | None = None,
) -> SceneSpec:
    text = _normalise(prompt)
    matched: list[str] = []

    palette_name, kw = _first_match(text, PALETTE_KEYWORDS)
    if palette_name is None:
        palette_name = _hash_palette(text)
    else:
        matched.append(kw or "")

    subject, kw = _first_match(text, SUBJECT_KEYWORDS)
    if subject is None:
        subject = "abstract"
    else:
        matched.append(kw or "")

    if style and style in STYLES:
        style_name = style
    else:
        style_name, kw = _first_match(text, STYLES)
        if style_name is None:
            style_name = "cinematic"
        else:
            matched.append(kw or "")

    mood, kw = _first_match(text, MOODS)
    if mood is None:
        mood = "calm"
    else:
        matched.append(kw or "")

    width, height = resolve_size(aspect_ratio, long_side)

    return SceneSpec(
        prompt=prompt,
        negative_prompt=negative_prompt,
        palette_name=palette_name,
        palette=list(PALETTES[palette_name]),
        subject=subject,
        style=style_name,
        mood=mood,
        seed=derive_seed(text, seed),
        width=width,
        height=height,
        matched_keywords=[m for m in matched if m],
    )
