from app.services.query_service import (
    _build_human_intervention_state,
    _build_tender_resume_comparison_answer,
)


def test_build_human_intervention_state_returns_pending_tasks(monkeypatch):
    captured_ids = []

    def fake_list_open_review_tasks(document_ids):
        captured_ids.extend(document_ids)
        return [
            {
                "id": 101,
                "document_id": 11,
                "document_type": "tender",
                "status": "pending",
            }
        ]

    monkeypatch.setattr(
        "app.services.query_service.list_open_review_tasks_for_documents",
        fake_list_open_review_tasks,
    )

    state = _build_human_intervention_state(
        {
            "tender": [{"id": 11}],
            "resume": [{"id": 22}, {"id": 33}],
        },
        ["tender", "resume"],
    )

    assert captured_ids == [11, 22, 33]
    assert state["human_intervention_required"] is True
    assert state["review_tasks"] == [
        {
            "id": 101,
            "document_id": 11,
            "document_type": "tender",
            "status": "pending",
        }
    ]


def test_build_human_intervention_state_honors_scope(monkeypatch):
    captured_ids = []

    def fake_list_open_review_tasks(document_ids):
        captured_ids.extend(document_ids)
        return []

    monkeypatch.setattr(
        "app.services.query_service.list_open_review_tasks_for_documents",
        fake_list_open_review_tasks,
    )

    state = _build_human_intervention_state(
        {
            "tender": [{"id": 11}],
            "resume": [{"id": 22}],
        },
        ["tender"],
    )

    assert captured_ids == [11]
    assert state["human_intervention_required"] is False
    assert state["human_intervention_reason"] == ""
    assert state["review_tasks"] == []


def test_build_tender_resume_comparison_answer_flags_bidder_vs_cv_mismatch(monkeypatch):
    tender_document = {
        "id": 11,
        "document_type": "tender",
        "status": "stored",
        "structured_data": {
            "role": "Highway Construction Contractor",
            "domain": "Highway Construction",
            "skills_required": ["Highway Construction", "Bridge Engineering"],
        },
    }
    resume_document = {
        "id": 22,
        "document_type": "resume",
        "status": "stored",
        "structured_data": {
            "candidate_name": "Dharmireddi Sanyasi Naidu",
            "role": "Bridge Structural Engineer",
            "domain": "Highway Construction",
            "skills": ["Highway Construction", "Bridge Engineering"],
        },
    }

    monkeypatch.setattr(
        "app.services.query_service._scope_documents_for_exact_extraction",
        lambda *args, **kwargs: {"tender": [tender_document], "resume": [resume_document]},
    )

    def fake_all_page_chunks_for_documents(documents):
        document = documents[0]
        if document["document_type"] == "tender":
            return [
                {
                    "document_id": 11,
                    "filename": "tender.pdf",
                    "page_start": 1,
                    "page_end": 1,
                    "section": "general",
                    "chunk_id": 1,
                    "text": (
                        "Request for Proposals for Construction of 4 Lanning in Madhya Pradesh "
                        "on Hybrid Annuity Mode."
                    ),
                },
                {
                    "document_id": 11,
                    "filename": "tender.pdf",
                    "page_start": 4,
                    "page_end": 4,
                    "section": "eligibility",
                    "chunk_id": 4,
                    "text": (
                        "Selection of a private entity as the Bidder with technical capacity, "
                        "financial capacity, bid security, power of attorney, and consortium requirements."
                    ),
                },
            ]
        return [
            {
                "document_id": 22,
                "filename": "tender_resume.pdf",
                "page_start": 1,
                "page_end": 1,
                "section": "general",
                "chunk_id": 1,
                "text": (
                    "Technical Proposal. Proposed Position: Bridge Structural Engineer. "
                    "Name of Firm: Rodic Consultants Pvt. Ltd. Name of Staff: Dharmireddi Sanyasi Naidu. "
                    "Independent Engineer Services in Odisha."
                ),
            }
        ]

    monkeypatch.setattr(
        "app.services.query_service._all_page_chunks_for_documents",
        fake_all_page_chunks_for_documents,
    )
    monkeypatch.setattr(
        "app.services.query_service.preferred_structured_data",
        lambda document: document.get("structured_data", {}),
    )

    result = _build_tender_resume_comparison_answer(
        "Compare tender and resume",
        ["tender", "resume"],
    )

    assert result is not None
    answer_text, sources = result
    assert "Final verdict: Not a Valid Match" in answer_text
    assert "bidder/company/consortium" in answer_text
    assert "individual consultant CV" in answer_text
    assert len(sources) >= 2


def test_build_tender_resume_comparison_answer_handles_candidate_project_phrasing(monkeypatch):
    tender_document = {
        "id": 11,
        "document_type": "tender",
        "status": "stored",
        "structured_data": {},
    }
    resume_document = {
        "id": 22,
        "document_type": "resume",
        "status": "stored",
        "structured_data": {},
    }

    monkeypatch.setattr(
        "app.services.query_service._scope_documents_for_exact_extraction",
        lambda *args, **kwargs: {"tender": [tender_document], "resume": [resume_document]},
    )
    monkeypatch.setattr(
        "app.services.query_service._all_page_chunks_for_documents",
        lambda documents: [
            {
                "document_id": documents[0]["id"],
                "filename": "tender.pdf" if documents[0]["document_type"] == "tender" else "tender_resume.pdf",
                "page_start": 1,
                "page_end": 1,
                "section": "general",
                "chunk_id": 1,
                "text": (
                    "Selection of a private entity as the Bidder with technical capacity and financial capacity."
                    if documents[0]["document_type"] == "tender"
                    else "Technical Proposal Proposed Position Bridge Structural Engineer Name of Staff Dharmireddi Sanyasi Naidu"
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "app.services.query_service.preferred_structured_data",
        lambda document: document.get("structured_data", {}),
    )

    result = _build_tender_resume_comparison_answer(
        "compare project of this candidate with projects of tender",
        ["tender", "resume"],
    )

    assert result is not None
    answer_text, _ = result
    assert "Project comparison:" in answer_text
    assert "Final verdict: Not a Valid Match" in answer_text
