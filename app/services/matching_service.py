from app.extraction.resume_extractor import extract_resume_data
from app.extraction.tender_extractor import extract_tender_requirements
from app.graph.matching_graph import build_matching_graph
from app.rag.resume_retriever import get_resume_document_chunks, search_resume_vectors
from app.rag.tender_retriever import get_tender_document_chunks, search_tender_vectors
from app.services.document_repository import (
    get_document_by_id,
    get_document_by_original_filename,
    get_documents_by_ids,
    get_latest_document,
    get_persisted_document_chunks,
    update_document_record,
)
from app.services.document_intent import compare_tender_and_resume
from app.services.evidence_service import build_evidence_map
from app.services.review_service import document_uses_unreviewed_data, preferred_structured_data
from app.services.resume_name_service import repair_resume_structured_data
from app.services.search_service import search_resumes, get_structured_match_plan


matching_graph = build_matching_graph()

SECTION_PRIORITIES = {
    "tender": {
        "eligibility": 0,
        "qualifications": 1,
        "experience": 2,
        "responsibilities": 3,
        "personnel": 4,
        "commercial": 5,
        "general": 6,
    },
    "resume": {
        "skills": 0,
        "experience": 1,
        "projects": 2,
        "summary": 3,
        "education": 4,
        "certifications": 5,
        "general": 6,
    },
}


def _default_tender_requirements():
    return {
        "role": None,
        "domain": None,
        "skills_required": [],
        "preferred_skills": [],
        "experience_required": None,
        "qualifications": [],
        "responsibilities": [],
    }


def _normalize_token(token):
    token = "".join(char for char in str(token).lower() if char.isalnum())
    if token.endswith("s") and len(token) > 4:
        token = token[:-1]
    return token


def _tokenize_phrase(value):
    return {_normalize_token(token) for token in str(value).split() if _normalize_token(token)}


def _phrase_match(a, b):
    if not a or not b:
        return False

    a_str = str(a).strip().lower()
    b_str = str(b).strip().lower()

    if a_str == b_str or a_str in b_str or b_str in a_str:
        return True

    a_tokens = _tokenize_phrase(a_str)
    b_tokens = _tokenize_phrase(b_str)

    if not a_tokens or not b_tokens:
        return False

    overlap = a_tokens & b_tokens
    if not overlap:
        return False

    return len(overlap) >= min(len(a_tokens), len(b_tokens))


def _to_int(value):
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _text_match(a, b):
    if not a or not b:
        return False
    return _phrase_match(a, b)


def _build_verdict(score, experience_match):
    if score >= 80 and experience_match:
        return "Highly Suitable"
    if score >= 50:
        return "Partially Suitable"
    return "Low Suitable"


def _build_resume_search_query(query, tender_data):
    parts = []

    role = tender_data.get("role")
    domain = tender_data.get("domain")
    skills = tender_data.get("skills_required", [])
    preferred_skills = tender_data.get("preferred_skills", [])
    experience = tender_data.get("experience_required")

    if role:
        parts.append(role)

    if domain:
        parts.append(domain)

    if skills:
        parts.extend(skills)

    if preferred_skills:
        parts.extend(preferred_skills[:5])

    if experience is not None:
        parts.append(f"{experience} years experience")

    if not parts:
        parts.append(query)

    return " ".join(parts)


def _chunk_sort_key(item: dict, document_type: str) -> tuple:
    section = item.get("section") or "general"
    section_rank = SECTION_PRIORITIES.get(document_type, {}).get(section, 99)
    page_rank = item.get("page_start") or 0
    chunk_rank = item.get("chunk_id") or 0
    return (section_rank, page_rank, chunk_rank)


def _build_document_text(chunks, fallback_text="", limit=None, document_type="resume"):
    if not chunks:
        return fallback_text

    ordered_chunks = sorted(chunks, key=lambda item: _chunk_sort_key(item, document_type))
    if limit is not None:
        ordered_chunks = ordered_chunks[:limit]

    text = "\n".join(item.get("text", "") for item in ordered_chunks if item.get("text"))
    return text or fallback_text


