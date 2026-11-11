# Architecture

## What Rang is

Rang is an image generation studio. You write a prompt, it gives you a picture,
and it keeps everything you made in a gallery you can search and favourite.

The interesting part is not that it makes images. It's *how* it makes them, and
what it refuses to hide.

## The core idea: no black box

Most image tools are a text box and a picture. You have no idea why you got what
you got, and you can't get it again.

Rang splits generation into two visible halves:

1. **A parser** that reads your prompt and produces a `SceneSpec` — palette,
   subject, style, mood, seed, size. Every decision it makes is returned to the
   UI, so you can see *"it picked the sunset palette because you wrote 'golden
   hour'"*.
2. **A renderer** that turns that spec into pixels, deterministically.

Same prompt + same seed = byte-identical image. That's what makes the gallery
reproducible instead of a slot machine.

## System diagram

```
                    ┌──────────────────────────────┐
   browser  ───────► │  static/index.html + app.js  │
                    │  (vanilla JS, no build step) │
                    └──────────────┬───────────────┘
                                    │ fetch, JSON, Bearer token
                                    ▼
                    ┌──────────────────────────────┐
                    │        FastAPI (app/main.py) │
                    │  CORS · security headers     │
                    │  slowapi rate limiting       │
                    └───┬──────────────┬───────────┘
                        │              │
        ┌───────────────▼──┐      ┌────▼─────────────────┐
        │ routers/auth.py  │      │ routers/generation.py│
        │ register/login   │      │ preview/generate/    │
        │ /me              │      │ gallery/images       │
        └───────┬──────────┘      └────┬─────────────────┘
                │                      │
                │              ┌───────▼──────────────┐
                │              │  prompting.py        │
                │              │  prompt → SceneSpec  │
                │              └───────┬──────────────┘
                │                      │
                │              ┌───────▼──────────────┐
                │              │  providers/          │
                │              │  ├─ local.py (Pillow)│
                │              │  └─ gemini.py (HTTP) │
                │              └───────┬──────────────┘
                │                      │ PNG bytes
                └──────────┬───────────┘
                           ▼
                 ┌──────────────────────┐
                 │  SQLAlchemy 2.0      │
                 │  users / generations │
                 │  SQLite → Postgres   │
                 └──────────────────────┘
```

## Data flow: one generation

1. `POST /api/generate` with `{prompt, style, aspect_ratio, seed?}`.
2. `get_current_user` resolves the bearer token to a `User` row.
3. `parse_prompt()` normalises the text, scans it for palette / subject / style /
   mood keywords, and derives a seed from a SHA-256 of the prompt when none was
   given.
4. `resolve_size()` fits the requested ratio into a 1024px square, rounded to a
   multiple of 8.
5. The provider renders. `local` composes the image in six passes: gradient sky →
   light source → subject layer → horizon haze → style grade → mood grade →
   vignette → grain.
6. A 480px thumbnail is generated locally regardless of which provider ran, so
   the gallery grid stays fast even if a remote provider returns a 4K image.
7. Both blobs are written to the `generations` row and the row is returned with
   `image_url` / `thumb_url` pointing at `/api/images/{id}`.

## Why images live in the database

`image_bytes` and `thumb_bytes` are `LargeBinary` columns, not files on disk.

That is a deliberate trade. It costs database size and it will not scale to
millions of images. In exchange the app works with **zero** storage
configuration on ephemeral filesystems — Vercel's `/tmp`, a container with no
volume, a fresh clone. For a portfolio app that has to run anywhere without a
setup step, that trade is correct. The scaling note below says what to change.

## Providers

`providers/__init__.py` resolves a provider by name and raises `ProviderError`
when one is unavailable. The router turns that into a **503**, not a 500 —
the provider is a dependency that is down, not a bug in the request.

- **local** — Pillow, in-process, no key, no network, deterministic. The default.
- **gemini** — Google's image model over HTTP. Opt-in; requires `GEMINI_API_KEY`.
  If you select it without a key you get a clear 503 explaining exactly that.

Adding a third provider means one file implementing `generate(spec) ->
ProviderResult` and one branch in `get_provider()`.

## Security

| Concern | How it's handled |
|---|---|
| Passwords | bcrypt, 12 rounds, via passlib |
| Sessions | JWT HS256, 24h expiry, `sub` = user id |
| Account enumeration | Login returns the same 401 for unknown email and wrong password |
| Ownership | Every generation query is scoped to `user_id`; someone else's row returns **404, not 403** — we don't confirm it exists |
| Input bounds | Pydantic `Field` limits on every string and number; prompt ≤ 800 chars |
| Rate limiting | slowapi, 20/min on generate, 120/min default |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` |
| Secrets | Environment only. No key is ever hardcoded or committed. |
| CORS | Allow-list from `CORS_ORIGINS`, defaults to `*` for local dev |

## Scaling notes

What breaks first, in order:

1. **Images in the database.** At a few thousand images the row size dominates
   backups and every `SELECT` gets heavy. Move blobs to S3/R2, keep a `storage_key`
   column, and serve via signed URLs. The `image_url` field in the API response
   already abstracts this — clients never touch the blob directly.
2. **SQLite write contention.** One writer at a time. Postgres via
   `docker-compose.yml` is already wired; set `DATABASE_URL` and it switches.
3. **Synchronous rendering.** A 1024px render blocks a worker for ~200-400ms.
   Past a few concurrent users, move generation to a background job (Celery/RQ)
   and have the client poll or subscribe over WebSocket. The API shape barely
   changes: `POST /api/generate` returns `202` with a job id.
4. **Rate limiting in memory.** slowapi's default store is per-process. With more
   than one instance, point it at Redis.
5. **No migrations.** `create_all()` is fine for one deploy. Before a second
   environment exists, add Alembic.

## Testing

51 tests, no network, no API keys:

- `test_prompting.py` — parser behaviour, keyword precedence, seed stability,
  size maths.
- `test_renderer.py` — real pixels: correct dimensions, determinism, that
  different seeds differ, that the output is not a flat colour, and that every
  subject and style renders without raising.
- `test_api.py` — auth flows, validation rejections, ownership isolation,
  pagination, search, favourites, deletion, security headers, JSON 404s.

The renderer tests are the ones that matter. `test_render_is_not_a_flat_colour`
exists because a renderer can fail silently — return a valid PNG of one colour
and every other test still passes.
