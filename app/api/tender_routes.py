from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from app.services.tender_service import process_tender
from app.services.review_service import approve_tender_criteria

router = APIRouter(prefix="/tenders", tags=["Tenders"])


class TenderCriteriaCorrectionItemRequest(BaseModel):
    review_item_id: int | None = None
    field_name: str | None = None
    corrected_value: Any = None


class TenderCriteriaApprovalRequest(BaseModel):
    reviewer: str | None = None
    review_notes: str | None = None
    corrections: list[TenderCriteriaCorrectionItemRequest] = Field(default_factory=list)

@router.post("/upload")
async def upload_tender(file: UploadFile = File(...)):
    return await process_tender(file)


@router.post("/{document_id}/approve-criteria")
def approve_tender_review(document_id: int, request: TenderCriteriaApprovalRequest):
    try:
        return approve_tender_criteria(
            document_id,
            reviewer=request.reviewer,
            review_notes=request.review_notes,
            corrections=[item.model_dump() for item in request.corrections],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
