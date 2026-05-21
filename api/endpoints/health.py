"""api/endpoints/health.py — Health, readiness probes and root redirect."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

import api.state as state
from api.models import ComponentHealth, HealthResponse
from core.config import Settings, get_settings

router = APIRouter(tags=["Operations"])


def _check_checkpointer_health(settings: Settings) -> tuple[str, str]:
    """Probe the checkpointer backend for real connectivity."""
    backend = settings.memory_backend.value

    if backend == "redis" and settings.redis_url:
        try:
            import redis as redis_lib

            r = redis_lib.Redis.from_url(settings.redis_url, socket_timeout=2)
            r.ping()
            r.close()
            return ("ok", "redis reachable")
        except Exception as exc:
            return ("degraded", f"redis unreachable: {exc}")

    if backend == "postgres" and settings.postgres_url:
        try:
            import psycopg

            with psycopg.connect(settings.postgres_url, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return ("ok", "postgres reachable")
        except Exception as exc:
            return ("degraded", f"postgres unreachable: {exc}")

    return ("ok", backend)


@router.get("/", include_in_schema=False, summary="Root redirect or probe hints")
async def root(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Any:
    """In development, redirect to /docs. In production, return machine-readable hints."""
    from fastapi.responses import JSONResponse

    if settings.environment == "production":
        return JSONResponse(
            {
                "service": "langgraph-agent-stack",
                "health": "/health",
                "ready": "/ready",
                "docs": "disabled in production",
            }
        )
    return RedirectResponse(url="/docs", status_code=status.HTTP_302_FOUND)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    response_description="Service health status and uptime information.",
)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Return the current health status of the service."""
    components: dict[str, ComponentHealth] = {}

    components["llm"] = (
        ComponentHealth(status="ok", detail=f"{settings.llm_provider} (initialised)")
        if state.shared_llm is not None
        else ComponentHealth(status="degraded", detail="LLM not initialised")
    )

    if state.shared_memory is not None:
        mem_status, mem_detail = state.shared_memory.health_check()
        components["memory"] = ComponentHealth(
            status="ok" if mem_status == "ok" else "degraded", detail=mem_detail
        )
    else:
        components["memory"] = ComponentHealth(
            status="degraded", detail="Memory store not initialised"
        )

    if state.shared_checkpointer is not None:
        chk_status, chk_detail = _check_checkpointer_health(settings)
        components["checkpointer"] = ComponentHealth(
            status="ok" if chk_status == "ok" else "degraded", detail=chk_detail
        )
    else:
        components["checkpointer"] = ComponentHealth(
            status="degraded", detail="Checkpointer not initialised"
        )

    overall = "ok" if all(c.status == "ok" for c in components.values()) else "degraded"
    return HealthResponse(
        status=overall,
        version=state.APP_VERSION,
        uptime_seconds=round(time.monotonic() - state.start_time, 3),
        environment=settings.environment,
        components=components,
    )


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    response_description="Returns 200 when the service is ready to accept traffic.",
)
async def ready() -> dict[str, str]:
    """Readiness probe for Kubernetes."""
    if state.shutting_down.is_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is shutting down.",
        )
    if state.get_shared_llm() is None or state.get_shared_checkpointer() is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready: LLM or checkpointer not initialised.",
        )
    return {"status": "ready"}
