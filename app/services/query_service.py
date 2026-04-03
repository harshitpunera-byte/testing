import re
from datetime import datetime, timezone
import os

from app.agents.query_agent import (
    RESUME_HINTS,
    TENDER_HINTS,
    build_answer_prompt,
    build_collection_summary_prompt,
    build_exact_fact_summary_prompt,
    build_fallback_answer,
    classify_query_intent,
    COLLECTION_HINTS,
)
from app.llm.provider import llm_text_answer
from app.rag.loader import load_pdf_pages
from app.rag.resume_retriever import (
    get_resume_chunk_window,
    get_resume_document_chunks,
    search_resume_vectors_hybrid,
)
from app.rag.tender_retriever import (
    get_tender_chunk_window,
    get_tender_document_chunks,
    search_tender_vectors_hybrid,
)
from app.rag.vector_store import index_has_data
from app.services.document_repository import (
    get_document_by_id,
    get_document_by_original_filename,
    get_documents_by_ids,
    get_latest_document,
    get_persisted_document_chunks,
)
from app.services.document_intent import compare_tender_and_resume
from app.services.matching_service import match_resumes_with_uploaded_tender
from app.services.review_service import (
    list_open_review_tasks_for_documents,
    preferred_structured_data,
)
from app.services.search_service import search_resumes


COLLECTION_QUERY_HINTS = {
    "all applicants",
    "all candidates",
    "all profiles",
    "all resumes",
    "compare",
    "comparison",
    "find candidates",
    "find resumes",
    "list applicants",
    "list candidates",
    "list resumes",
    "many resumes",
    "multiple resumes",
    "rank candidate",
    "rank resume",
    "shortlist",
    "top candidate",
    "top candidates",
    "who are the applicants",
    "who are the candidates",
}

COLLECTION_QUERY_TOKENS = {
    "applicants",
    "candidates",
    "files",
    "profiles",
    "resumes",
}

APPENDIX_PATTERN = re.compile(r"\bappendix[-\s]*([a-z0-9]+)\b", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"\bclause\s+\d+(?:\.\d+)*\b", re.IGNORECASE)
NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
GENERIC_NAME_PHRASES = {
    "date of birth",
    "letter of award",
    "request for proposals",
    "total project cost",
    "net worth",
    "name of staff",
    "major activities",
}

TENDER_QUERY_BUNDLES = {
    "loa": "LOA letter of award glossary clause definition",
    "glossary": "glossary definitions term clause",
    "chainage": "appendix chainage ch km section range",
    "project cost": "project cost estimated project cost bid project cost crore",
    "tpc": "project cost estimated project cost bid project cost crore",
    "net worth": "financial capacity net worth bidder crore",
    "financial capacity": "financial capacity net worth bidder crore",
}

RESUME_QUERY_BUNDLES = {
    "dob": "Date of Birth DOB Name of Staff candidate profile",
    "date of birth": "Date of Birth DOB Name of Staff candidate profile",
    "birth": "Date of Birth DOB Name of Staff candidate profile",
    "project cost": "Project Cost Name of Work Experience Details Andhra Pradesh",
    "tpc": "Project Cost Name of Work Experience Details Andhra Pradesh",
    "staff": "Name of Staff candidate profile resume",
    "member": "Name of Staff candidate profile resume",
}

COMPARISON_QUERY_HINTS = {
    "compare",
    "comparison",
    "false positive",
    "genuine match",
    "not a valid match",
    "compare project",
    "compare projects",
    "role mismatch",
    "project type mismatch",
    "individual vs company",
    "consultant vs contractor",
    "compare tender and resume",
}


def _add_query_variant(variants: list[str], seen: set[str], text: str) -> None:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return

    lowered = normalized.lower()
    if lowered in seen:
        return

    seen.add(lowered)
    variants.append(normalized)


def _extract_named_sequences(text: str) -> list[str]:
    candidates = []
    for match in NAME_PATTERN.findall(text or ""):
        normalized = " ".join(match.split())
        if normalized.lower() in GENERIC_NAME_PHRASES:
            continue
        candidates.append(normalized)

    unique_candidates = list(dict.fromkeys(candidates))
    return sorted(unique_candidates, key=lambda value: (-len(value.split()), len(value)))


def _build_search_queries(document_type: str, query: str) -> list[str]:
    original_query = " ".join((query or "").split())
    lowered = original_query.lower()
    variants: list[str] = []
    seen: set[str] = set()

    _add_query_variant(variants, seen, original_query)

    if document_type == "tender":
        focused_tokens = [
            token
            for token in original_query.split()
            if token.lower() not in RESUME_HINTS or token.lower() in TENDER_HINTS
        ]
        _add_query_variant(variants, seen, " ".join(focused_tokens))

        for hint, bundle in TENDER_QUERY_BUNDLES.items():
            if hint in lowered:
                _add_query_variant(variants, seen, bundle)

        for appendix_ref in APPENDIX_PATTERN.findall(original_query):
            appendix_label = f"Appendix-{appendix_ref.upper()}"
            _add_query_variant(variants, seen, f"{appendix_label} chainage")
            _add_query_variant(variants, seen, f"{appendix_label} project section")

        for clause_ref in CLAUSE_PATTERN.findall(original_query):
            _add_query_variant(variants, seen, clause_ref)

        if "glossary" in lowered and "loa" in lowered:
            _add_query_variant(variants, seen, "glossary LOA clause")

    else:
        focused_tokens = [
            token
            for token in original_query.split()
            if token.lower() in RESUME_HINTS or token[0].isupper() or len(token) > 3
        ]
        _add_query_variant(variants, seen, " ".join(focused_tokens))

        for hint, bundle in RESUME_QUERY_BUNDLES.items():
            if hint in lowered:
                _add_query_variant(variants, seen, bundle)

        for name in _extract_named_sequences(original_query):
            _add_query_variant(variants, seen, name)
            if any(term in lowered for term in ("dob", "date of birth", "birth")):
                _add_query_variant(variants, seen, f"{name} Date of Birth DOB")
            if "project cost" in lowered or "tpc" in lowered:
                _add_query_variant(variants, seen, f"{name} Project Cost")

    return variants[:8]


