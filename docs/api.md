# API Reference

Base URL: `http://127.0.0.1:8000`

All request and response bodies are JSON. Authenticated endpoints expect
`Authorization: Bearer <token>`.

Interactive docs: `/docs` (Swagger) and `/redoc`.

---

## Meta

### `GET /api/health`

No auth. Returns service and database status.

```json
{ "status": "ok", "version": "1.0.0", "database": "ok", "provider": "local" }
```

`status` is `"degraded"` when the database check fails. Always **200** — a
health endpoint that 500s is useless to a load balancer.

---

## Auth

### `POST /api/auth/register`

| Field | Type | Rules |
|---|---|---|
| `email` | string | valid email, unique |
| `display_name` | string | 2–80 chars, not blank after trim |
| `password` | string | 8–128 chars |

**201** → `TokenResponse`. **409** if the email exists. **422** on validation.

```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 86400 }
```

### `POST /api/auth/login`

`{email, password}` → **200** `TokenResponse`.

**401** for both an unknown email and a wrong password, with the same message.
This is deliberate: a different response for each would let an attacker
enumerate which emails have accounts.

### `GET /api/auth/me` 🔒

**200** → `{id, email, display_name, created_at}`. **401** without a valid token.

---

## Generation

### `POST /api/preview`

No auth. Parses a prompt without rendering — this is what powers the live chips
in the composer.

Request body is the same shape as `/api/generate` (only `prompt` is required).

**200** →

```json
{
  "palette": "neon",
  "subject": "city",
  "style": "neon",
  "mood": "calm",
  "seed": 1283746502,
  "size": "1024x1024",
  "matched_keywords": ["neon", "city"]
}
```

### `GET /api/providers`

No auth. Lists providers and whether each is usable right now.

```json
[
  { "name": "local",  "available": true,  "model": "rang-procedural-v1",
    "note": "Runs in-process with Pillow. No key, no network, deterministic." },
  { "name": "gemini", "available": false, "model": "gemini-2.5-flash-image",
    "note": "Google image model. Requires GEMINI_API_KEY." }
]
```

### `POST /api/generate` 🔒

| Field | Type | Default | Rules |
|---|---|---|---|
| `prompt` | string | — | 3–800 chars after trim |
| `negative_prompt` | string | `""` | ≤ 400 chars |
| `style` | enum | `null` | `cinematic` `neon` `watercolor` `minimal` `retro` `dreamy`; `null` = read from prompt |
| `aspect_ratio` | enum | `1:1` | `1:1` `3:2` `2:3` `16:9` `9:16` `4:5` |
| `seed` | int | `null` | 0 – 2147483647; `null` = derive from prompt |
| `provider` | enum | `null` | `local` `gemini`; `null` = server default |

**201** → `GenerationOut`:

```json
{
  "id": 1,
  "prompt": "a neon city at night",
  "negative_prompt": "",
  "style": "neon",
  "aspect_ratio": "16:9",
  "width": 1024,
  "height": 576,
  "seed": 1283746502,
  "provider": "local",
  "model": "rang-procedural-v1",
  "render_ms": 214,
  "is_favourite": false,
  "created_at": "2026-11-12T00:14:03.221Z",
  "image_url": "/api/images/1",
  "thumb_url": "/api/images/1/thumb"
}
```

**401** unauthenticated · **422** validation · **429** rate limited ·
**503** provider unavailable.

### `GET /api/generations` 🔒

| Query | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 24 | 1–100 |
| `offset` | int | 0 | ≥ 0 |
| `favourite_only` | bool | false | |
| `q` | string | — | case-insensitive substring of the prompt, ≤ 200 chars |

**200** → `{items: [GenerationOut], total, limit, offset}`. Newest first.

### `GET /api/generations/{id}` 🔒

**200** → `GenerationOut`. **404** if it doesn't exist **or belongs to another
user** — we return 404 rather than 403 so the response never confirms that
someone else's row exists.

### `PATCH /api/generations/{id}/favourite` 🔒

`{"is_favourite": true}` → **200** `GenerationOut`. **404** as above.

### `DELETE /api/generations/{id}` 🔒

**204** on success. **404** as above.

---

## Images

### `GET /api/images/{id}`

No auth. Returns the full image with its stored MIME type and
`Cache-Control: public, max-age=31536000, immutable`.

**404** if the id doesn't exist.

> **Why no auth?** An `<img src>` can't send an `Authorization` header. For a
> portfolio app with sequential integer ids this is an acceptable trade. If you
> need private images, replace this with a signed, expiring URL — the API
> response already abstracts the location behind `image_url`, so clients don't
> change.

### `GET /api/images/{id}/thumb`

No auth. 480px PNG thumbnail, same caching headers.

---

## Errors

Every error is JSON:

```json
{ "detail": "Incorrect email or password" }
```

Validation errors (422) use FastAPI's list form:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "prompt"],
      "msg": "String should have at least 3 characters",
      "input": "a",
      "ctx": { "min_length": 3 }
    }
  ]
}
```

Unknown `/api/*` paths return a JSON 404, never an HTML page — so a client
parsing JSON never chokes on a stray `<html>`.

| Status | When |
|---|---|
| 401 | Missing / invalid / expired token |
| 404 | Not found, or not yours |
| 409 | Email already registered |
| 422 | Validation failed |
| 429 | Rate limited (`Retry-After` header set) |
| 503 | Provider unavailable |

---

## Rate limits

| Scope | Default |
|---|---|
| `POST /api/generate` | 20 / minute / IP |
| all other routes | 120 / minute / IP |

Configurable via `RATE_LIMIT_GENERATE` and `RATE_LIMIT_DEFAULT`. The store is
in-process; point it at Redis before running more than one instance.