def _score_candidate(tender_data, resume_data, *, tender_text: str = "", resume_text: str = ""):
    required_skills = tender_data.get("skills_required", [])
    preferred_skills = tender_data.get("preferred_skills", [])
    required_experience = _to_int(tender_data.get("experience_required"))

    candidate_skills = resume_data.get("skills", [])
    candidate_experience = _to_int(resume_data.get("experience"))
    candidate_role = resume_data.get("role")
    candidate_domain = resume_data.get("domain")

    tender_role = tender_data.get("role")
    tender_domain = tender_data.get("domain")

    matched_skills = sorted(
        [
            required_skill
            for required_skill in required_skills
            if any(_phrase_match(required_skill, candidate_skill) for candidate_skill in candidate_skills)
        ]
    )
    missing_skills = sorted(
        [
            required_skill
            for required_skill in required_skills
            if required_skill not in matched_skills
        ]
    )
    matched_preferred_skills = sorted(
        [
            preferred_skill
            for preferred_skill in preferred_skills
            if any(_phrase_match(preferred_skill, candidate_skill) for candidate_skill in candidate_skills)
        ]
    )

    if len(required_skills) == 0:
        skill_score = 0
    else:
        skill_score = (len(matched_skills) / len(required_skills)) * 70

    preferred_score = 0
    if preferred_skills:
        preferred_score = (len(matched_preferred_skills) / len(preferred_skills)) * 10

    role_match = _text_match(tender_role, candidate_role)
    domain_match = _text_match(tender_domain, candidate_domain)

    role_score = 10 if role_match else 0
    domain_score = 10 if domain_match else 0

    if required_experience is not None and candidate_experience is not None:
        experience_match = candidate_experience >= required_experience
        experience_score = 10 if experience_match else 0
    else:
        experience_match = False
        experience_score = 0

    final_score = round(
        min(100, skill_score + preferred_score + role_score + domain_score + experience_score),
        2
    )
    comparison_assessment = compare_tender_and_resume(
        tender_text=tender_text,
        resume_text=resume_text,
        tender_data=tender_data,
        resume_data=resume_data,
    )

    if not comparison_assessment.get("is_valid_match", True):
        role_match = False
        experience_match = False
        final_score = 0.0

    verdict = _build_verdict(final_score, experience_match)

    return {
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_preferred_skills": matched_preferred_skills,
        "required_experience": required_experience,
        "candidate_experience": candidate_experience,
        "experience_match": experience_match,
        "role_match": role_match,
        "domain_match": domain_match,
        "score": final_score,
        "verdict": verdict,
        "eligibility_intent_match": comparison_assessment.get("is_valid_match", True),
        "disqualifiers": comparison_assessment.get("critical_mismatches", []),
        "comparison_mismatches": comparison_assessment.get("mismatches", []),
        "comparison_verdict": comparison_assessment.get("verdict"),
        "tender_document_intent": comparison_assessment.get("tender_intent", {}),
        "resume_document_intent": comparison_assessment.get("resume_intent", {}),
    }


def _resolve_document(document_type: str, match: dict | None = None, fallback_latest: bool = False) -> dict | None:
    document = None

    if match and match.get("document_id") is not None:
        document = get_document_by_id(match["document_id"])

    if document is None and match and match.get("filename"):
        document = get_document_by_original_filename(document_type, match["filename"])

    if document is None and fallback_latest:
        document = get_latest_document(document_type)

    return document


def _get_active_documents(document_type: str, document_ids: list[int] | None = None) -> list[dict]:
    if not document_ids:
        return []

    active_documents = []
    for document in get_documents_by_ids(document_ids):
        if (
            document
            and document.get("document_type") == document_type
            and document.get("status") == "stored"
        ):
            active_documents.append(document)

    return active_documents


def _load_document_chunks(document_type: str, document: dict | None = None, match: dict | None = None, limit: int | None = None) -> list[dict]:
    filename = None
    document_id = None

    if document:
        document_id = document.get("id")
        filename = document.get("original_filename")

    if match:
        filename = filename or match.get("filename")
        document_id = document_id if document_id is not None else match.get("document_id")

    if document_id is not None:
        persisted = get_persisted_document_chunks(document_id, limit=limit)
        if persisted:
            return persisted

    if document_type == "tender":
        return get_tender_document_chunks(filename=filename, document_id=document_id, limit=limit)

    return get_resume_document_chunks(filename=filename, document_id=document_id, limit=limit)