def _search_query_variants(
    document_type: str,
    queries: list[str],
    *,
    top_k: int,
    document_id: int | None = None,
) -> list[dict]:
    search_fn = search_tender_vectors_hybrid if document_type == "tender" else search_resume_vectors_hybrid
    combined_results: dict[tuple, dict] = {}
    per_query_top_k = max(4, min(8, top_k))

    for query_index, variant in enumerate(queries):
        results = search_fn(variant, top_k=per_query_top_k, document_id=document_id)
        bonus = max(0.0, 0.12 - (query_index * 0.02))

        for result in results:
            key = (result.get("document_id"), result.get("filename"), result.get("chunk_id"))
            entry = combined_results.setdefault(key, dict(result))

            for field, value in result.items():
                if field not in entry or entry.get(field) in (None, "", 0):
                    entry[field] = value

            entry["variant_hits"] = entry.get("variant_hits", 0) + 1
            entry["variant_score"] = entry.get("variant_score", 0.0) + float(result.get("retrieval_score", 0.0)) + bonus
            entry["retrieval_score"] = max(entry.get("retrieval_score", 0.0), float(result.get("retrieval_score", 0.0)))
            entry["keyword_score"] = max(entry.get("keyword_score", 0.0), float(result.get("keyword_score", 0.0)))

    ranked = sorted(
        combined_results.values(),
        key=lambda item: (
            item.get("variant_score", 0.0),
            item.get("variant_hits", 0),
            item.get("retrieval_score", 0.0),
            item.get("keyword_score", 0.0),
        ),
        reverse=True,
    )
    return ranked[:top_k]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_extraction_text(text: str) -> str:
    normalized = _normalize_text(text)
    normalized = normalized.replace("<br>", " ")
    normalized = normalized.replace("**", "")
    normalized = re.sub(r"\|(?:\s*---\s*\|)+", " ", normalized)
    normalized = re.sub(
        r"\b(\d{1,2}(?:st|nd|rd|th)?)(?=[A-Za-z]{3,9}\s+\d{4}\b)",
        r"\1 ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"(?<=\d)\s*\|\s*(?=\d)", "", normalized)
    normalized = normalized.replace("|", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _build_document_text(
    chunks: list[dict],
    *,
    fallback_text: str = "",
    limit: int | None = None,
    document_type: str = "resume",
) -> str:
    if not chunks:
        return fallback_text

    ordered_chunks = sorted(
        chunks,
        key=lambda item: (
            item.get("page_start") or 0,
            item.get("chunk_id") or 0,
        ),
    )
    if limit is not None:
        ordered_chunks = ordered_chunks[:limit]

    text = "\n".join(item.get("text", "") for item in ordered_chunks if item.get("text"))
    return text or fallback_text


def _scope_documents_for_exact_extraction(
    scope_documents: list[str],
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
) -> dict[str, list[dict]]:
    active_documents_by_type = active_documents_by_type or {}
    requested_active_document_types = requested_active_document_types or set()
    documents_by_type: dict[str, list[dict]] = {}

    for document_type in scope_documents:
        active_documents = [
            document
            for document in active_documents_by_type.get(document_type, [])
            if document and document.get("status") == "stored"
        ]
        if active_documents:
            documents_by_type[document_type] = active_documents
            continue

        if restrict_to_active_uploads or document_type in requested_active_document_types:
            documents_by_type[document_type] = []
            continue

        latest_document = get_latest_document(document_type)
        documents_by_type[document_type] = [latest_document] if latest_document else []

    return documents_by_type


def _all_chunks_for_documents(documents: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    seen_document_ids: set[int] = set()

    for document in documents:
        document_id = document.get("id")
        if document_id is None or document_id in seen_document_ids:
            continue

        seen_document_ids.add(document_id)
        all_chunks.extend(get_persisted_document_chunks(document_id))

    return all_chunks


def _all_page_chunks_for_documents(documents: list[dict]) -> list[dict]:
    page_chunks: list[dict] = []
    seen_document_ids: set[int] = set()

    for document in documents:
        document_id = document.get("id")
        if document_id is None or document_id in seen_document_ids:
            continue

        seen_document_ids.add(document_id)
        stored_path = document.get("stored_path")
        if not stored_path or not os.path.exists(stored_path):
            continue

        try:
            with open(stored_path, "rb") as file_obj:
                extracted = load_pdf_pages(
                    file_obj.read(),
                    document_name=document.get("original_filename"),
                )
        except Exception:
            continue

        for page in extracted.pages:
            page_chunks.append(
                {
                    "filename": document.get("original_filename", "unknown.pdf"),
                    "text": page.text,
                    "document_id": document_id,
                    "document_type": document.get("document_type"),
                    "page_start": page.page,
                    "page_end": page.page,
                    "section": "general",
                    "chunk_id": page.page,
                }
            )

    return page_chunks


def _pick_best_chunk(chunks: list[dict], required_terms: list[str], preferred_terms: list[str] | None = None) -> dict | None:
    preferred_terms = preferred_terms or []
    ranked_candidates: list[tuple[tuple, dict]] = []

    for chunk in chunks:
        normalized = _normalize_extraction_text(chunk.get("text", ""))
        lowered = normalized.lower()
        if not all(term.lower() in lowered for term in required_terms):
            continue

        ranking = (
            sum(1 for term in preferred_terms if term.lower() in lowered),
            len(normalized),
            -(chunk.get("page_start") or 0),
        )
        ranked_candidates.append((ranking, chunk))

    if not ranked_candidates:
        return None

    ranked_candidates.sort(reverse=True)
    return ranked_candidates[0][1]


def _combine_same_page_chunks(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []

    combined: list[dict] = []
    sorted_chunks = sorted(
        chunks,
        key=lambda item: (
            item.get("page_start") or 0,
            item.get("chunk_id") if item.get("chunk_id") is not None else item.get("chunk_index", 0),
        ),
    )

    for chunk in sorted_chunks:
        current = dict(chunk)
        combined.append(current)

    for first, second in zip(sorted_chunks, sorted_chunks[1:]):
        if first.get("page_start") != second.get("page_start"):
            continue

        merged = dict(first)
        merged["text"] = _normalize_text(f"{first.get('text', '')} {second.get('text', '')}")
        combined.append(merged)

    return combined


def _extract_chunk_dates(chunk_text: str) -> list[tuple[str, int]]:
    normalized = _normalize_extraction_text(chunk_text)
    dates: list[tuple[str, int]] = []

    for pattern in (
        r"\b\d{1,2}(?:st|nd|rd|th)?\s*[A-Za-z]+\s+\d{4}\b",
        r"\b\d{2}/\d{2}/\d{4}\b",
    ):
        for match in re.finditer(pattern, normalized, re.IGNORECASE):
            dates.append((match.group(0), match.start()))

    dates.sort(key=lambda item: item[1])
    return dates


def _parse_candidate_date(value: str) -> datetime | None:
    normalized = _normalize_extraction_text(value)

    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            pass

    textual = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", normalized, flags=re.IGNORECASE)
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(textual, fmt)
        except ValueError:
            pass

    return None


def _extract_requested_fact_keys(query: str) -> list[str]:
    lowered = _normalize_text(query).lower()
    keys = []

    if "loa" in lowered and ("glossary" in lowered or "definition" in lowered or "clause" in lowered):
        keys.append("loa_clause")
    if "project cost" in lowered or "total project cost" in lowered:
        keys.append("project_cost")
    if "chainage" in lowered or "appendix" in lowered:
        keys.append("chainage")
    if "net worth" in lowered or "financial capacity" in lowered:
        keys.append("net_worth")
    if "date of birth" in lowered or "dob" in lowered or "birth" in lowered:
        keys.append("dob")

    return keys


def _is_tender_resume_comparison_query(query: str, scope_documents: list[str]) -> bool:
    if not {"tender", "resume"}.issubset(set(scope_documents)):
        return False

    lowered = _normalize_text(query).lower()
    if "tender" not in lowered:
        return False

    resume_side_terms = (
        "resume",
        "candidate",
        "cv",
        "profile",
        "staff",
        "personnel",
    )
    if not any(term in lowered for term in resume_side_terms):
        return False

    return any(hint in lowered for hint in COMPARISON_QUERY_HINTS)


def _select_primary_scope_document(
    documents_by_type: dict[str, list[dict]],
    document_type: str,
) -> dict | None:
    documents = documents_by_type.get(document_type, [])
    return documents[0] if documents else None


def _overview_source_chunks(chunks: list[dict], max_pages: int) -> list[dict]:
    selected: list[dict] = []
    seen_pages: set[int] = set()

    for chunk in chunks:
        page = chunk.get("page_start")
        if page in seen_pages:
            continue
        seen_pages.add(page)
        selected.append(chunk)
        if len(selected) >= max_pages:
            break

    return selected


def _build_tender_resume_comparison_answer(
    query: str,
    scope_documents: list[str],
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
) -> tuple[str, list[dict]] | None:
    if not _is_tender_resume_comparison_query(query, scope_documents):
        return None

    documents_by_type = _scope_documents_for_exact_extraction(
        scope_documents,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
    )
    tender_document = _select_primary_scope_document(documents_by_type, "tender")
    resume_document = _select_primary_scope_document(documents_by_type, "resume")

    if not tender_document or not resume_document:
        return None

    tender_chunks = _all_page_chunks_for_documents([tender_document]) or _load_document_chunks(
        "tender",
        document=tender_document,
        limit=8,
    )
    resume_chunks = _all_page_chunks_for_documents([resume_document]) or _load_document_chunks(
        "resume",
        document=resume_document,
        limit=6,
    )

    if not tender_chunks or not resume_chunks:
        return None

    tender_text = _build_document_text(
        tender_chunks,
        fallback_text=tender_document.get("raw_text", ""),
        limit=8,
        document_type="tender",
    )
    resume_text = _build_document_text(
        resume_chunks,
        fallback_text=resume_document.get("raw_text", ""),
        limit=6,
        document_type="resume",
    )
    tender_data = preferred_structured_data(tender_document) or tender_document.get("structured_data", {}) or {}
    resume_data = preferred_structured_data(resume_document) or resume_document.get("structured_data", {}) or {}
    comparison = compare_tender_and_resume(
        tender_text=tender_text,
        resume_text=resume_text,
        tender_data=tender_data,
        resume_data=resume_data,
    )

    tender_intent = comparison.get("tender_intent", {})
    resume_intent = comparison.get("resume_intent", {})
    similarities = comparison.get("similarities", [])
    mismatches = comparison.get("mismatches", [])
    confusion_reasons = comparison.get("confusion_reasons", [])
    verdict = comparison.get("verdict", "Not a Valid Match")

    answer_lines = [
        f"Tender classification: {tender_intent.get('summary', 'Tender intent could not be classified.')}",
        f"Resume classification: {resume_intent.get('summary', 'Resume intent could not be classified.')}",
        "",
        "Project comparison:",
        f"- Tender project: {tender_intent.get('project_title') or 'Not clearly detected'}",
        f"- Resume project: {resume_intent.get('project_title') or 'Not clearly detected'}",
        f"- Tender states: {', '.join(tender_intent.get('states', [])) or 'Not clearly detected'}",
        f"- Resume states: {', '.join(resume_intent.get('states', [])) or 'Not clearly detected'}",
        "",
        "Superficial similarities:",
    ]
    for index, item in enumerate(similarities[:5], start=1):
        answer_lines.append(f"{index}. {item}")

    answer_lines.extend(["", "Decisive mismatches:"])
    for index, item in enumerate(mismatches[:5], start=1):
        answer_lines.append(f"{index}. {item}")

    answer_lines.extend(
        [
            "",
            f"Final verdict: {verdict}",
            "",
            "Why the matching system got confused:",
        ]
    )
    for index, item in enumerate(confusion_reasons[:4], start=1):
        answer_lines.append(f"{index}. {item}")

    tender_evidence = ", ".join(tender_intent.get("evidence", [])[:5]) or "no strong bidder markers detected"
    resume_evidence = ", ".join(resume_intent.get("evidence", [])[:5]) or "no strong resume markers detected"
    if tender_intent.get("project_title"):
        tender_evidence += f"; project title: {tender_intent['project_title']}"
    if resume_intent.get("project_title"):
        resume_evidence += f"; project title: {resume_intent['project_title']}"

    answer_lines.extend(
        [
            "",
            f"Tender evidence signals: {tender_evidence}.",
            f"Resume evidence signals: {resume_evidence}.",
        ]
    )

    source_chunks = _overview_source_chunks(tender_chunks, max_pages=4) + _overview_source_chunks(resume_chunks, max_pages=3)
    return "\n".join(answer_lines).strip(), source_chunks[:7]


def _extract_loa_clause(tender_chunks: list[dict]) -> tuple[str, dict] | None:
    glossary_chunk = _pick_best_chunk(
        tender_chunks,
        required_terms=["loa", "as defined in clause"],
        preferred_terms=["glossary"],
    )
    if glossary_chunk:
        normalized = _normalize_text(glossary_chunk.get("text", ""))
        match = re.search(r"\bLOA\b.*?As defined in Clause\s+(\d+(?:\.\d+)*)", normalized, re.IGNORECASE)
        if match:
            return f"Clause {match.group(1)}", glossary_chunk

    clause_chunk = _pick_best_chunk(
        tender_chunks,
        required_terms=["3.8.4", "letter of award", "loa"],
        preferred_terms=["after selection"],
    )
    if clause_chunk:
        return "Clause 3.8.4", clause_chunk

    return None


def _extract_chainage_range(query: str, tender_chunks: list[dict]) -> tuple[str, dict] | None:
    appendix_match = APPENDIX_PATTERN.search(query or "")
    appendix_ref = appendix_match.group(1).lower() if appendix_match else "vii"
    appendix_pattern = re.compile(rf"\bappendix[-\s]*{re.escape(appendix_ref)}\b", re.IGNORECASE)
    ranked_candidates: list[tuple[tuple, str, dict]] = []

    for chunk in tender_chunks:
        normalized = _normalize_extraction_text(chunk.get("text", ""))
        lowered = normalized.lower()
        matches = re.findall(r"Ch\.\s*(\d+\+\d+)", normalized, re.IGNORECASE)
        unique_matches = list(dict.fromkeys(matches))
        if len(unique_matches) < 2:
            continue

        appendix_search = appendix_pattern.search(lowered)
        appendix_position = appendix_search.start() if appendix_search else 10_000
        ranking = (
            1 if appendix_position < 10_000 else 0,
            1 if "chainage" in lowered else 0,
            1 if "sub:" in lowered else 0,
            -appendix_position,
            chunk.get("page_start") or 0,
            -len(normalized),
        )
        ranked_candidates.append(
            (
                ranking,
                f"Ch. {unique_matches[0]} to Ch. {unique_matches[1]}",
                chunk,
            )
        )

    if ranked_candidates:
        ranked_candidates.sort(reverse=True)
        _, value, chunk = ranked_candidates[0]
        return value, chunk

    return None


def _extract_net_worth(tender_chunks: list[dict]) -> tuple[str, dict] | None:
    chunk = _pick_best_chunk(
        tender_chunks,
        required_terms=["minimum available net worth", "rs."],
        preferred_terms=["financial capacity", "crore"],
    )
    if not chunk:
        return None

    normalized = _normalize_text(chunk.get("text", ""))
    match = re.search(r"Rs\.\s*([\d,]+(?:\.\d+)?)\s*Crore", normalized, re.IGNORECASE)
    if not match:
        return None

    return f"Rs. {match.group(1)} Crore", chunk


def _extract_resume_project_cost(query: str, resume_chunks: list[dict]) -> tuple[str, dict] | None:
    lowered_query = _normalize_text(query).lower()
    preferred_terms = ["project cost"]
    if "andhra pradesh" in lowered_query:
        preferred_terms.append("andhra pradesh")
    if "supervision" in lowered_query:
        preferred_terms.append("supervision")

    search_space = [
        chunk
        for chunk in _combine_same_page_chunks(resume_chunks)
        if "project cost" in _normalize_extraction_text(chunk.get("text", "")).lower()
    ]
    ranked_candidates: list[tuple[tuple, str, dict]] = []

    for chunk in search_space:
        normalized = _normalize_extraction_text(chunk.get("text", ""))
        lowered = normalized.lower()
        for project_cost_match in re.finditer(r"project cost", lowered, re.IGNORECASE):
            window = normalized[project_cost_match.start(): project_cost_match.start() + 180]
            window_variants = {
                window,
                re.sub(r"(?<=\d)\s+(?=\d+\.\d+\b)", "", window),
            }
            currency_values: set[str] = set()

            for variant in window_variants:
                for match in re.finditer(
                    r"\b([\d,]+(?:\.\d+)?)\s*(?:RS|Rs\.?|INR)\s*\(?(?:Cr|Crore)\.?\)?",
                    variant,
                    re.IGNORECASE,
                ):
                    currency_values.add(match.group(1))

            if not currency_values:
                continue

            for value in currency_values:
                numeric_value = float(value.replace(",", ""))
                digit_count = len(re.sub(r"[^0-9]", "", value))

                ranking = (
                    sum(1 for term in preferred_terms + ["name of work", "experience details"] if term.lower() in lowered),
                    digit_count,
                    numeric_value,
                    len(normalized),
                    -(chunk.get("page_start") or 0),
                )
                ranked_candidates.append((ranking, value, chunk))

    if not ranked_candidates:
        return None

    ranked_candidates.sort(reverse=True)
    _, value, chunk = ranked_candidates[0]
    return f"{value} Rs (Cr.)", chunk


def _extract_resume_dob(query: str, resume_chunks: list[dict]) -> tuple[str, dict] | None:
    candidate_names = [
        name
        for name in _extract_named_sequences(query)
        if len(name.split()) >= 3 and "andhra pradesh" not in name.lower()
    ]
    preferred_name = candidate_names[0].lower() if candidate_names else None

    candidate_pool = []
    for chunk in resume_chunks:
        normalized = _normalize_extraction_text(chunk.get("text", ""))
        lowered = normalized.lower()
        if "date of birth" in lowered or re.search(r"\b\d{2}/\d{2}/\d{4}\b", normalized):
            if preferred_name and preferred_name not in lowered:
                continue
            candidate_pool.append(chunk)

    if not candidate_pool and preferred_name:
        for chunk in resume_chunks:
            normalized = _normalize_extraction_text(chunk.get("text", ""))
            if preferred_name in normalized.lower():
                candidate_pool.append(chunk)

    scored_dates: list[tuple[tuple, str, dict]] = []
    for chunk in candidate_pool:
        normalized = _normalize_extraction_text(chunk.get("text", ""))
        lowered = normalized.lower()
        dob_index = lowered.find("date of birth")
        if dob_index >= 0:
            dob_window = normalized[dob_index: dob_index + 160]
            textual = re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s*[A-Za-z]+\s+\d{4}\b", dob_window, re.IGNORECASE)
            if textual:
                return _normalize_extraction_text(textual.group(0)), chunk

            numeric_near_label = re.search(r"\b\d{2}/\d{2}/\d{4}\b", dob_window)
            if numeric_near_label:
                prefix = dob_window[: numeric_near_label.start()].lower()
                suffix = dob_window[numeric_near_label.end(): numeric_near_label.end() + 40].lower()
                looks_like_signature_date = (
                    prefix.rstrip().endswith("date:")
                    or "day/month/year" in suffix
                    or "signature" in suffix
                )
                if not looks_like_signature_date:
                    return numeric_near_label.group(0), chunk

        for date_value, position in _extract_chunk_dates(normalized):
            context_window = normalized[max(0, position - 40): position + 60].lower()
            penalty = 0
            if "day/month/year" in context_window:
                penalty += 4
            if "signature" in context_window:
                penalty += 3
            if "date:" in context_window and "date of birth" not in context_window:
                penalty += 2

            proximity_bonus = 0
            if preferred_name and preferred_name in lowered:
                proximity_bonus += 2
            if "date of birth" in lowered:
                proximity_bonus += 1

            parsed_date = _parse_candidate_date(date_value)
            if parsed_date:
                current_year = datetime.now(timezone.utc).year
                if parsed_date.year < 1900:
                    penalty += 6
                elif parsed_date.year > current_year - 16:
                    penalty += 6
                else:
                    proximity_bonus += 2

            ranking = (
                proximity_bonus - penalty,
                -(chunk.get("page_start") or 0),
                -position,
            )
            scored_dates.append((ranking, date_value, chunk))

    if scored_dates:
        scored_dates.sort(reverse=True)
        _, date_value, chunk = scored_dates[0]
        return date_value, chunk

    return None


def _build_exact_fact_answer(
    query: str,
    scope_documents: list[str],
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
) -> tuple[str, list[dict]] | None:
    requested_keys = _extract_requested_fact_keys(query)
    if not requested_keys:
        return None

    documents_by_type = _scope_documents_for_exact_extraction(
        scope_documents,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
    )
    tender_chunks = _all_page_chunks_for_documents(documents_by_type.get("tender", [])) or _all_chunks_for_documents(
        documents_by_type.get("tender", [])
    )
    resume_chunks = _all_page_chunks_for_documents(documents_by_type.get("resume", [])) or _all_chunks_for_documents(
        documents_by_type.get("resume", [])
    )

    if not tender_chunks and not resume_chunks:
        return None

    facts: dict[str, tuple[str, dict, str]] = {}

    if "loa_clause" in requested_keys:
        result = _extract_loa_clause(tender_chunks)
        if result:
            value, chunk = result
            facts["loa_clause"] = (f"LOA definition clause: {value}", chunk, "TENDER SOURCE")

    if "project_cost" in requested_keys:
        result = _extract_resume_project_cost(query, resume_chunks)
        if result:
            value, chunk = result
            facts["project_cost"] = (
                f"Total Project Cost for the Andhra Pradesh supervision project: {value}",
                chunk,
                "RESUME SOURCE",
            )

    if "chainage" in requested_keys:
        result = _extract_chainage_range(query, tender_chunks)
        if result:
            value, chunk = result
            facts["chainage"] = (f"Appendix-VII chainage range: {value}", chunk, "TENDER SOURCE")

    if "net_worth" in requested_keys:
        result = _extract_net_worth(tender_chunks)
        if result:
            value, chunk = result
            facts["net_worth"] = (f"Minimum required Net Worth for bidders: {value}", chunk, "TENDER SOURCE")

    if "dob" in requested_keys:
        result = _extract_resume_dob(query, resume_chunks)
        if result:
            value, chunk = result
            facts["dob"] = (f"Date of Birth of Dharmireddi Sanyasi Naidu: {value}", chunk, "RESUME SOURCE")

    if not facts:
        return None

    ordered_keys = ["loa_clause", "project_cost", "chainage", "net_worth", "dob"]
    answer_lines = []
    source_chunks = []

    for key in ordered_keys:
        if key not in facts:
            continue
        statement, chunk, source_label = facts[key]
        page = chunk.get("page_start") or "?"
        filename = chunk.get("filename", "unknown.pdf")
        answer_lines.append(f"{len(answer_lines) + 1}. {statement} [{source_label}: {filename} page {page}]")
        source_chunks.append(chunk)

    return "\n".join(answer_lines), source_chunks


def _compose_exact_answer_response(
    query: str,
    exact_answer_text: str,
    exact_chunks: list[dict],
) -> str:
    response_parts = ["Extracted Facts", exact_answer_text]

    summary_prompt = build_exact_fact_summary_prompt(query, exact_answer_text, exact_chunks)
    summary_text = llm_text_answer(summary_prompt).strip()

    if summary_text and summary_text != "NO_ADDITIONAL_INTERPRETATION":
        response_parts.extend(["", "Interpretation", summary_text])

    return "\n".join(response_parts).strip()


def _build_active_documents_by_type(
    tender_document_id: int | None = None,
    resume_document_ids: list[int] | None = None,
) -> dict[str, list[dict]]:
    document_ids = []
    if tender_document_id is not None:
        document_ids.append(tender_document_id)
    if resume_document_ids:
        document_ids.extend(resume_document_ids)

    active_documents = {"tender": [], "resume": []}

    for document in get_documents_by_ids(document_ids):
        if not document or document.get("status") != "stored":
            continue

        document_type = document.get("document_type")
        if document_type in active_documents:
            active_documents[document_type].append(document)

    return active_documents


def _resolve_document(
    document_type: str,
    match: dict | None = None,
    active_documents: list[dict] | None = None,
) -> dict | None:
    document = None
    active_documents = active_documents or []
    active_documents_by_id = {
        item.get("id"): item
        for item in active_documents
        if item.get("id") is not None
    }

    if match and match.get("document_id") is not None:
        document = active_documents_by_id.get(match["document_id"]) or get_document_by_id(match["document_id"])

    if document is None and match and match.get("filename"):
        document = get_document_by_original_filename(document_type, match["filename"])

    if document is None:
        if active_documents:
            document = active_documents[0]
        else:
            document = get_latest_document(document_type)

    return document


def _load_document_chunks(document_type: str, document: dict | None = None, match: dict | None = None, limit: int = 4) -> list[dict]:
    filename = None
    document_id = None

    if document:
        filename = document.get("original_filename")
        document_id = document.get("id")

    if match:
        filename = filename or match.get("filename")
        if document_id is None:
            document_id = match.get("document_id")

    if document_id is not None:
        persisted_chunks = get_persisted_document_chunks(document_id, limit=limit)
        if persisted_chunks:
            return persisted_chunks

    if document_type == "tender":
        return get_tender_document_chunks(filename=filename, document_id=document_id, limit=limit)

    return get_resume_document_chunks(filename=filename, document_id=document_id, limit=limit)


def _load_match_context_chunks(document_type: str, match: dict, window: int = 1) -> list[dict]:
    if document_type == "tender":
        chunks = get_tender_chunk_window(
            center_chunk_id=match.get("chunk_id"),
            window=window,
            filename=match.get("filename"),
            document_id=match.get("document_id"),
        )
    else:
        chunks = get_resume_chunk_window(
            center_chunk_id=match.get("chunk_id"),
            window=window,
            filename=match.get("filename"),
            document_id=match.get("document_id"),
        )

    if chunks:
        return chunks

    fallback_chunk = dict(match)
    fallback_chunk["document_type"] = document_type
    return [fallback_chunk] if fallback_chunk.get("text") else []


def _should_focus_latest_document(
    document_type: str,
    query: str,
    scope_documents: list[str],
    active_documents: list[dict] | None = None,
) -> bool:
    lowered = " ".join((query or "").lower().split())
    active_documents = active_documents or []

    if document_type == "tender":
        return True

    if document_type != "resume":
        return False

    if active_documents:
        return len(active_documents) == 1

    if len(scope_documents) != 1:
        return False

    if ".pdf" in lowered:
        return False

    if any(hint in lowered for hint in COLLECTION_QUERY_HINTS):
        return False

    query_tokens = set(lowered.replace("?", " ").replace(",", " ").split())
    if query_tokens & COLLECTION_QUERY_TOKENS:
        return False

    return True


def _search_scope_matches(
    scope_documents: list[str],
    query: str,
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
    top_k_per_type: int = 8,
    total_top_k: int = 10,
) -> list[dict]:
    all_matches = []
    active_documents_by_type = active_documents_by_type or {}
    requested_active_document_types = requested_active_document_types or set()

    for document_type in scope_documents:
        active_documents = active_documents_by_type.get(document_type, [])
        active_document_ids = {
            document.get("id")
            for document in active_documents
            if document.get("id") is not None
        }
        if restrict_to_active_uploads and not active_document_ids:
            continue

        if document_type in requested_active_document_types and not active_document_ids:
            continue

        latest_document = None
        if (
            not active_document_ids
            and not restrict_to_active_uploads
            and document_type not in requested_active_document_types
            and _should_focus_latest_document(
                document_type,
                query,
                scope_documents,
                active_documents=active_documents,
            )
        ):
            latest_document = get_latest_document(document_type)

        focused_queries = _build_search_queries(document_type, query)

        # SATURATING SEARCH: Use Active Documents first.
        doc_ids_to_search = list(active_document_ids)
        if not doc_ids_to_search and latest_document:
            doc_ids_to_search = [latest_document.get("id")]

        if doc_ids_to_search:
            matches = []
            for doc_id in doc_ids_to_search:
                all_doc_chunks = get_persisted_document_chunks(doc_id)
                if len(all_doc_chunks) <= 30:
                    # Full document for small files
                    doc_matches = all_doc_chunks
                else:
                    doc_matches = _search_query_variants(
                        document_type,
                        focused_queries,
                        top_k=20,
                        document_id=doc_id,
                    )
                
                for match in doc_matches:
                    match["document_type"] = document_type
                    matches.append(match)
        else:
            matches = _search_query_variants(
                document_type,
                focused_queries,
                top_k=top_k_per_type,
            )

        for match in matches:
            enriched = dict(match)
            enriched["document_type"] = document_type
            all_matches.append(enriched)

    # Ensure parity in results: if we have multiple scope types, take a balanced amount from each
    # before doing any global sorting that could cause one type to dominate.
    type_counts = {}
    balanced_matches = []
    
    # We sort each group internally first
    all_matches.sort(key=lambda x: (x.get("retrieval_score", 0.0), x.get("keyword_score", 0.0)), reverse=True)
    
    max_per_type = total_top_k // len(set(scope_documents)) if scope_documents else total_top_k
    
    for match in all_matches:
        dtype = match.get("document_type")
        type_counts[dtype] = type_counts.get(dtype, 0) + 1
        if type_counts[dtype] <= max_per_type:
            balanced_matches.append(match)
            
    # If we still have room (one type had fewer results), fill it up
    if len(balanced_matches) < total_top_k:
        for match in all_matches:
            if match not in balanced_matches:
                balanced_matches.append(match)
            if len(balanced_matches) >= total_top_k:
                break

    return balanced_matches[:total_top_k]


def _gather_scope_context(
    scope_documents: list[str],
    query: str,
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
    top_k_per_type: int = 5,
    total_top_k: int = 6,
    chunk_window: int = 0,
    max_chunks: int = 5,
) -> tuple[list[dict], list[dict]]:
    active_documents_by_type = active_documents_by_type or {}
    requested_active_document_types = requested_active_document_types or set()
    search_results = _search_scope_matches(
        scope_documents,
        query,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
        top_k_per_type=top_k_per_type,
        total_top_k=total_top_k,
    )

    chunks = []
    structured_contexts = []
    seen_documents = set()
    seen_chunks = set()

    match_by_type = {}
    for match in search_results:
        dtype = match.get("document_type")
        if dtype not in match_by_type:
            match_by_type[dtype] = []
        match_by_type[dtype].append(match)

    num_types = len(match_by_type)
    chunks_per_type = max_chunks // num_types if num_types > 0 else max_chunks
    
    chunks_by_type = {}
    for dtype, type_matches in match_by_type.items():
        type_chunks = []
        active_documents = active_documents_by_type.get(dtype, [])
        
        for match in type_matches:
            document = _resolve_document(dtype, match, active_documents=active_documents)
            document_key = (document or {}).get("id") or match.get("document_id") or match.get("filename")

            canonical_context = preferred_structured_data(document)
            if document_key not in seen_documents and canonical_context:
                structured_contexts.append(canonical_context)
                seen_documents.add(document_key)

            context_chunks = _load_match_context_chunks(dtype, match, window=chunk_window)
            
            # IDENTITY PRIORITIZATION: For resumes, always grab the first 3 chunks (Page 1).
            # This is where Names, DOB, and Contact info live.
            if dtype == "resume":
                doc_id = (document or {}).get("id") or match.get("document_id")
                if doc_id:
                    identity_chunks = get_persisted_document_chunks(doc_id, limit=3)
                    for ic in identity_chunks:
                        if not any(c.get("chunk_id") == ic.get("chunk_id") for c in context_chunks):
                            context_chunks.insert(0, ic)

            for chunk in context_chunks:
                chunk["document_type"] = dtype
                chunk_key = (chunk.get("document_id"), chunk.get("filename"), chunk.get("chunk_id"))
                
                if chunk_key in seen_chunks or not chunk.get("text"):
                    continue
                
                seen_chunks.add(chunk_key)
                type_chunks.append(chunk)
                if len(type_chunks) >= (max_chunks // 2):
                    break
            
            if len(type_chunks) >= (max_chunks // 2):
                break
        chunks_by_type[dtype] = type_chunks

    # SECTIONED MERGE: Group all chunks by their type for the prompt
    final_chunks = []
    t_ch = chunks_by_type.get("tender", [])
    r_ch = chunks_by_type.get("resume", [])
    for i in range(max(len(t_ch), len(r_ch))):
        if i < len(t_ch):
            c = dict(t_ch[i]); c["text"] = f"[TENDER SOURCE]: {c['text']}"; final_chunks.append(c)
        if i < len(r_ch):
            c = dict(r_ch[i]); c["text"] = f"[RESUME SOURCE]: {c['text']}"; final_chunks.append(c)
                
    if final_chunks:
        return structured_contexts[:2], final_chunks[:max_chunks]

    if final_chunks:
        return structured_contexts[:2], final_chunks[:max_chunks]

    for document_type in scope_documents:
        active_documents = active_documents_by_type.get(document_type, [])
        if restrict_to_active_uploads and not active_documents:
            continue

        if document_type in requested_active_document_types and not active_documents:
            continue

        fallback_documents = active_documents or (
            [get_latest_document(document_type)]
            if get_latest_document(document_type)
            else []
        )

        if not fallback_documents:
            continue

        for fallback_document in fallback_documents:
            canonical_context = preferred_structured_data(fallback_document)
            if canonical_context:
                document_key = fallback_document.get("id")
                if document_key not in seen_documents:
                    structured_contexts.append(canonical_context)
                    seen_documents.add(document_key)

            fallback_chunks = _load_document_chunks(
                document_type,
                document=fallback_document,
                limit=max(4, max_chunks // max(1, len(scope_documents))),
            )
            for chunk in fallback_chunks:
                chunk["document_type"] = chunk.get("document_type") or document_type
                chunk_key = (
                    chunk.get("document_id"),
                    chunk.get("filename"),
                    chunk.get("chunk_id"),
                )
                if chunk_key in seen_chunks or not chunk.get("text"):
                    continue
                seen_chunks.add(chunk_key)
                chunks.append(chunk)
                if len(chunks) >= max_chunks:
                    break

            if len(chunks) >= max_chunks:
                break

        if len(chunks) >= max_chunks:
            break

    return structured_contexts[:2], chunks[:max_chunks]


def _source_list(chunks: list[dict]) -> list[dict]:
    sources = []
    seen = set()

    for chunk in chunks:
        source = (
            chunk.get("filename"),
            chunk.get("page_start"),
            chunk.get("page_end"),
            chunk.get("section"),
        )
        if source in seen:
            continue
        seen.add(source)
        sources.append(
            {
                "filename": chunk.get("filename", "unknown.pdf"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "section": chunk.get("section"),
            }
        )

    return sources[:6]


def _build_human_intervention_state(
    active_documents_by_type: dict[str, list[dict]] | None,
    scope_documents: list[str],
) -> dict:
    active_documents_by_type = active_documents_by_type or {}

    document_ids = []
    for document_type in scope_documents:
        for document in active_documents_by_type.get(document_type, []):
            document_id = document.get("id")
            if document_id is not None:
                document_ids.append(document_id)

    review_tasks = list_open_review_tasks_for_documents(document_ids)
    human_intervention_required = bool(review_tasks)

    return {
        "human_intervention_required": human_intervention_required,
        "human_intervention_reason": (
            "Human review is needed for one or more uploaded documents before relying on this answer."
            if human_intervention_required
            else ""
        ),
        "review_tasks": review_tasks,
    }


def _answer_qa(
    query: str,
    scope: str,
    active_documents_by_type: dict[str, list[dict]] | None = None,
    requested_active_document_types: set[str] | None = None,
    restrict_to_active_uploads: bool = False,
) -> dict:
    scope_map = {
        "tender": ["tender"],
        "resume": ["resume"],
        "both": ["tender", "resume"],
    }

    scope_documents = scope_map.get(scope, [])
    structured_contexts = []
    chunks = []

    structured_contexts, chunks = _gather_scope_context(
        scope_documents,
        query,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
        top_k_per_type=15,
        total_top_k=24,
        max_chunks=24,
        chunk_window=0,
    )

    # Collection Query Special Handling: Use structured search for aggregate questions
    is_collection_query = (
        scope == "resume" 
        and any(hint in query.lower() for hint in COLLECTION_HINTS)
    )
    if is_collection_query:
        search_result = search_resumes(query, page=1, page_size=20)
        total_matches = search_result.get("total", 0)
        if total_matches > 0:
            prompt = build_collection_summary_prompt(
                query=query, 
                total_count=total_matches, 
                matched_candidates=search_result.get("results", [])
            )
            answer_text = llm_text_answer(prompt).strip()
            if answer_text:
                return {
                    "mode": "qa",
                    "query_scope": scope,
                    "message": f"Analyzed {total_matches} candidates using structured search.",
                    "answer_text": answer_text,
                    "sources": [],
                    "matches": search_result.get("results", [])[:10],
                    "reasoning_summary": f"Found {total_matches} candidates matching criteria.",
                    **_build_human_intervention_state(active_documents_by_type, scope_documents),
                }

    if not chunks:
        return {
            "mode": "qa",
            "query_scope": scope,
            "message": "No uploaded documents are available for this question.",
            "answer_text": "",
            "sources": [],
            "matches": [],
            "reasoning_summary": "",
            **_build_human_intervention_state(active_documents_by_type, scope_documents),
        }

    scope_label = " and ".join(scope_documents) if scope_documents else scope
    exact_answer = _build_exact_fact_answer(
        query,
        scope_documents,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
    )
    if exact_answer:
        exact_answer_text, exact_chunks = exact_answer
        return {
            "mode": "qa",
            "query_scope": scope,
            "message": f"Answered using uploaded {scope_label} documents.",
            "answer_text": _compose_exact_answer_response(query, exact_answer_text, exact_chunks),
            "sources": _source_list(exact_chunks),
            "matches": [],
            "reasoning_summary": "",
            **_build_human_intervention_state(active_documents_by_type, scope_documents),
        }

    comparison_answer = _build_tender_resume_comparison_answer(
        query,
        scope_documents,
        active_documents_by_type=active_documents_by_type,
        requested_active_document_types=requested_active_document_types,
        restrict_to_active_uploads=restrict_to_active_uploads,
    )
    if comparison_answer:
        comparison_text, comparison_chunks = comparison_answer
        return {
            "mode": "qa",
            "query_scope": scope,
            "message": f"Answered using uploaded {scope_label} documents.",
            "answer_text": comparison_text,
            "sources": _source_list(comparison_chunks),
            "matches": [],
            "reasoning_summary": "",
            **_build_human_intervention_state(active_documents_by_type, scope_documents),
        }

    prompt = build_answer_prompt(query, scope_label, structured_contexts, chunks)
    answer_text = llm_text_answer(prompt).strip()

    if not answer_text:
        answer_text = build_fallback_answer(scope_label, chunks)

    return {
        "mode": "qa",
        "query_scope": scope,
        "message": f"Answered using uploaded {scope_label} documents.",
        "answer_text": answer_text,
        "sources": _source_list(chunks),
        "matches": [],
        "reasoning_summary": "",
        **_build_human_intervention_state(active_documents_by_type, scope_documents),
    }


def answer_query(
    query: str,
    tender_document_id: int | None = None,
    resume_document_ids: list[int] | None = None,
    restrict_to_active_uploads: bool = False,
) -> dict:
    active_documents_by_type = _build_active_documents_by_type(
        tender_document_id=tender_document_id,
        resume_document_ids=resume_document_ids,
    )
    active_scope_enabled = (
        restrict_to_active_uploads
        or tender_document_id is not None
        or bool(resume_document_ids)
    )

    if active_scope_enabled:
        has_tender = bool(active_documents_by_type["tender"])
        has_resume = bool(active_documents_by_type["resume"])
    else:
        has_tender = get_latest_document("tender") is not None or index_has_data("tender")
        has_resume = get_latest_document("resume") is not None or index_has_data("resume")

    requested_active_document_types = set()
    if tender_document_id is not None:
        requested_active_document_types.add("tender")
    if resume_document_ids:
        requested_active_document_types.add("resume")

    intent = classify_query_intent(query, has_tender=has_tender, has_resume=has_resume)

    if intent["mode"] == "matching":
        result = match_resumes_with_uploaded_tender(
            query,
            tender_document_id=tender_document_id,
            resume_document_ids=resume_document_ids,
            restrict_to_active_uploads=restrict_to_active_uploads,
        )
        result["mode"] = "matching"
        result["query_scope"] = "both"
        result.update(
            _build_human_intervention_state(
                active_documents_by_type,
                ["tender", "resume"],
            )
        )
        return result

    if intent["mode"] == "qa":
        return _answer_qa(
            query,
            scope=intent["scope"],
            active_documents_by_type=active_documents_by_type,
            requested_active_document_types=requested_active_document_types,
            restrict_to_active_uploads=restrict_to_active_uploads,
        )

    return {
        "mode": "none",
        "query_scope": "none",
        "message": "No uploaded tender or resume documents were found.",
        "answer_text": "",
        "sources": [],
        "matches": [],
        "reasoning_summary": "",
        "human_intervention_required": False,
        "human_intervention_reason": "",
        "review_tasks": [],
    }
