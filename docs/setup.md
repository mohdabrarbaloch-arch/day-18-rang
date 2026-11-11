# Setup

## Requirements

- Python 3.11 or newer
- pip
- Optional: Docker + Docker Compose (for the Postgres path)

No API key is required. The default renderer runs entirely in-process.

## Local install

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-18-rang.git
cd day-18-rang

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

`pip install -e .` alone is enough to run the app; `[dev]` adds pytest, ruff and
black.

## Configure

```bash
cp .env.example .env
```

Then open `.env` and set `SECRET_KEY` to something random:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Everything else has a working default. You can skip this step entirely for a
local run — the app boots with a development key and warns you in the logs.

## Seed demo data (optional)

```bash
python -m app.seed
```

This creates `demo@rang.pk` / `rangdemo12345` and renders eight images so the
gallery isn't empty on first load. It takes a few seconds.

## Run

```bash
uvicorn app.main:app --reload
```

- App: <http://127.0.0.1:8000>
- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

## Docker

```bash
docker compose up --build
```

Brings up the app on port 8000 and Postgres 16 on 5432. The app waits for the
database health check before starting.

To use Postgres without Docker, install the driver and point at your server:

```bash
pip install "psycopg[binary]"
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/rang"
uvicorn app.main:app --reload
```

## Switching to the Gemini provider

```bash
export IMAGE_PROVIDER=gemini
export GEMINI_API_KEY="your-key-here"
```

Or set both in `.env`. If you select `gemini` without a key, generation returns
a **503** with a message telling you exactly that — it does not silently fall
back to local, because a silent fallback would make you think you were looking
at a Gemini image when you weren't.

## Troubleshooting

**`ModuleNotFoundError: No module named 'app'`**
Run from the repository root, and make sure you installed with `-e` so the
package is importable.

**`bcrypt` errors on install**
The project pins `bcrypt==4.0.1` because passlib 1.7.4 reads an attribute that
newer bcrypt versions removed. Don't unpin it without also moving off passlib.

**Images look identical for different prompts**
That's the parser finding the same palette and subject. Check the preview chips
in the composer — they show exactly what it matched. Add a more specific word
(a colour, a place, a mood) or set an explicit seed.

**`database is locked` under load**
SQLite allows one writer at a time. Switch to Postgres via `DATABASE_URL`.
