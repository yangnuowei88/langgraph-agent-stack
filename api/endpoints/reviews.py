"""api/endpoints/reviews.py — Human-review queue for regulated pack outputs.

Regulated packs return ``human_review_required=True`` on every output; this
router closes the compliance loop by letting a human reviewer list pending
runs, inspect one, and record an approve/reject decision.

Auth and rate limiting apply via the global middlewares (``/reviews`` is not
in any exemption list).
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi import Path as FastAPIPath

import api.state as state
from api.models import ReviewDecisionRequest, ReviewEntry, ReviewListResponse
from core.review_store import (
    ReviewAlreadyDecidedError,
    ReviewNotFoundError,
    ReviewRecord,
)

router = APIRouter(prefix="/reviews", tags=["Reviews"])
logger = logging.getLogger(__name__)

_RUN_ID_PATH = FastAPIPath(
    min_length=1,
    max_length=64,
    pattern=r"^[a-zA-Z0-9_-]+$",
    description="Run identifier the review refers to.",
)


def _require_store():
    if state.review_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review store unavailable.",
        )
    return state.review_store


def _to_entry(record: ReviewRecord) -> ReviewEntry:
    return ReviewEntry(**record.model_dump())


@router.get(
    "",
    response_model=ReviewListResponse,
    summary="List human-review queue entries",
)
async def list_reviews(
    status_filter: Annotated[
        Literal["pending", "approved", "rejected"] | None,
        Query(alias="status", description="Filter by review state."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewListResponse:
    """Return reviews newest-first, optionally filtered by status."""
    store = _require_store()
    records = store.list_reviews(status=status_filter, limit=limit, offset=offset)
    entries = [_to_entry(r) for r in records]
    return ReviewListResponse(reviews=entries, total=len(entries))


@router.get(
    "/{run_id}",
    response_model=ReviewEntry,
    summary="Get one review by run_id",
)
async def get_review(run_id: Annotated[str, _RUN_ID_PATH]) -> ReviewEntry:
    """Return the review for *run_id* (404 when unknown)."""
    store = _require_store()
    record = store.get(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No review found for this run_id.",
        )
    return _to_entry(record)


@router.post(
    "/{run_id}/decision",
    response_model=ReviewEntry,
    summary="Record an approve/reject decision",
)
async def decide_review(
    run_id: Annotated[str, _RUN_ID_PATH],
    body: ReviewDecisionRequest,
) -> ReviewEntry:
    """Record the reviewer's decision (409 when already decided)."""
    store = _require_store()
    try:
        record = store.decide(
            run_id,
            status=body.status,
            reviewer=body.reviewer,
            notes=body.notes,
        )
    except ReviewNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No review found for this run_id.",
        ) from exc
    except ReviewAlreadyDecidedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    logger.info(
        "Review decided",
        extra={"run_id": run_id, "status": body.status, "reviewer": body.reviewer},
    )
    return _to_entry(record)
