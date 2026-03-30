from fastapi import APIRouter
from pydantic import BaseModel

from app.services.query_service import answer_query
from app.services.review_service import record_match_feedback

router = APIRouter(prefix="/match", tags=["Matching"])


class MatchRequest(BaseModel):
    query: str
    tender_document_id: int | None = None
    resume_document_ids: list[int] | None = None
    restrict_to_active_uploads: bool = False


class MatchFeedbackRequest(BaseModel):
    tender_document_id: int
    resume_document_id: int
    system_score: float | None = None
    human_decision: str
    reason_code: str | None = None
    review_comment: str | None = None
    reviewed_by: str | None = None


@router.post("/")
def match(request: MatchRequest):
    results = answer_query(
        request.query,
        tender_document_id=request.tender_document_id,
        resume_document_ids=request.resume_document_ids,
        restrict_to_active_uploads=request.restrict_to_active_uploads,
    )

    return {
        "matches": results
    }


@router.post("/feedback")
def save_match_feedback(request: MatchFeedbackRequest):
    return record_match_feedback(
        tender_document_id=request.tender_document_id,
        resume_document_id=request.resume_document_id,
        system_score=request.system_score,
        human_decision=request.human_decision,
        reason_code=request.reason_code,
        review_comment=request.review_comment,
        reviewed_by=request.reviewed_by,
    )
