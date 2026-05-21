"""api/main.py — Uvicorn entry point (thin re-export).

Usage: uvicorn api.main:app --host 0.0.0.0 --port 8000

All application logic lives in api/app.py and its sub-modules.
This file exists solely to preserve the ``api.main:app`` entry point used
by the Dockerfile, CI smoke test, and docker-compose.
"""

from api.app import app  # noqa: F401

__all__ = ["app"]
