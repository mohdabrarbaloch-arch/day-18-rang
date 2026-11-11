"""Procedural image renderer.

No model weights, no network, no API key. Given a SceneSpec it composes a
layered image: gradient sky, subject silhouettes, atmosphere, then a film
grade. Deterministic for a given seed, so the same prompt always gives the
same picture — which is what makes the gallery reproducible.
"""

from __future__ import annotations

import io
import math
import random
import time

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.prompting import SceneSpec
from app.providers.base import ProviderResult

Color = tuple[int, int, int]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _mix(c1: Color, c2: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def _shade(c: Color, factor: float) -> Color:
    return (
        max(0, min(255, int(c[0] * factor))),
        max(0, min(255, int(c[1] * factor))),
        max(0, min(255, int(c[2] * factor))),
    )


def _grain(size: tuple[int, int], rng: random.Random, sigma: float) -> Image.Image:
    """Deterministic film grain.

    PIL's Image.effect_noise() seeds itself from the OS, which would make the
    same prompt render differently every time. We build the noise from our own
    seeded RNG instead so renders stay reproducible.
    """
    w, h = size
    # Draw at 1/4 scale then upscale — much faster and looks the same at this
    # opacity, since grain is high-frequency anyway.
    sw, sh = max(2, w // 4), max(2, h // 4)
    small = Image.new("L", (sw, sh))
    small.putdata([max(0, min(255, int(rng.gauss(128, sigma)))) for _ in range(sw * sh)])
    return small.resize((w, h), Image.BILINEAR)


def _gradient_column(stops: list[Color], height: int) -> Image.Image:
    """Build a 1px-wide vertical gradient then stretch it — fast and smooth."""
    strip = Image.new("RGB", (1, height))
    px = strip.load()
    segments = len(stops) - 1
    for y in range(height):
        pos = (y / max(1, height - 1)) * segments
        idx = min(int(pos), segments - 1)
        t = pos - idx
        px[0, y] = _mix(stops[idx], stops[idx + 1], t)
    return strip


def _radial_glow(
    size: tuple[int, int],
    center: tuple[float, float],
    radius: float,
    color: Color,
    strength: float = 1.0,
) -> Image.Image:
    """A soft additive light blob, drawn small then upscaled for speed."""
    w, h = size
    scale = 4
    sw, sh = max(2, w // scale), max(2, h // scale)
    layer = Image.new("L", (sw, sh), 0)
    draw = ImageDraw.Draw(layer)
    cx, cy = center[0] / scale, center[1] / scale
    r = max(1.0, radius / scale)
    steps = 18
    for i in range(steps, 0, -1):
        t = i / steps
        rr = r * t
        val = int(255 * strength * (1 - t) ** 2.2)
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=val)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=max(1, r / 6)))
    layer = layer.resize((w, h), Image.BICUBIC)
    tint = Image.new("RGB", (w, h), color)
    return Image.composite(tint, Image.new("RGB", (w, h), (0, 0, 0)), layer)


def _screen(base: Image.Image, layer: Image.Image, opacity: float = 0.6) -> Image.Image:
    """Screen blend — lightens, good for glows and haze."""
    from PIL import ImageChops

    screened = ImageChops.screen(base, layer)
    return Image.blend(base, screened, opacity)


