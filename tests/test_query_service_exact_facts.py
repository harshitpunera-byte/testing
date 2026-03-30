from types import SimpleNamespace

from app.services.query_service import (
    _answer_qa,
    _build_exact_fact_answer,
    _extract_chainage_range,
    _extract_resume_dob,
    _extract_resume_project_cost,
)


MULTI_FACT_QUERY = (
    "Tell me the LOA definition clause from the glossary, the total Project Cost "
    "for the supervision project in Andhra Pradesh, the Chainage range mentioned "
    "in Appendix-VII, the minimum required Net Worth for bidders, and the Date of "
    "Birth of staff member Dharmireddi Sanyasi Naidu"
)


def _tender_chunks():
    return [
        {
            "document_id": 101,
            "filename": "tender.pdf",
            "page_start": 8,
            "page_end": 8,
            "section": "general",
            "chunk_id": 8,
            "text": (
                "GLOSSARY LOA As defined in Clause 3.8.4 "
                "Selected Bidder As defined in Clause 3.8.1"
            ),
        },
        {
            "document_id": 101,
            "filename": "tender.pdf",
            "page_start": 33,
            "page_end": 33,
            "section": "eligibility",
            "chunk_id": 33,
            "text": (
                "Financial Capacity: The Bidder shall have a minimum available Net Worth "
                "(the Financial Capacity) of Rs. 332.59 Crore at the close of the preceding "
                "financial year."
            ),
        },
        {
            "document_id": 101,
            "filename": "tender.pdf",
            "page_start": 111,
            "page_end": 111,
            "section": "general",
            "chunk_id": 111,
            "text": (
                "Appendix-VII Sub: BID for 4 Lanning of Badnawar-Petlawad-Thandla-Timarwani "
                "section of (NH-752D) from Badnawar Bypass Ch. 70+400 to Timarwani "
                "Interchange of Delhi Mumbai expressway (NE-4) Ch. 150+850 in the state "
                "of Madhya Pradesh on Hybrid Annuity Mode under NH(O)"
            ),
        },
    ]


def _resume_chunks():
    return [
        {
            "document_id": 202,
            "filename": "tender_resume.pdf",
            "page_start": 1,
            "page_end": 1,
            "section": "general",
            "chunk_id": 1,
            "text": (
                "Name of Staff : Dharmireddi Sanyasi Naidu Profession : Civil Engineering "
                "Date of Birth: : 1st July 1970 Date: 11/11/2025"
            ),
        },
        {
            "document_id": 202,
            "filename": "tender_resume.pdf",
            "page_start": 15,
            "page_end": 15,
            "section": "experience",
            "chunk_id": 15,
            "text": (
                "Experience Details Name of Work Consultancy Services for Authority Engineer "
                "for Supervision of Widening of existing road to 4 lane of Tadipatri to "
                "Muddanur Bypass section of NH67 in the State of Andhra Pradesh. "
                "Project Cost 424.99 RS (Cr.)"
            ),
        },
    ]


def test_build_exact_fact_answer_extracts_known_values(monkeypatch):
    def fake_get_latest_document(document_type):
        if document_type == "tender":
            return {"id": 101, "document_type": "tender", "status": "stored"}
        if document_type == "resume":
            return {"id": 202, "document_type": "resume", "status": "stored"}
        return None

    def fake_get_persisted_document_chunks(document_id, limit=None):
        chunks = {
            101: _tender_chunks(),
            202: _resume_chunks(),
        }[document_id]
        return chunks[:limit] if limit is not None else chunks

    monkeypatch.setattr("app.services.query_service.get_latest_document", fake_get_latest_document)
    monkeypatch.setattr(
        "app.services.query_service.get_persisted_document_chunks",
        fake_get_persisted_document_chunks,
    )

    result = _build_exact_fact_answer(MULTI_FACT_QUERY, ["tender", "resume"])

    assert result is not None
    answer_text, source_chunks = result

    assert "LOA definition clause: Clause 3.8.4" in answer_text
    assert "Total Project Cost for the Andhra Pradesh supervision project: 424.99 Rs (Cr.)" in answer_text
    assert "Appendix-VII chainage range: Ch. 70+400 to Ch. 150+850" in answer_text
    assert "Minimum required Net Worth for bidders: Rs. 332.59 Crore" in answer_text
    assert "Date of Birth of Dharmireddi Sanyasi Naidu: 1st July 1970" in answer_text
    assert len(source_chunks) == 5


def test_extract_resume_dob_prefers_birth_label_over_later_date():
    result = _extract_resume_dob(
        "Tell me the Date of Birth of staff member Dharmireddi Sanyasi Naidu",
        _resume_chunks(),
    )

    assert result is not None
    assert result[0] == "1st July 1970"
    assert result[1]["page_start"] == 1


