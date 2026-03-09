from fastapi import APIRouter
from pydantic import BaseModel
from app.services.matching_service import match_resumes_with_tender

router = APIRouter(prefix="/match", tags=["Matching"])


class MatchRequest(BaseModel):
    tender_text: str


@router.post("/")
def match(request: MatchRequest):

    results = match_resumes_with_tender(request.tender_text)

    return {
        "matches": results
    }