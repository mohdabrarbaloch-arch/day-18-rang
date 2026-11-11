"""Prompt parser tests — the part that decides what gets drawn."""

from __future__ import annotations

from app.prompting import (
    PALETTES,
    derive_seed,
    parse_prompt,
    resolve_size,
)


def test_palette_detected_from_keyword():
    # The earliest keyword in the text wins, so put "sunset" first.
    spec = parse_prompt("a sunset over the calm ocean")
    assert spec.palette_name == "sunset"
    assert spec.palette == PALETTES["sunset"]


def test_earliest_keyword_wins():
    spec = parse_prompt("a calm ocean at sunset")
    assert spec.palette_name == "ocean"


def test_palette_falls_back_deterministically():
    a = parse_prompt("qwerty zxcvbn")
    b = parse_prompt("qwerty zxcvbn")
    assert a.palette_name == b.palette_name
    assert a.palette_name in PALETTES


def test_subject_detected():
    spec = parse_prompt("a mountain range at dawn")
    assert spec.subject == "mountain"


def test_subject_defaults_to_abstract():
    spec = parse_prompt("something completely unrecognisable here")
    assert spec.subject == "abstract"


def test_style_override_wins_over_text():
    spec = parse_prompt("a neon city", style="watercolor")
    assert spec.style == "watercolor"


def test_style_detected_from_text_when_not_overridden():
    spec = parse_prompt("a neon cyberpunk street")
    assert spec.style == "neon"


def test_mood_detected():
    spec = parse_prompt("a lonely melancholy road")
    assert spec.mood == "melancholy"


def test_seed_is_stable_for_same_prompt():
    assert derive_seed("same prompt") == derive_seed("same prompt")


def test_seed_differs_for_different_prompts():
    assert derive_seed("prompt one") != derive_seed("prompt two")


def test_explicit_seed_is_respected():
    assert derive_seed("anything", 42) == 42


def test_resolve_size_square():
    assert resolve_size("1:1", 1024) == (1024, 1024)


def test_resolve_size_wide():
    w, h = resolve_size("16:9", 1024)
    assert w == 1024
    assert h == 576
    assert w % 8 == 0 and h % 8 == 0


def test_resolve_size_vertical():
    w, h = resolve_size("9:16", 1024)
    assert h == 1024
    assert w == 576


def test_unknown_ratio_defaults_to_square():
    assert resolve_size("7:3", 512) == (512, 512)


def test_matched_keywords_are_reported():
    spec = parse_prompt("a neon city at sunset")
    assert len(spec.matched_keywords) >= 2


def test_as_dict_shape():
    spec = parse_prompt("a forest")
    d = spec.as_dict()
    assert set(d) == {"palette", "subject", "style", "mood", "seed", "size", "matched_keywords"}
    assert d["size"] == "1024x1024"
