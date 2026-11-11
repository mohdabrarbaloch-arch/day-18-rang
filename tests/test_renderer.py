"""Renderer tests — real pixels, real invariants."""

from __future__ import annotations

import io

from PIL import Image

from app.prompting import parse_prompt
from app.providers.local import LocalProvider, make_thumbnail, render_image


def _open(payload: bytes) -> Image.Image:
    return Image.open(io.BytesIO(payload))


def test_render_returns_png_of_requested_size():
    spec = parse_prompt("a mountain at sunset", aspect_ratio="16:9", long_side=512)
    result = LocalProvider().generate(spec)
    img = _open(result.image_bytes)
    assert img.format == "PNG"
    assert img.size == (spec.width, spec.height)


def test_render_is_deterministic_for_same_seed():
    spec = parse_prompt("a neon city", seed=1234, long_side=256)
    a = LocalProvider().generate(spec).image_bytes
    b = LocalProvider().generate(spec).image_bytes
    assert a == b


def test_different_seeds_produce_different_images():
    a = LocalProvider().generate(parse_prompt("a forest", seed=1, long_side=256)).image_bytes
    b = LocalProvider().generate(parse_prompt("a forest", seed=2, long_side=256)).image_bytes
    assert a != b


def test_render_is_not_a_flat_colour():
    """A real render must have variation — catches a silently broken renderer."""
    spec = parse_prompt("a city at night", long_side=256)
    img = _open(LocalProvider().generate(spec).image_bytes).convert("RGB")
    colors = img.getcolors(maxcolors=1_000_000)
    assert colors is not None
    assert len(colors) > 500


def test_every_subject_renders():
    for subject in (
        "mountain",
        "city",
        "ocean",
        "forest",
        "space",
        "portrait",
        "architecture",
        "abstract",
        "animal",
    ):
        spec = parse_prompt(f"a {subject}", long_side=192)
        spec.subject = subject
        img = render_image(spec)
        assert img.size == (spec.width, spec.height)


def test_every_style_renders():
    for style in ("cinematic", "neon", "watercolor", "minimal", "retro", "dreamy"):
        spec = parse_prompt("a mountain", style=style, long_side=192)
        img = render_image(spec)
        assert img.size == (spec.width, spec.height)


def test_thumbnail_fits_within_box():
    spec = parse_prompt("a wide ocean", aspect_ratio="16:9", long_side=1024)
    img = render_image(spec)
    thumb = make_thumbnail(img, 480)
    assert max(thumb.size) <= 480
    assert thumb.size[0] / thumb.size[1] == img.size[0] / img.size[1]


def test_render_reports_timing():
    result = LocalProvider().generate(parse_prompt("a forest", long_side=192))
    assert result.render_ms >= 0
    assert result.provider == "local"
    assert result.mime == "image/png"
