"""ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    generations: Mapped[list[Generation]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(String(40), default="cinematic")
    aspect_ratio: Mapped[str] = mapped_column(String(12), default="1:1")
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=1024)
    seed: Mapped[int] = mapped_column(Integer, default=0)

    provider: Mapped[str] = mapped_column(String(24), default="local")
    model: Mapped[str] = mapped_column(String(80), default="rang-procedural-v1")
    render_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Images live in the row so the app works on ephemeral filesystems
    # (Vercel /tmp, containers without a volume) with zero extra setup.
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    thumb_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_mime: Mapped[str] = mapped_column(String(32), default="image/png")

    is_favourite: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    owner: Mapped[User] = relationship(back_populates="generations")
