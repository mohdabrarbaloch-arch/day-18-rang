"""Seed a demo account with a handful of real renders.

Run: python -m app.seed
"""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Generation, User
from app.prompting import parse_prompt
from app.providers.local import LocalProvider, _to_png_bytes, make_thumbnail
from app.security import hash_password

DEMO_EMAIL = "demo@rang.pk"
DEMO_PASSWORD = "rangdemo12345"

PROMPTS = [
    (
        "A cinematic mountain range at golden hour, snow caps catching the last light",
        "cinematic",
        "16:9",
    ),
    ("Neon cyberpunk city skyline at night, rain on the streets, glowing signs", "neon", "16:9"),
    ("Calm ocean waves at sunset, long exposure, soft pastel sky", "cinematic", "3:2"),
    ("A misty forest in the early morning, deep green, quiet and still", "dreamy", "2:3"),
    ("Deep space nebula with a ringed planet, stars everywhere", "cinematic", "1:1"),
    (
        "Minimal abstract geometric shapes, soft pastel palette, lots of negative space",
        "minimal",
        "1:1",
    ),
    ("A grand mosque with domes and minarets at dusk, warm ember light", "cinematic", "4:5"),
    ("Retro 80s desert highway at sunset, film grain, vintage colour", "retro", "16:9"),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                display_name="Demo Studio",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"demo user already exists: {DEMO_EMAIL}")

        existing = db.scalar(select(Generation).where(Generation.user_id == user.id))
        if existing is not None:
            print("demo user already has generations, skipping seed")
            return

        provider = LocalProvider()
        for prompt, style, ratio in PROMPTS:
            spec = parse_prompt(prompt, style=style, aspect_ratio=ratio, long_side=1024)
            result = provider.generate(spec)
            import io

            from PIL import Image

            full = Image.open(io.BytesIO(result.image_bytes))
            thumb = _to_png_bytes(make_thumbnail(full, 480))
            db.add(
                Generation(
                    user_id=user.id,
                    prompt=spec.prompt,
                    negative_prompt="",
                    style=spec.style,
                    aspect_ratio=ratio,
                    width=spec.width,
                    height=spec.height,
                    seed=spec.seed,
                    provider=result.provider,
                    model=result.model,
                    render_ms=result.render_ms,
                    image_bytes=result.image_bytes,
                    thumb_bytes=thumb,
                    image_mime=result.mime,
                )
            )
            print(f"  rendered: {prompt[:52]}...")
        db.commit()
        print(f"seeded {len(PROMPTS)} generations")
    finally:
        db.close()


if __name__ == "__main__":
    main()