def _extract_or_load_structured_data(document_type: str, document: dict | None, chunks: list[dict], fallback_text: str) -> tuple[dict, dict]:
    if document and document.get("canonical_data_ready") and preferred_structured_data(document):
        return preferred_structured_data(document), document.get("evidence_map", {})

    if document and document.get("structured_data"):
        structured_data = document["structured_data"]
        evidence_map = document.get("evidence_map", {})

        if document_type == "resume":
            repaired_data, source_chunk, changed = repair_resume_structured_data(
                structured_data,
                chunks,
                document=document,
            )
            if changed:
                structured_data = repaired_data
                evidence_map = dict(build_evidence_map(structured_data, chunks))
                if source_chunk:
                    preferred_evidence = build_evidence_map(
                        {
                            "candidate_name": structured_data.get("candidate_name"),
                            "role": structured_data.get("role"),
                        },
                        [source_chunk],
                    )
                    if preferred_evidence.get("candidate_name"):
                        evidence_map["candidate_name"] = preferred_evidence["candidate_name"]
                    if preferred_evidence.get("role"):
                        evidence_map["role"] = preferred_evidence["role"]
                update_document_record(
                    document["id"],
                    structured_data=structured_data,
                    evidence_map=evidence_map,
                )

        return structured_data, evidence_map

    source_text = _build_document_text(
        chunks,
        fallback_text=fallback_text,
        limit=8 if document_type == "tender" else 6,
        document_type=document_type,
    )

    if document_type == "tender":
        structured_data = extract_tender_requirements(source_text)
    else:
        structured_data = extract_resume_data(source_text)

    evidence_map = build_evidence_map(structured_data, chunks)

    if document:
        update_document_record(
            document["id"],
            structured_data=structured_data,
            evidence_map=evidence_map,
        )

    return structured_data, evidence_map


