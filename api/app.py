"""api/app.py — FastAPI application instance with all middleware and routes wired.

Entry point for uvicorn: ``uvicorn api.main:app`` (main.py re-exports this app).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api.state as state
from api.lifespan import lifespan
from api.middleware import (
    add_security_headers,
    auth_middleware,
    body_size_limit_middleware,
    drain_middleware,
    log_requests,
    rate_limit_middleware,
)
from core.config import get_settings
from core.observability import configure_logging, create_metrics_app

configure_logging(level=get_settings().log_level.value)

_settings = get_settings()
_is_production = _settings.environment == "production"

app = FastAPI(
    title="LangGraph Agent Stack API",
    description=(
        "Production API exposing a multi-agent LangGraph pipeline. "
        "The pipeline sequences a ResearchAgent and an AnalystAgent "
        "to turn a free-text query into a structured AnalysisReport."
    ),
    version=state.APP_VERSION,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Prometheus metrics endpoint — exempt from auth and rate limiting
# ---------------------------------------------------------------------------

_metrics_app = create_metrics_app()
if _metrics_app is not None:
    app.mount("/metrics", _metrics_app)

# ---------------------------------------------------------------------------
# CORS — fail-closed: no wildcard unless explicitly set in CORS_ORIGINS
# ---------------------------------------------------------------------------

_cors_origins = _settings.cors_origins
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
elif not _is_production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

# ---------------------------------------------------------------------------
# Middlewares (registered in reverse execution order)
# ---------------------------------------------------------------------------

app.middleware("http")(add_security_headers)
app.middleware("http")(auth_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(log_requests)
app.middleware("http")(drain_middleware)
app.middleware("http")(body_size_limit_middleware)

# ---------------------------------------------------------------------------
# Static routers
# ---------------------------------------------------------------------------

from api.endpoints import health, packs, pipeline, sessions  # noqa: E402

app.include_router(health.router)
app.include_router(pipeline.router)
app.include_router(packs.router)
app.include_router(sessions.router)
