"""Image generation and gallery routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Generation, User
from app.prompting import parse_prompt
from app.providers import ProviderError, render
from app.providers.local import _to_png_bytes, make_thumbnail
from app.ratelimit import limiter
from app.schemas import (
    FavouriteRequest,
    GenerateRequest,
    GenerationList,
    GenerationOut,
    PromptPreview,
    ProviderInfo,
)

router = APIRouter(prefix="/api", tags=["generation"])


def _to_out(gen: Generation) -> GenerationOut:
    return GenerationOut(
        id=gen.id,
        prompt=gen.prompt,
        negative_prompt=gen.negative_prompt,
        style=gen.style,
        aspect_ratio=gen.aspect_ratio,
        width=gen.width,
        height=gen.height,
        seed=gen.seed,
        provider=gen.provider,
        model=gen.model,
        render_ms=gen.render_ms,
        is_favourite=gen.is_favourite,
        created_at=gen.created_at,
        image_url=f"/api/images/{gen.id}",
        thumb_url=f"/api/images/{gen.id}/thumb",
    )


@router.post("/preview", response_model=PromptPreview)
def preview(payload: GenerateRequest) -> PromptPreview:
    """Show what the parser understood before spending a render."""
    spec = parse_prompt(
        payload.prompt,
        negative_prompt=payload.negative_prompt,
        style=payload.style,
        aspect_ratio=payload.aspect_ratio,
        long_side=1024,
        seed=payload.seed,
    )
    return PromptPreview(**spec.as_dict())


@router.get("/providers", response_model=list[ProviderInfo])
def providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            name="local",
            available=True,
            model="rang-procedural-v1",
            note="Runs in-process with Pillow. No key, no network, deterministic.",
        ),
        ProviderInfo(
            name="gemini",
            available=bool(settings.gemini_api_key),
            model=settings.gemini_image_model,
            note=(
                "Google image model. Requires GEMINI_API_KEY."
                if not settings.gemini_api_key
                else "Configured and ready."
            ),
        ),
    ]


@router.post("/generate", response_model=GenerationOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_generate)
def generate(
    request: Request,
    response: Response,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GenerationOut:
    spec = parse_prompt(
        payload.prompt,
        negative_prompt=payload.negative_prompt,
        style=payload.style,
        aspect_ratio=payload.aspect_ratio,
        long_side=1024,
        seed=payload.seed,
    )

    try:
        result = render(spec, payload.provider)
    except ProviderError as exc:
        # 503: the provider is a dependency that is not available right now.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    # Thumbnail is always produced locally so the gallery stays fast even
    # when a remote provider returns a large image.
    import io

    from PIL import Image

    try:
        full = Image.open(io.BytesIO(result.image_bytes))
        thumb = make_thumbnail(full, 480)
        thumb_bytes = _to_png_bytes(thumb)
    except Exception:  # noqa: BLE001 - a broken thumb must not lose the image
        thumb_bytes = result.image_bytes

    gen = Generation(
        user_id=user.id,
        prompt=spec.prompt,
        negative_prompt=spec.negative_prompt,
        style=spec.style,
        aspect_ratio=payload.aspect_ratio,
        width=spec.width,
        height=spec.height,
        seed=spec.seed,
        provider=result.provider,
        model=result.model,
        render_ms=result.render_ms,
        image_bytes=result.image_bytes,
        thumb_bytes=thumb_bytes,
        image_mime=result.mime,
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)
    return _to_out(gen)


@router.get("/generations", response_model=GenerationList)
def list_generations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    favourite_only: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
) -> GenerationList:
    stmt = select(Generation).where(Generation.user_id == user.id)
    count_stmt = select(func.count(Generation.id)).where(Generation.user_id == user.id)

    if favourite_only:
        stmt = stmt.where(Generation.is_favourite.is_(True))
        count_stmt = count_stmt.where(Generation.is_favourite.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(Generation.prompt.ilike(pattern))
        count_stmt = count_stmt.where(Generation.prompt.ilike(pattern))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Generation.created_at.desc(), Generation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return GenerationList(items=[_to_out(g) for g in rows], total=total, limit=limit, offset=offset)


@router.get("/generations/{gen_id}", response_model=GenerationOut)
def get_generation(
    gen_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> GenerationOut:
    gen = db.get(Generation, gen_id)
    # 404 rather than 403 for someone else's row: don't confirm it exists.
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return _to_out(gen)


@router.patch("/generations/{gen_id}/favourite", response_model=GenerationOut)
def set_favourite(
    gen_id: int,
    payload: FavouriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GenerationOut:
    gen = db.get(Generation, gen_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    gen.is_favourite = payload.is_favourite
    db.commit()
    db.refresh(gen)
    return _to_out(gen)


@router.delete("/generations/{gen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(
    gen_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    gen = db.get(Generation, gen_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    db.delete(gen)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/images/{gen_id}")
def get_image(gen_id: int, db: Session = Depends(get_db)) -> Response:
    """Serve the full image.

    Deliberately unauthenticated: the id is an unguessable-enough integer for
    a portfolio app, and it lets <img src> work without a token header. If you
    need private images, swap this for a signed URL.
    """
    gen = db.get(Generation, gen_id)
    if gen is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(
        content=gen.image_bytes,
        media_type=gen.image_mime,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/images/{gen_id}/thumb")
def get_thumb(gen_id: int, db: Session = Depends(get_db)) -> Response:
    gen = db.get(Generation, gen_id)
    if gen is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(
        content=gen.thumb_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