def test_extract_resume_dob_ignores_signature_date_when_birth_date_is_elsewhere():
    result = _extract_resume_dob(
        "Tell me the Date of Birth of staff member Dharmireddi Sanyasi Naidu",
        [
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 1,
                "page_end": 1,
                "section": "general",
                "chunk_id": 1,
                "text": (
                    "Name of Staff : Dharmireddi Sanyasi Naidu Date of Birth: : "
                    "Date: 11/11/2025 Day/Month/Year"
                ),
            },
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 2,
                "page_end": 2,
                "section": "general",
                "chunk_id": 2,
                "text": "Dharmireddi Sanyasi Naidu 01/07/1970 ANDHRA PRADESH",
            },
        ],
    )

    assert result is not None
    assert result[0] == "01/07/1970"
    assert result[1]["page_start"] == 2


def test_extract_resume_dob_handles_pymupdf4llm_compacted_textual_date():
    result = _extract_resume_dob(
        "Tell me the Date of Birth of staff member Dharmireddi Sanyasi Naidu",
        [
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 1,
                "page_end": 1,
                "section": "general",
                "chunk_id": 1,
                "text": (
                    "|**Name of Staff**<br>**:**<br>**Dharmireddi Sanyasi Naidu**| "
                    "|**Date of Birth:**<br>**:**<br>1stJuly 1970| "
                    "|**Date:**|**11/11/2025**|"
                ),
            },
        ],
    )

    assert result is not None
    assert result[0] == "1st July 1970"
    assert result[1]["page_start"] == 1


def test_extract_resume_project_cost_handles_split_label_and_value_chunks():
    result = _extract_resume_project_cost(
        "Tell me the total Project Cost for the supervision project in Andhra Pradesh",
        [
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 6,
                "page_end": 6,
                "section": "experience",
                "chunk_id": 6,
                "text": "Project Cost",
            },
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 6,
                "page_end": 6,
                "section": "experience",
                "chunk_id": 7,
                "text": (
                    "Consultancy Services for Authority Engineer for Supervision in Andhra Pradesh "
                    "424.99 RS (Cr.)"
                ),
            },
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 16,
                "page_end": 16,
                "section": "general",
                "chunk_id": 16,
                "text": "Project Cost",
            },
        ],
    )

    assert result is not None
    assert result[0] == "424.99 Rs (Cr.)"
    assert result[1]["page_start"] == 6


def test_extract_resume_project_cost_handles_pymupdf4llm_split_amount():
    result = _extract_resume_project_cost(
        "Tell me the total Project Cost for the supervision project in Andhra Pradesh",
        [
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 16,
                "page_end": 16,
                "section": "general",
                "chunk_id": 16,
                "text": (
                    "|**Experience Details**| |**State**|AN|DHRA PRADE|SH| "
                    "|**Project Cost**|42|4.99   RS (Cr.|)| "
                    "|**Whether EPC or PPP or**<br>**Hybrid Annuity Model**|EP|C|"
                ),
            },
        ],
    )

    assert result is not None
    assert result[0] == "424.99 Rs (Cr.)"
    assert result[1]["page_start"] == 16


def test_extract_resume_project_cost_prefers_full_value_over_truncated_value():
    result = _extract_resume_project_cost(
        "Tell me the total Project Cost for the supervision project in Andhra Pradesh",
        [
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 15,
                "page_end": 15,
                "section": "experience",
                "chunk_id": 15,
                "text": (
                    "Experience Details Name of Work Consultancy Services for Authority Engineer "
                    "for Supervision in Andhra Pradesh. Project Cost 424.99 RS (Cr.)"
                ),
            },
            {
                "document_id": 202,
                "filename": "tender_resume.pdf",
                "page_start": 16,
                "page_end": 16,
                "section": "general",
                "chunk_id": 16,
                "text": "Project Cost 4.99 RS (Cr.) Andhra Pradesh",
            },
        ],
    )

    assert result is not None
    assert result[0] == "424.99 Rs (Cr.)"
    assert result[1]["page_start"] == 15