# --------------------------------------------------------------------------
# subject layers
# --------------------------------------------------------------------------
def _draw_mountains(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    horizon = int(h * 0.62)
    layers = 4
    for layer in range(layers):
        depth = layer / max(1, layers - 1)
        base_y = horizon + int(depth * h * 0.10)
        amp = h * (0.20 - depth * 0.11)
        color = _shade(spec.palette[0], 0.55 + depth * 0.55)
        alpha = int(150 + depth * 90)
        points = [(0, h)]
        x = 0
        step = max(6, w // 90)
        phase = rng.uniform(0, math.tau)
        freq = rng.uniform(1.4, 2.6)
        while x <= w:
            y = base_y - amp * (0.55 + 0.45 * math.sin(x / w * math.tau * freq + phase))
            y -= amp * 0.25 * math.sin(x / w * math.tau * freq * 2.7 + phase * 1.7)
            points.append((x, y))
            x += step
        points.append((w, h))
        draw.polygon(points, fill=(*color, alpha))
    # snow caps on the nearest ridge
    for _ in range(6):
        cx = rng.randint(int(w * 0.1), int(w * 0.9))
        cy = horizon - int(h * 0.10) + rng.randint(-8, 8)
        rw = rng.randint(w // 40, w // 18)
        draw.polygon(
            [(cx - rw, cy + rw // 2), (cx, cy - rw // 2), (cx + rw, cy + rw // 2)],
            fill=(*_shade(spec.palette[-1], 1.0), 120),
        )


def _draw_city(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    horizon = int(h * 0.70)
    x = -20
    while x < w + 20:
        bw = rng.randint(w // 26, w // 11)
        bh = rng.randint(int(h * 0.10), int(h * 0.34))
        top = horizon - bh
        body = _shade(spec.palette[0], rng.uniform(0.30, 0.55))
        draw.rectangle([x, top, x + bw, h], fill=(*body, 235))
        # lit windows
        cols = max(1, bw // 12)
        rows = max(1, bh // 14)
        for c in range(cols):
            for r in range(rows):
                if rng.random() < 0.34:
                    wx = x + 4 + c * 12
                    wy = top + 6 + r * 14
                    if wx + 4 < x + bw and wy + 6 < h:
                        warm = rng.choice([spec.palette[-1], spec.palette[-2], (255, 226, 160)])
                        draw.rectangle(
                            [wx, wy, wx + 4, wy + 6], fill=(*warm, rng.randint(120, 230))
                        )
        x += bw + rng.randint(2, 10)
    # a couple of antenna lights
    for _ in range(4):
        ax = rng.randint(0, w)
        draw.line(
            [(ax, horizon - rng.randint(20, 60)), (ax, horizon)],
            fill=(*spec.palette[0], 200),
            width=2,
        )


def _draw_ocean(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    horizon = int(h * 0.58)
    # water body
    water = _shade(spec.palette[1], 0.55)
    draw.rectangle([0, horizon, w, h], fill=(*water, 255))
    # sun reflection column
    sun_x = w * rng.uniform(0.35, 0.65)
    for i in range(60):
        t = i / 60
        y = horizon + int(t * (h - horizon))
        spread = 6 + t * w * 0.10
        alpha = int(120 * (1 - t) ** 1.4)
        draw.line(
            [(sun_x - spread, y), (sun_x + spread, y)],
            fill=(*spec.palette[-1], alpha),
            width=max(1, int(2 + t * 4)),
        )
    # wave bands
    for _ in range(26):
        y = rng.randint(horizon + 4, h - 2)
        t = (y - horizon) / max(1, h - horizon)
        length = rng.randint(w // 20, w // 5)
        x0 = rng.randint(-length, w)
        draw.line(
            [(x0, y), (x0 + length, y)],
            fill=(*_shade(spec.palette[-1], 0.9), int(40 + t * 60)),
            width=max(1, int(1 + t * 3)),
        )


def _draw_forest(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    ground = int(h * 0.78)
    draw.rectangle([0, ground, w, h], fill=(*_shade(spec.palette[0], 0.5), 255))
    for layer in range(3):
        depth = layer / 2
        color = _shade(spec.palette[0], 0.35 + depth * 0.5)
        count = 14 - layer * 3
        for _ in range(count):
            cx = rng.randint(-20, w + 20)
            th = rng.randint(int(h * 0.18), int(h * 0.42)) * (0.7 + depth * 0.5)
            tw = th * rng.uniform(0.16, 0.26)
            base = ground + int(depth * h * 0.06)
            draw.rectangle(
                [cx - tw * 0.12, base - th * 0.35, cx + tw * 0.12, base],
                fill=(*_shade(color, 0.7), 240),
            )
            for tier in range(3):
                ty = base - th * (0.30 + tier * 0.22)
                spread = tw * (1.0 - tier * 0.22)
                draw.polygon(
                    [(cx - spread, ty), (cx, ty - th * 0.30), (cx + spread, ty)],
                    fill=(*color, 235),
                )


def _draw_space(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(int(w * h / 2600)):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        r = rng.choice([0, 0, 0, 1, 1, 2])
        b = rng.randint(140, 255)
        draw.ellipse(
            [x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 10), rng.randint(120, 255))
        )
    # nebula blobs
    for _ in range(3):
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        rad = rng.randint(int(w * 0.15), int(w * 0.4))
        col = rng.choice([spec.palette[1], spec.palette[2], spec.palette[-1]])
        glow = _radial_glow((w, h), (cx, cy), rad, col, 0.5)
        img.paste(_screen(img, glow, 0.45), (0, 0))
    # planet
    pr = rng.randint(int(w * 0.10), int(w * 0.22))
    px, py = rng.randint(pr, w - pr), rng.randint(pr, h - pr)
    draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*_shade(spec.palette[2], 0.8), 255))
    draw.ellipse(
        [px - pr, py - pr, px + pr, py + pr],
        outline=(*_shade(spec.palette[-1], 1.0), 90),
        width=max(2, pr // 14),
    )


def _draw_portrait(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w * rng.uniform(0.42, 0.58)
    head_r = w * 0.16
    head_y = h * 0.40
    body = _shade(spec.palette[0], 0.42)
    # shoulders
    draw.ellipse(
        [cx - head_r * 2.6, head_y + head_r * 0.9, cx + head_r * 2.6, h + head_r * 2],
        fill=(*body, 250),
    )
    # head
    draw.ellipse([cx - head_r, head_y - head_r, cx + head_r, head_y + head_r], fill=(*body, 250))
    # rim light
    draw.arc(
        [cx - head_r, head_y - head_r, cx + head_r, head_y + head_r],
        start=200,
        end=340,
        fill=(*spec.palette[-1], 170),
        width=max(2, int(head_r * 0.10)),
    )


def _draw_architecture(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    base = int(h * 0.80)
    col = _shade(spec.palette[0], 0.40)
    # main dome
    dw = w * 0.30
    draw.ellipse(
        [w / 2 - dw / 2, base - dw * 0.95, w / 2 + dw / 2, base + dw * 0.05], fill=(*col, 250)
    )
    draw.rectangle([w / 2 - dw / 2, base - dw * 0.10, w / 2 + dw / 2, base], fill=(*col, 250))
    # minarets
    for side in (-1, 1):
        mx = w / 2 + side * dw * 0.95
        mw = w * 0.035
        mh = h * 0.30
        draw.rectangle([mx - mw, base - mh, mx + mw, base], fill=(*col, 250))
        draw.ellipse(
            [mx - mw * 1.5, base - mh - mw * 1.5, mx + mw * 1.5, base - mh + mw * 1.5],
            fill=(*col, 250),
        )
    # ground
    draw.rectangle([0, base, w, h], fill=(*_shade(spec.palette[0], 0.30), 255))


def _draw_road(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    """A road running to the horizon — the classic one-point-perspective shot."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    horizon = int(h * 0.60)
    vx = w * rng.uniform(0.42, 0.58)

    # ground plane
    draw.rectangle([0, horizon, w, h], fill=(*_shade(spec.palette[1], 0.55), 255))

    # the road: a trapezoid from the bottom edge to the vanishing point
    half_bottom = w * 0.42
    half_top = w * 0.012
    road = _shade(spec.palette[0], 0.30)
    draw.polygon(
        [
            (vx - half_bottom, h),
            (vx - half_top, horizon),
            (vx + half_top, horizon),
            (vx + half_bottom, h),
        ],
        fill=(*road, 255),
    )

    # dashed centre line, shrinking toward the horizon
    y = h
    dash = h * 0.055
    while y > horizon + 4:
        t = (y - horizon) / max(1, h - horizon)
        half = half_top + (half_bottom - half_top) * t
        lw = max(1, int(2 + t * 9))
        draw.line(
            [(vx, y), (vx, y - dash * t)],
            fill=(*_shade(spec.palette[-1], 1.0), int(120 + t * 120)),
            width=lw,
        )
        y -= dash * t * 2.1

    # roadside posts
    for side in (-1, 1):
        for i in range(7):
            t = (i + 1) / 8
            py = horizon + (h - horizon) * (t**1.7)
            half = half_top + (half_bottom - half_top) * ((py - horizon) / max(1, h - horizon))
            px = vx + side * half * 1.12
            ph = max(2, int(6 + t * 26))
            draw.rectangle(
                [px - 1, py - ph, px + 1, py], fill=(*_shade(spec.palette[0], 0.5), 200)
            )


def _draw_abstract(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(rng.randint(5, 9)):
        col = rng.choice(spec.palette)
        alpha = rng.randint(40, 120)
        kind = rng.choice(["ellipse", "band", "arc"])
        if kind == "ellipse":
            rw = rng.randint(int(w * 0.15), int(w * 0.6))
            rh = rng.randint(int(h * 0.15), int(h * 0.6))
            cx, cy = rng.randint(0, w), rng.randint(0, h)
            draw.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=(*col, alpha))
        elif kind == "band":
            y = rng.randint(0, h)
            th = rng.randint(int(h * 0.03), int(h * 0.16))
            draw.rectangle([0, y, w, y + th], fill=(*col, alpha))
        else:
            rw = rng.randint(int(w * 0.2), int(w * 0.7))
            cx, cy = rng.randint(0, w), rng.randint(0, h)
            draw.arc(
                [cx - rw, cy - rw, cx + rw, cy + rw],
                rng.randint(0, 180),
                rng.randint(180, 360),
                fill=(*col, min(255, alpha + 60)),
                width=rng.randint(2, 14),
            )


def _draw_animal(img: Image.Image, rng: random.Random, spec: SceneSpec) -> None:
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    col = _shade(spec.palette[0], 0.35)
    cx, cy = w * 0.5, h * 0.62
    bw, bh = w * 0.26, h * 0.16
    draw.ellipse([cx - bw, cy - bh, cx + bw, cy + bh], fill=(*col, 250))
    hr = bw * 0.42
    draw.ellipse(
        [cx + bw * 0.55, cy - bh * 1.5, cx + bw * 0.55 + hr * 2, cy - bh * 1.5 + hr * 2],
        fill=(*col, 250),
    )
    for side in (-1, 1):
        draw.polygon(
            [
                (cx + bw * 0.55 + hr * (0.4 if side < 0 else 1.4), cy - bh * 1.5),
                (cx + bw * 0.55 + hr * (0.6 if side < 0 else 1.2), cy - bh * 1.5 - hr * 0.9),
                (cx + bw * 0.55 + hr * (0.9 if side < 0 else 0.9), cy - bh * 1.5),
            ],
            fill=(*col, 250),
        )
    for i in range(4):
        lx = cx - bw * 0.7 + i * bw * 0.45
        draw.rectangle([lx, cy + bh * 0.6, lx + bw * 0.10, cy + bh * 1.9], fill=(*col, 250))


SUBJECT_RENDERERS = {
    "mountain": _draw_mountains,
    "city": _draw_city,
    "ocean": _draw_ocean,
    "forest": _draw_forest,
    "space": _draw_space,
    "portrait": _draw_portrait,
    "architecture": _draw_architecture,
    "road": _draw_road,
    "abstract": _draw_abstract,
    "animal": _draw_animal,
}


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------
def _apply_style(img: Image.Image, spec: SceneSpec, rng: random.Random) -> Image.Image:
    style = spec.style
    if style == "cinematic":
        img = ImageEnhance.Contrast(img).enhance(1.18)
        img = ImageEnhance.Color(img).enhance(1.12)
        # teal-orange split tone
        overlay = Image.new("RGB", img.size, (10, 30, 45))
        img = Image.blend(img, Image.blend(img, overlay, 0.18), 0.5)
    elif style == "neon":
        img = ImageEnhance.Color(img).enhance(1.45)
        img = ImageEnhance.Contrast(img).enhance(1.15)
        w, h = img.size
        # real neon: a few bright horizontal light streaks
        streaks = Image.new("RGB", (w, h), (0, 0, 0))
        sd = ImageDraw.Draw(streaks, "RGBA")
        for _ in range(rng.randint(3, 6)):
            sy = rng.randint(int(h * 0.25), int(h * 0.85))
            col = rng.choice([(255, 40, 160), (40, 240, 255), (150, 60, 255), (255, 200, 40)])
            sd.line([(0, sy), (w, sy)], fill=(*col, rng.randint(90, 170)), width=rng.randint(2, 6))
        streaks = streaks.filter(ImageFilter.GaussianBlur(radius=max(2, w // 90)))
        img = _screen(img, streaks, 0.55)
        draw = ImageDraw.Draw(img, "RGBA")
        for y in range(0, h, 4):
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, 26))
    elif style == "watercolor":
        img = img.filter(ImageFilter.GaussianBlur(radius=1.6))
        img = ImageEnhance.Color(img).enhance(0.88)
        img = ImageEnhance.Brightness(img).enhance(1.06)
        # paper grain
        noise = _grain(img.size, rng, 22)
        paper = Image.merge("RGB", (noise, noise, noise))
        img = Image.blend(img, paper, 0.07)
    elif style == "minimal":
        img = ImageEnhance.Color(img).enhance(0.72)
        img = ImageEnhance.Contrast(img).enhance(0.92)
        img = ImageEnhance.Brightness(img).enhance(1.10)
    elif style == "retro":
        img = ImageEnhance.Color(img).enhance(0.82)
        img = ImageEnhance.Contrast(img).enhance(1.08)
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * 1.08)))
        b = b.point(lambda v: min(255, int(v * 0.94)))
        img = Image.merge("RGB", (r, g, b))
        noise = _grain(img.size, rng, 30)
        img = Image.blend(img, Image.merge("RGB", (noise, noise, noise)), 0.10)
    elif style == "dreamy":
        blurred = img.filter(ImageFilter.GaussianBlur(radius=6))
        img = Image.blend(img, blurred, 0.30)
        img = ImageEnhance.Brightness(img).enhance(1.10)
        img = ImageEnhance.Color(img).enhance(1.05)
    return img


def _apply_mood(img: Image.Image, spec: SceneSpec) -> Image.Image:
    mood = spec.mood
    if mood == "calm":
        img = ImageEnhance.Brightness(img).enhance(1.04)
        img = ImageEnhance.Color(img).enhance(0.94)
    elif mood == "energetic":
        img = ImageEnhance.Contrast(img).enhance(1.16)
        img = ImageEnhance.Color(img).enhance(1.20)
    elif mood == "melancholy":
        img = ImageEnhance.Brightness(img).enhance(0.86)
        img = ImageEnhance.Color(img).enhance(0.72)
    elif mood == "joyful":
        img = ImageEnhance.Brightness(img).enhance(1.12)
        img = ImageEnhance.Color(img).enhance(1.18)
    elif mood == "mysterious":
        img = ImageEnhance.Brightness(img).enhance(0.80)
        img = ImageEnhance.Contrast(img).enhance(1.22)
    return img


def _vignette(img: Image.Image, strength: float = 0.42) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    steps = 24
    for i in range(steps):
        t = i / steps
        inset_x = int(w * 0.5 * t)
        inset_y = int(h * 0.5 * t)
        val = int(255 * (1 - t) ** 1.6)
        draw.ellipse([inset_x, inset_y, w - inset_x, h - inset_y], fill=val)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, w // 60)))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, dark, mask.point(lambda v: int(255 - (255 - v) * strength)))


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def render_image(spec: SceneSpec) -> Image.Image:
    rng = random.Random(spec.seed)
    w, h = spec.width, spec.height

    # 1. sky
    img = _gradient_column(spec.palette, h).resize((w, h), Image.BICUBIC).convert("RGB")

    # 2. light source
    sun_x = w * rng.uniform(0.25, 0.75)
    sun_y = h * rng.uniform(0.18, 0.42)
    glow = _radial_glow((w, h), (sun_x, sun_y), w * 0.55, spec.palette[-1], 0.85)
    img = _screen(img, glow, 0.68)
    draw = ImageDraw.Draw(img, "RGBA")
    sun_r = w * rng.uniform(0.035, 0.075)
    draw.ellipse(
        [sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r],
        fill=(*_shade(spec.palette[-1], 1.0), 235),
    )

    # 3. subject
    renderer = SUBJECT_RENDERERS.get(spec.subject, _draw_abstract)
    renderer(img, rng, spec)

    # 4. atmosphere: haze band near the horizon
    haze = Image.new("RGB", (w, h), spec.palette[-1])
    haze_mask = Image.new("L", (w, h), 0)
    hd = ImageDraw.Draw(haze_mask)
    band_y = int(h * 0.55)
    hd.rectangle([0, band_y, w, band_y + int(h * 0.12)], fill=70)
    haze_mask = haze_mask.filter(ImageFilter.GaussianBlur(radius=max(4, h // 40)))
    img = Image.composite(haze, img, haze_mask.point(lambda v: int(v * 0.55)))

    # 5. grade
    img = _apply_style(img, spec, rng)
    img = _apply_mood(img, spec)
    img = _vignette(img, 0.26)

    # 6. fine grain
    noise = _grain((w, h), rng, 12)
    img = Image.blend(img, Image.merge("RGB", (noise, noise, noise)), 0.035)

    return img


def make_thumbnail(img: Image.Image, size: int = 480) -> Image.Image:
    thumb = img.copy()
    thumb.thumbnail((size, size), Image.LANCZOS)
    return thumb


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class LocalProvider:
    name = "local"
    model = "rang-procedural-v1"

    def generate(self, spec: SceneSpec) -> ProviderResult:
        started = time.perf_counter()
        img = render_image(spec)
        payload = _to_png_bytes(img)
        elapsed = int((time.perf_counter() - started) * 1000)
        return ProviderResult(
            image_bytes=payload,
            mime="image/png",
            provider=self.name,
            model=self.model,
            render_ms=elapsed,
        )