def match_resumes_with_uploaded_tender(
    query: str,
    tender_document_id: int | None = None,
    resume_document_ids: list[int] | None = None,
    restrict_to_active_uploads: bool = False,
):
    tender_scope_requested = tender_document_id is not None
    resume_scope_requested = bool(resume_document_ids)
    active_scope_enabled = (
        restrict_to_active_uploads
        or tender_scope_requested
        or resume_scope_requested
    )
    active_tender_documents = _get_active_documents(
        "tender",
        [tender_document_id] if tender_scope_requested else None,
    )
    active_resume_documents = _get_active_documents("resume", resume_document_ids)

    tender_matches = []
    primary_tender_match = None
    primary_tender_document = active_tender_documents[0] if active_tender_documents else None

    if active_scope_enabled and primary_tender_document is None:
        return {
            "message": "No uploaded tender data found for the current session.",
            "tender_requirements": _default_tender_requirements(),
            "tender_evidence_map": {},
            "tender_review_status": None,
            "tender_canonical_data_ready": False,
            "uses_unreviewed_data": False,
            "matches": [],
            "reasoning_summary": "No tender available for reasoning.",
        }

    if active_scope_enabled and not active_resume_documents:
        return {
            "message": "No uploaded resume data found for the current session.",
            "tender_requirements": _default_tender_requirements(),
            "tender_evidence_map": {},
            "tender_review_status": None,
            "tender_canonical_data_ready": False,
            "uses_unreviewed_data": False,
            "matches": [],
            "reasoning_summary": "No resume matches were available for reasoning.",
        }

    if primary_tender_document is None:
        tender_matches = search_tender_vectors(query, top_k=5)
        primary_tender_match = tender_matches[0] if tender_matches else None
        primary_tender_document = _resolve_document("tender", primary_tender_match, fallback_latest=True)

    if primary_tender_document is None and not tender_matches:
        return {
            "message": "No uploaded tender data found. Please upload a tender PDF first.",
            "tender_requirements": _default_tender_requirements(),
            "tender_evidence_map": {},
            "tender_review_status": None,
            "tender_canonical_data_ready": False,
            "uses_unreviewed_data": False,
            "matches": [],
            "reasoning_summary": "No tender available for reasoning.",
        }

    tender_document_chunks = _load_document_chunks(
        "tender",
        document=primary_tender_document,
        match=primary_tender_match,
        limit=8,
    )
    tender_fallback_text = "\n".join(item.get("text", "") for item in tender_matches)
    tender_data, tender_evidence_map = _extract_or_load_structured_data(
        "tender",
        primary_tender_document,
        tender_document_chunks,
        tender_fallback_text,
    )
    tender_context_text = _build_document_text(
        tender_document_chunks,
        fallback_text=tender_fallback_text,
        limit=8,
        document_type="tender",
    )
    tender_uses_unreviewed = document_uses_unreviewed_data(primary_tender_document)

    resume_search_query = _build_resume_search_query(query, tender_data)
    if active_resume_documents:
        resume_matches = [
            {
                "document_id": document.get("id"),
                "filename": document.get("original_filename"),
                "text": "",
            }
            for document in active_resume_documents
        ]
    else:
        search_result = search_resumes(resume_search_query, page=1, page_size=10)
        resume_matches = [
            {
                "document_id": item.get("document_id"),
                "filename": None,
                "text": item.get("summary_text", ""),
                "score": item.get("score"),
            }
            for item in search_result.get("results", [])
        ]
        if not resume_matches:
            resume_matches = search_resume_vectors(resume_search_query, top_k=10)

    if not resume_matches:
        return {
            "message": "No resume matches found. Please upload resume PDFs first.",
            "tender_requirements": tender_data,
            "tender_evidence_map": tender_evidence_map,
            "tender_review_status": (primary_tender_document or {}).get("review_status"),
            "tender_canonical_data_ready": (primary_tender_document or {}).get("canonical_data_ready", False),
            "uses_unreviewed_data": tender_uses_unreviewed,
            "matches": [],
            "reasoning_summary": "No resume matches were available for reasoning.",
        }

    results = []
    seen_candidates = set()
    uses_unreviewed_data = tender_uses_unreviewed

    for match in resume_matches:
        resume_document = _resolve_document("resume", match, fallback_latest=False)
        candidate_key = (
            (resume_document or {}).get("id")
            or match.get("document_id")
            or match.get("filename")
        )

        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)

        resume_chunks = _load_document_chunks("resume", document=resume_document, match=match, limit=6)
        resume_fallback_text = match.get("text", "")
        resume_data, resume_evidence_map = _extract_or_load_structured_data(
            "resume",
            resume_document,
            resume_chunks,
            resume_fallback_text,
        )
        resume_analysis_text = _build_document_text(
            resume_chunks,
            fallback_text=resume_fallback_text,
            limit=6,
            document_type="resume",
        )

        scored = _score_candidate(
            tender_data,
            resume_data,
            tender_text=tender_context_text,
            resume_text=resume_analysis_text,
        )
        resume_context = _build_document_text(
            resume_chunks,
            fallback_text=resume_fallback_text,
            limit=4,
            document_type="resume",
        )

        results.append(
            {
                "document_id": (resume_document or {}).get("id") or match.get("document_id"),
                "filename": (resume_document or {}).get("original_filename") or match.get("filename", "unknown.pdf"),
                "resume_excerpt": resume_context[:300],
                "candidate_name": resume_data.get("candidate_name"),
                "candidate_role": resume_data.get("role"),
                "candidate_domain": resume_data.get("domain"),
                "candidate_skills": resume_data.get("skills", []),
                "candidate_qualifications": resume_data.get("qualifications", []),
                "candidate_projects": resume_data.get("projects", []),
                "candidate_evidence_map": resume_evidence_map,
                "review_status": (resume_document or {}).get("review_status"),
                "canonical_data_ready": (resume_document or {}).get("canonical_data_ready", False),
                "uses_unreviewed_data": document_uses_unreviewed_data(resume_document),
                **scored,
            }
        )
        uses_unreviewed_data = uses_unreviewed_data or document_uses_unreviewed_data(resume_document)

    results.sort(key=lambda item: (item["score"], item["experience_match"]), reverse=True)

    graph_result = matching_graph.invoke(
        {
            "query": query,
            "tender_requirements": tender_data,
            "matches": results,
        }
    )

    match_plan = get_structured_match_plan(tender_data)

    return {
        "message": "Matching completed using uploaded tender.",
        "tender_requirements": tender_data,
        "structured_matching_plan": match_plan["structured_requirements"],
        "matching_sql_query": match_plan["sql_query"],
        "matching_explanation": match_plan["short_explanation"],
        "tender_evidence_map": tender_evidence_map,
        "tender_review_status": (primary_tender_document or {}).get("review_status"),
        "tender_canonical_data_ready": (primary_tender_document or {}).get("canonical_data_ready", False),
        "uses_unreviewed_data": uses_unreviewed_data,
        "matches": graph_result.get("matches", results),
        "reasoning_summary": graph_result.get("reasoning_summary", ""),
    }
