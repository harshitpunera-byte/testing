from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.search_service import get_resume_profile_debug, search_resumes


router = APIRouter(prefix="/search", tags=["Search"])


class ResumeSearchRequest(BaseModel):
    query: str
    page: int = 1
    page_size: int = 20


@router.post("/resumes")
def search_resume_profiles(request: ResumeSearchRequest):
    return search_resumes(request.query, page=request.page, page_size=request.page_size)


@router.get("/resumes/{document_id}")
def get_resume_profile_details(document_id: int):
    return get_resume_profile_debug(document_id)
