from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.database.connection import session_scope
from app.models.db_models import FieldChangeAudit
from app.services.document_repository import (
    create_document_record,
    delete_all_documents,
    get_document_by_id,
    get_resume_profile_with_relations,
)
from app.services.matching_service import _extract_or_load_structured_data, _score_candidate
from app.services.profile_normalizer import normalize_resume_profile
from app.services.review_service import (
    approve_review_task,
    correct_review_task,
    get_review_task_detail,
    list_review_tasks,
    sync_document_review_state,
)
from app.services.search_service import search_resumes


def _make_document(*, document_type: str, suffix: str, structured_data: dict, evidence_map: dict | None = None, raw_text: str = "") -> dict:
    return create_document_record(
        document_type=document_type,
        original_filename=f"{document_type}-{suffix}.pdf",
        stored_filename=f"{document_type}-{suffix}.pdf",
        stored_path=f"/tmp/{document_type}-{suffix}.pdf",
        file_hash=f"{document_type}-{suffix}",
        file_size=max(1, len(raw_text or "placeholder")),
        mime_type="application/pdf",
        status="stored",
        raw_text=raw_text,
        markdown_text=raw_text,
        structured_data=structured_data,
        evidence_map=evidence_map or {},
        metadata_json={},
    )


def _resume_evidence() -> dict:
    return {
        "candidate_name": {"value": "Rahul Sharma", "page": 1, "source_text": "Rahul Sharma", "confidence": 0.94},
        "role": {"value": "Python Developer", "page": 1, "source_text": "Python Developer", "confidence": 0.84},
        "total_experience_years": {"value": 2, "page": 1, "source_text": "2 years of experience", "confidence": 0.72},
        "skills": [
            {"value": "Python", "page": 1, "source_text": "Python", "confidence": 0.88},
        ],
    }


@pytest.fixture(autouse=True)
def cleanup_database():
    delete_all_documents()
    yield
    delete_all_documents()


def test_document_needing_review_creates_task_and_items():
    structured_data = {
        "candidate_name": None,
        "role": "Python Developer",
        "domain": "AI/ML",
        "skills": [],
        "total_experience_years": None,
        "qualifications": [],
        "projects": [],
    }
    document = _make_document(
        document_type="resume",
        suffix="needs-review",
        structured_data=structured_data,
        evidence_map={},
        raw_text="Short OCR text",
    )

    result = sync_document_review_state(
        document_id=document["id"],
        document_type="resume",
        text="Short OCR text",
        structured_data=structured_data,
        evidence_map={},
        extraction_backend="ocr",
    )

    updated = get_document_by_id(document["id"])
    detail = get_review_task_detail(result["review_task_id"])

    assert updated["review_status"] == "needs_review"
    assert updated["canonical_data_ready"] is False
    assert result["review_task_id"] is not None
    assert detail["status"] == "pending"
    assert any(item["field_name"] == "candidate_name" for item in detail["items"])


def test_approve_flow_updates_review_status():
    structured_data = {
        "candidate_name": "Rahul Sharma",
        "role": "Python Developer",
        "domain": "AI/ML",
        "skills": [{"raw": "Python", "generic": "python"}],
        "total_experience_years": 2,
        "qualifications": [],
        "projects": [],
    }
    document = _make_document(
        document_type="resume",
        suffix="approve",
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        raw_text="Rahul Sharma Python Developer with 2 years of experience in Python.",
    )

    result = sync_document_review_state(
        document_id=document["id"],
        document_type="resume",
        text=document["raw_text"],
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        extraction_backend="pymupdf",
    )
    approved = approve_review_task(result["review_task_id"], reviewer="qa-user", review_notes="Looks fine.")
    updated = get_document_by_id(document["id"])

    assert approved["status"] == "approved"
    assert updated["review_status"] == "approved"
    assert updated["canonical_data_ready"] is True
    assert updated["reviewed_data"]["role"] == "Python Developer"


def test_correction_flow_updates_canonical_data_and_audit():
    structured_data = {
        "candidate_name": "Rahul Sharma",
        "role": "Python Developer",
        "domain": "AI/ML",
        "skills": [{"raw": "Python", "generic": "python"}],
        "total_experience_years": 2,
        "qualifications": [],
        "projects": [],
    }
    document = _make_document(
        document_type="resume",
        suffix="correct",
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        raw_text="Rahul Sharma Python Developer with 2 years of experience in Python.",
    )

    result = sync_document_review_state(
        document_id=document["id"],
        document_type="resume",
        text=document["raw_text"],
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        extraction_backend="pymupdf",
    )
    corrected = correct_review_task(
        result["review_task_id"],
        reviewer="reviewer-a",
        review_notes="Updated title, skills, and experience.",
        corrections=[
            {"field_name": "role", "corrected_value": "Senior Backend Engineer"},
            {"field_name": "skills", "corrected_value": [
                {"raw": "Python", "generic": "python"},
                {"raw": "FastAPI", "generic": "fastapi"},
                {"raw": "PostgreSQL", "generic": "postgresql"}
            ]},
            {"field_name": "total_experience_years", "corrected_value": 6},
        ],
    )

    updated = get_document_by_id(document["id"])
    normalized = get_resume_profile_with_relations(document["id"])
    with session_scope() as db:
        audit_rows = db.scalar(
            select(func.count()).select_from(FieldChangeAudit).where(FieldChangeAudit.document_id == document["id"])
        )

    assert corrected["status"] == "corrected"
    assert updated["review_status"] == "corrected"
    assert updated["reviewed_data"]["role"] == "Senior Backend Engineer"
    assert updated["canonical_data_ready"] is True
    assert int(audit_rows or 0) >= 3
    assert normalized["normalized_title"] == "senior backend engineer"
    assert normalized["total_experience_months"] == 72
    assert "fastapi" in [item["skill_name_normalized"] for item in normalized["skills"]]


