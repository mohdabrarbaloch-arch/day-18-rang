"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI callable named `app` in this file.
The real application lives in `app/main.py`; this module only re-exports it so
the whole `app/` package ships with the function (see `includeFiles` in
vercel.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repository root importable when running as a serverless function.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

__all__ = ["app"]
