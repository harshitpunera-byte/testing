from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.review_service import (
    approve_review_task,
    correct_review_task,
    get_review_task_detail,
    list_review_tasks,
    reject_review_task,
)


router = APIRouter(prefix="/reviews", tags=["Reviews"])


class ReviewActionRequest(BaseModel):
    reviewer: str | None = None
    review_notes: str | None = None


class ReviewCorrectionItemRequest(BaseModel):
    review_item_id: int | None = None
    field_name: str | None = None
    corrected_value: Any = None


class ReviewCorrectRequest(ReviewActionRequest):
    corrections: list[ReviewCorrectionItemRequest] = Field(default_factory=list)


@router.get("")
def review_task_list(
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
):
    return list_review_tasks(
        status=status,
        task_type=task_type,
        document_type=document_type,
    )


@router.get("/{task_id}")
def review_task_detail(task_id: int):
    detail = get_review_task_detail(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    return detail


@router.post("/{task_id}/approve")
def approve_task(task_id: int, request: ReviewActionRequest):
    try:
        return approve_review_task(
            task_id,
            reviewer=request.reviewer,
            review_notes=request.review_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/correct")
def correct_task(task_id: int, request: ReviewCorrectRequest):
    try:
        return correct_review_task(
            task_id,
            reviewer=request.reviewer,
            review_notes=request.review_notes,
            corrections=[item.model_dump() for item in request.corrections],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/reject")
def reject_task(task_id: int, request: ReviewActionRequest):
    try:
        return reject_review_task(
            task_id,
            reviewer=request.reviewer,
            review_notes=request.review_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