def test_matching_prefers_reviewed_canonical_data():
    document = {
        "structured_data": {
            "role": "Old Tender Role",
            "domain": "Legacy",
            "skills_required": [{"raw": "Cobol", "generic": "cobol"}],
            "preferred_skills": [],
            "experience_required": 3,
            "qualifications": [],
            "responsibilities": [],
        },
        "reviewed_data": {
            "role": "Senior Backend Engineer",
            "domain": "AI/ML",
            "skills_required": [{"raw": "Python", "generic": "python"}, {"raw": "FastAPI", "generic": "fastapi"}],
            "preferred_skills": [{"raw": "PostgreSQL", "generic": "postgresql"}],
            "experience_required": 6,
            "qualifications": [],
            "responsibilities": [],
        },
        "canonical_data_ready": True,
        "evidence_map": {},
    }

    resolved, evidence = _extract_or_load_structured_data("tender", document, [], "")

    assert resolved["role"] == "Senior Backend Engineer"
    assert [s["raw"] for s in resolved["skills_required"]] == ["Python", "FastAPI"]
    assert evidence == {}


def test_score_candidate_rejects_bidder_tender_vs_consultant_cv_false_positive():
    tender_data = {
        "role": "Highway Construction Contractor",
        "role_generic": "highway_construction_contractor",
        "domain": "Highway Construction",
        "domain_generic": "highway_construction",
        "skills_required": [{"raw": "Highway Construction", "generic": "highway_construction"}, {"raw": "Bridge Engineering", "generic": "bridge_engineering"}],
        "preferred_skills": [{"raw": "Construction Management", "generic": "construction_management"}],
        "experience_required": None,
    }
    resume_data = {
        "candidate_name": "Dharmireddi Sanyasi Naidu",
        "role": "Bridge Structural Engineer",
        "role_generic": "bridge_structural_engineer",
        "domain": "Highway Construction",
        "domain_generic": "highway_construction",
        "skills": [{"raw": "Highway Construction", "generic": "highway_construction"}, {"raw": "Bridge Engineering", "generic": "bridge_engineering"}],
        "experience": 20,
        "total_experience_years": 20,
    }

    scored = _score_candidate(
        tender_data,
        resume_data,
        tender_text=(
            "Request for Proposals. Selection of a private entity as the Bidder. "
            "Technical Capacity, Financial Capacity, Bid Security, Consortium, Power of Attorney."
        ),
        resume_text=(
            "Technical Proposal. Proposed Position: Bridge Structural Engineer. "
            "Name of Firm: Rodic Consultants Pvt. Ltd. Name of Staff: Dharmireddi Sanyasi Naidu. "
            "Independent Engineer Services."
        ),
    )

    assert scored["score"] == 0.0
    assert scored["verdict"] == "Low Suitable"
    assert scored["eligibility_intent_match"] is False
    assert scored["disqualifiers"]


def test_search_returns_results_with_review_metadata():
    structured_data = {
        "candidate_name": "Rahul Sharma",
        "role": "Senior Backend Engineer",
        "domain": "AI/ML",
        "skills": [{"raw": "Python", "generic": "python"}, {"raw": "FastAPI", "generic": "fastapi"}, {"raw": "PostgreSQL", "generic": "postgresql"}],
        "total_experience_years": 6,
        "qualifications": [],
        "projects": [],
    }
    document = _make_document(
        document_type="resume",
        suffix="search",
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        raw_text=(
            "Rahul Sharma Senior Backend Engineer with 6 years of experience in Python FastAPI PostgreSQL. "
            "Built backend APIs, retrieval systems, and search services for production recruiting workflows. "
            "Worked with PostgreSQL, vector search, and structured profile normalization across multiple resume ingestion pipelines. "
            "Delivered candidate ranking, review tooling, and evidence-backed extraction features for enterprise hiring teams."
        ),
    )
    review_state = sync_document_review_state(
        document_id=document["id"],
        document_type="resume",
        text=document["raw_text"],
        structured_data=structured_data,
        evidence_map=_resume_evidence(),
        extraction_backend="pymupdf",
    )
    if review_state.get("review_task_id"):
        approve_review_task(review_state["review_task_id"], reviewer="qa-user", review_notes="Approve canonical search fixture.")
    normalize_resume_profile(
        document["id"],
        structured_data,
        document["raw_text"],
        _resume_evidence(),
        confidence_score=0.91,
        source_kind="canonical_reviewed",
    )

    results = search_resumes("Find candidates with Python and 6+ years experience", page=1, page_size=5)

    assert results["results"]
    assert results["results"][0]["candidate_name"] == "Rahul Sharma"
    assert results["results"][0]["review_status"] == "approved"
    assert results["results"][0]["uses_unreviewed_data"] is False
