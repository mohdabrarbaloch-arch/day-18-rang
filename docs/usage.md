# Usage

## The composer

Everything starts on the left. Write a prompt, pick a style and a ratio, hit
Generate.

### Prompt

Plain English. The parser looks for keywords in four categories and picks the
**earliest match in your text** for each:

| Category | Examples |
|---|---|
| Palette | sunset, ocean, forest, desert, neon, mono, pastel, ember, arctic, rose |
| Subject | mountain, city, ocean, forest, space, portrait, architecture, road, abstract, animal |
| Style | cinematic, neon, watercolour, minimal, retro, dreamy |
| Mood | calm, energetic, melancholy, joyful, mysterious |

So `"a calm ocean at sunset"` gives you the **ocean** palette (it appears first),
while `"a sunset over the calm ocean"` gives you **sunset**. Word order matters,
and that's intentional — it's the one rule that's easy to reason about.

If nothing matches a category, the parser falls back: subject → `abstract`,
style → `cinematic`, mood → `calm`, and palette → a deterministic hash of your
prompt (so an unmatched prompt still gets a stable, repeatable look).

### The preview chips

As you type, the composer calls `POST /api/preview` and shows you what it
understood: palette, subject, style, mood, size, seed, and the keywords it
matched. Nothing is hidden. If the result isn't what you wanted, the chips tell
you which word to change.

### Style

An explicit style in the dropdown **overrides** whatever the parser would have
read from your text. Leave it on the default and the text decides.

### Aspect ratio

| Ratio | Use |
|---|---|
| 1:1 | Square — avatars, feed posts |
| 16:9 | Wide — desktop, YouTube thumbnails |
| 9:16 | Vertical — Reels, TikTok, Stories |
| 3:2 | Classic photo landscape |
| 2:3 | Classic photo portrait |
| 4:5 | Instagram feed |

The long side is always 1024px, rounded to a multiple of 8.

### Seed

Leave it blank and the seed is derived from a hash of your prompt — so the same
prompt always gives the same image. Set it explicitly to explore variations of
the same prompt, or to reproduce an image you made earlier.

**Same prompt + same seed = byte-identical image.** That's a guarantee, not a
hope; there's a test for it.

### Negative prompt

Words to steer away from. With the local provider this is recorded and shown in
the detail view but doesn't change the render (a procedural renderer has no
concept of "blurry"). With Gemini it's passed through as an "avoid" instruction.

## The gallery

- **Search** filters by prompt text, debounced at 320ms.
- **★ Favourites** toggles a favourites-only view.
- **Load more** pages through 24 at a time.
- Click any card for the detail view: full image, every generation parameter,
  and Download / Favourite / Delete.

## Keyboard

| Key | Action |
|---|---|
| `Enter` / `Space` on a card | Open detail view |
| `Esc` | Close detail view |

## API walkthrough

```bash
# 1. Register
curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","display_name":"You","password":"password123"}'
# → {"access_token":"eyJ...","token_type":"bearer","expires_in":86400}

TOKEN="eyJ..."

# 2. See what the parser thinks (no render, no auth needed)
curl -s -X POST http://127.0.0.1:8000/api/preview \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a neon city at night"}'
# → {"palette":"neon","subject":"city","style":"neon","mood":"calm",...}

# 3. Generate
curl -s -X POST http://127.0.0.1:8000/api/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a neon city at night","aspect_ratio":"16:9"}'
# → {"id":1,"width":1024,"height":576,"image_url":"/api/images/1",...}

# 4. Fetch the image
curl -s http://127.0.0.1:8000/api/images/1 -o city.png

# 5. List your gallery
curl -s "http://127.0.0.1:8000/api/generations?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## Rate limits

| Endpoint | Limit |
|---|---|
| `POST /api/generate` | 20 / minute per IP |
| everything else | 120 / minute per IP |

Exceeding a limit returns **429** with a `Retry-After` header. Limits are
configurable via `RATE_LIMIT_GENERATE` and `RATE_LIMIT_DEFAULT`.

## Common errors

| Status | Meaning |
|---|---|
| 401 | Missing, malformed or expired token |
| 404 | Not found — **or** it belongs to another user (we don't confirm which) |
| 409 | Email already registered |
| 422 | Validation failed; the body lists every offending field |
| 429 | Rate limited |
| 503 | The selected provider is unavailable (e.g. Gemini without a key) |