def test_extract_chainage_range_prefers_actual_appendix_page_over_instruction_page():
    result = _extract_chainage_range(
        MULTI_FACT_QUERY,
        [
            {
                "document_id": 101,
                "filename": "tender.pdf",
                "page_start": 30,
                "page_end": 30,
                "section": "general",
                "chunk_id": 30,
                "text": (
                    "A certificate on the letterhead of the Bidder shall be required to be submitted "
                    "in the format prescribed at Appendix-VII. Construction of 4 Lanning ... "
                    "Badnawar Bypass Ch. 70+400 to Timarwani Interchange ... Ch. 150+850"
                ),
            },
            {
                "document_id": 101,
                "filename": "tender.pdf",
                "page_start": 111,
                "page_end": 111,
                "section": "general",
                "chunk_id": 111,
                "text": (
                    "Appendix-VII Certificate regarding Compliance ... "
                    "Sub: BID for 4 Lanning ... Badnawar Bypass Ch. 70+400 "
                    "to Timarwani Interchange ... Ch. 150+850"
                ),
            },
        ],
    )

    assert result is not None
    assert result[0] == "Ch. 70+400 to Ch. 150+850"
    assert result[1]["page_start"] == 111


def test_build_exact_fact_answer_prefers_direct_pdf_pages_over_bad_chunks(monkeypatch, tmp_path):
    tender_path = tmp_path / "tender.pdf"
    resume_path = tmp_path / "tender_resume.pdf"
    tender_path.write_bytes(b"fake tender")
    resume_path.write_bytes(b"fake resume")

    def fake_get_latest_document(document_type):
        if document_type == "tender":
            return {
                "id": 101,
                "document_type": "tender",
                "status": "stored",
                "original_filename": "tender.pdf",
                "stored_path": str(tender_path),
            }
        if document_type == "resume":
            return {
                "id": 202,
                "document_type": "resume",
                "status": "stored",
                "original_filename": "tender_resume.pdf",
                "stored_path": str(resume_path),
            }
        return None

    def fake_get_persisted_document_chunks(document_id, limit=None):
        bad_chunks = {
            101: [
                {
                    "document_id": 101,
                    "filename": "tender.pdf",
                    "page_start": 30,
                    "page_end": 30,
                    "section": "eligibility",
                    "chunk_id": 30,
                    "text": "Appendix-VII Ch. 70+400 to Ch. 150+850",
                }
            ],
            202: [
                {
                    "document_id": 202,
                    "filename": "tender_resume.pdf",
                    "page_start": 1,
                    "page_end": 1,
                    "section": "general",
                    "chunk_id": 1,
                    "text": "Date of Birth: Date: 11/11/2025",
                },
                {
                    "document_id": 202,
                    "filename": "tender_resume.pdf",
                    "page_start": 16,
                    "page_end": 16,
                    "section": "general",
                    "chunk_id": 16,
                    "text": "Project Cost 4.99 RS (Cr.)",
                },
            ],
        }[document_id]
        return bad_chunks[:limit] if limit is not None else bad_chunks

    def fake_load_pdf_pages(pdf_bytes, document_name=None):
        if document_name == "tender.pdf":
            return SimpleNamespace(
                pages=[
                    SimpleNamespace(page=8, text="GLOSSARY LOA As defined in Clause 3.8.4"),
                    SimpleNamespace(
                        page=33,
                        text="Financial Capacity: The Bidder shall have a minimum available Net Worth of Rs. 332.59 Crore",
                    ),
                    SimpleNamespace(
                        page=111,
                        text="Appendix-VII ... Ch. 70+400 to Timarwani ... Ch. 150+850",
                    ),
                ]
            )
        return SimpleNamespace(
            pages=[
                SimpleNamespace(
                    page=1,
                    text="Name of Staff Dharmireddi Sanyasi Naidu Date of Birth: 1st July 1970",
                ),
                SimpleNamespace(
                    page=15,
                    text=(
                        "Experience Details Name of Work Supervision in Andhra Pradesh "
                        "Project Cost 424.99 RS (Cr.)"
                    ),
                ),
            ]
        )

    monkeypatch.setattr("app.services.query_service.get_latest_document", fake_get_latest_document)
    monkeypatch.setattr(
        "app.services.query_service.get_persisted_document_chunks",
        fake_get_persisted_document_chunks,
    )
    monkeypatch.setattr("app.services.query_service.load_pdf_pages", fake_load_pdf_pages)

    result = _build_exact_fact_answer(MULTI_FACT_QUERY, ["tender", "resume"])

    assert result is not None
    answer_text, _ = result
    assert "Total Project Cost for the Andhra Pradesh supervision project: 424.99 Rs (Cr.)" in answer_text
    assert "Date of Birth of Dharmireddi Sanyasi Naidu: 1st July 1970" in answer_text


def test_answer_qa_exact_fact_sources_only_include_exact_chunks(monkeypatch):
    exact_chunks = [
        {
            "document_id": 101,
            "filename": "tender.pdf",
            "page_start": 8,
            "page_end": 8,
            "section": "general",
            "chunk_id": 8,
            "text": "LOA As defined in Clause 3.8.4",
        },
        {
            "document_id": 202,
            "filename": "tender_resume.pdf",
            "page_start": 1,
            "page_end": 1,
            "section": "general",
            "chunk_id": 1,
            "text": "Date of Birth 1st July 1970",
        },
    ]

    monkeypatch.setattr(
        "app.services.query_service._gather_scope_context",
        lambda *args, **kwargs: (
            [],
            [
                {
                    "document_id": 101,
                    "filename": "tender.pdf",
                    "page_start": 75,
                    "page_end": 75,
                    "section": "commercial",
                    "chunk_id": 75,
                    "text": "Irrelevant extra page",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service._build_exact_fact_answer",
        lambda *args, **kwargs: ("1. test exact fact", exact_chunks),
    )
    monkeypatch.setattr(
        "app.services.query_service.llm_text_answer",
        lambda prompt: "NO_ADDITIONAL_INTERPRETATION",
    )
    monkeypatch.setattr(
        "app.services.query_service._build_human_intervention_state",
        lambda active_documents_by_type, scope_documents: {
            "human_intervention_required": False,
            "human_intervention_reason": "",
            "review_tasks": [],
        },
    )

    result = _answer_qa(MULTI_FACT_QUERY, "both")

    assert [source["page_start"] for source in result["sources"]] == [8, 1]


def test_answer_qa_bypasses_llm_when_exact_answer_exists(monkeypatch):
    monkeypatch.setattr(
        "app.services.query_service._gather_scope_context",
        lambda *args, **kwargs: (
            [],
            [
                {
                    "filename": "tender.pdf",
                    "page_start": 8,
                    "page_end": 8,
                    "section": "general",
                    "document_type": "tender",
                    "text": "[TENDER SOURCE]: GLOSSARY LOA As defined in Clause 3.8.4",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service._build_exact_fact_answer",
        lambda *args, **kwargs: (
            "1. LOA definition clause: Clause 3.8.4 [TENDER SOURCE: tender.pdf page 8]",
            [
                {
                    "filename": "tender.pdf",
                    "page_start": 8,
                    "page_end": 8,
                    "section": "general",
                    "document_type": "tender",
                    "text": "GLOSSARY LOA As defined in Clause 3.8.4",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service.llm_text_answer",
        lambda prompt: "The tender glossary provides the clause reference directly.",
    )
    monkeypatch.setattr(
        "app.services.query_service.list_open_review_tasks_for_documents",
        lambda document_ids: [],
    )

    result = _answer_qa(
        MULTI_FACT_QUERY,
        scope="both",
        active_documents_by_type={"tender": [], "resume": []},
        requested_active_document_types=set(),
        restrict_to_active_uploads=False,
    )

    assert result["answer_text"].startswith("Extracted Facts\n1. LOA definition clause: Clause 3.8.4")
    assert "\n\nInterpretation\nThe tender glossary provides the clause reference directly." in result["answer_text"]
    assert result["sources"][0]["filename"] == "tender.pdf"


def test_answer_qa_omits_interpretation_when_model_has_nothing_to_add(monkeypatch):
    monkeypatch.setattr(
        "app.services.query_service._gather_scope_context",
        lambda *args, **kwargs: (
            [],
            [
                {
                    "filename": "tender.pdf",
                    "page_start": 8,
                    "page_end": 8,
                    "section": "general",
                    "document_type": "tender",
                    "text": "[TENDER SOURCE]: GLOSSARY LOA As defined in Clause 3.8.4",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service._build_exact_fact_answer",
        lambda *args, **kwargs: (
            "1. LOA definition clause: Clause 3.8.4 [TENDER SOURCE: tender.pdf page 8]",
            [
                {
                    "filename": "tender.pdf",
                    "page_start": 8,
                    "page_end": 8,
                    "section": "general",
                    "document_type": "tender",
                    "text": "GLOSSARY LOA As defined in Clause 3.8.4",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service.llm_text_answer",
        lambda prompt: "NO_ADDITIONAL_INTERPRETATION",
    )
    monkeypatch.setattr(
        "app.services.query_service.list_open_review_tasks_for_documents",
        lambda document_ids: [],
    )

    result = _answer_qa(
        MULTI_FACT_QUERY,
        scope="both",
        active_documents_by_type={"tender": [], "resume": []},
        requested_active_document_types=set(),
        restrict_to_active_uploads=False,
    )

    assert result["answer_text"] == (
        "Extracted Facts\n"
        "1. LOA definition clause: Clause 3.8.4 [TENDER SOURCE: tender.pdf page 8]"
    )
