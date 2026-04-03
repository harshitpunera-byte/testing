from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Float, and_, case, cast, desc, func, literal, or_, select, text

from app.database.connection import session_scope
from app.models.db_models import (
    Document,
    DocumentChunk,
    ResumeProfile,
    ResumeSearchIndex,
    ResumeSkill,
)
from app.rag.vector_store import search_index_hybrid, search_resume_profiles_semantic
from app.services.document_repository import get_resume_profile_with_relations
from app.services.matching_utils import (
    extract_structured_requirements,
    generate_matching_sql,
    normalize_value,
)
from app.llm.query_to_sql import generate_sql_for_query



from app.services.matching_utils import (
    normalize_value,
    resolve_qualification_generic_key,
)


SEARCH_KEYWORDS = {
    "find",
    "candidate",
    "candidates",
    "profiles",
    "developers",
    "engineers",
    "notice",
    "experience",
    "years",
    "location",
    "rank",
    "top",
    "best",
    "similar",
    "worked",
}

KNOWN_SKILLS = [
    "python",
    "react",
    "node",
    "node js",
    "nodejs",
    "postgresql",
    "postgres",
    "fastapi",
    "aws",
    "django",
    "java",
    "spring boot",
    "machine learning",
    "nlp",
    "docker",
    "kubernetes",
]


def _normalize_skill(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _extract_skills(query: str) -> list[str]:
    lowered = query.lower()
    skills = []
    for skill in KNOWN_SKILLS:
        if skill in lowered:
            skills.append(_normalize_skill(skill))
    return list(dict.fromkeys(skills))


def _extract_title(query: str) -> str | None:
    patterns = [
        r"for\s+([a-z][a-z\s/-]{3,80})",
        r"find\s+(?:[a-z]+\s+)*?(developers|engineers|candidates|backend engineers|frontend engineers|data scientists)",
        r"top\s+\d+\s+([a-z][a-z\s/-]{3,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            title = re.sub(r"\b(with|who|in|having)\b.*$", "", match.group(1)).strip()
            normalized = title or None
            if normalized in {"candidates", "developers", "engineers"}:
                return None
            return normalized
    return None


def _extract_location(query: str) -> str | None:
    match = re.search(r"\bin\s+([a-z][a-z\s-]{2,60})", query.lower())
    if match:
        location = re.split(r"\b(with|under|below|who|having|for)\b", match.group(1))[0].strip()
        return location or None
    return None


def _extract_min_experience(query: str) -> int | None:
    match = re.search(r"(\d+)\+?\s*(?:years|yrs)", query.lower())
    if match:
        return int(match.group(1))
    return None


def _extract_max_notice_period(query: str) -> int | None:
    match = re.search(r"(?:below|under|max(?:imum)?)\s+(\d{1,3})\s*(?:days?|day)", query.lower())
    if match:
        return int(match.group(1))
    if "immediate" in query.lower():
        return 15
    return None


def _extract_education_dynamic(query: str):
    lowered = query.lower()
    
    # Check for negation
    negation_match = re.search(rf"\b(not|no|without|except)\b", lowered)
    is_negated = bool(negation_match)
    
    # Common degree patterns
    degrees = [
        "btech", "b.tech", "be", "b.e", "bachelor of engineering",
        "mtech", "m.tech", "me", "m.e", "master of engineering",
        "bca", "mca", "mba", "bba", "bcom", "bsc", "b.sc", "msc", "m.sc",
        "barch", "b.arch", "diploma", "phd", "graduation", "post graduation",
        "masters", "master", "master's", "bachelors", "bachelor", "bachelor's", "pg", "ug"
    ]
    
    found_degree = None
    # 1. Try to find one of the common abbreviations first
    for d in degrees:
        if re.search(rf"\b{re.escape(d)}\b", lowered):
            found_degree = d
            break
            
    # 2. If no abbreviation, try to find a phrase like "degree in X" or "bachelor of X"
    if not found_degree:
        match = re.search(r"(?:degree|graduation|specialization|bachelor of|master of|masters in|diploma in)\s+(?:in\s+)?([a-z\s]{2,30})", lowered)
        if match:
            found_degree = match.group(1).strip()
            
    if not found_degree and not is_negated:
        return None
        
    degree_mapping_normalization = {
        "masters": "master",
        "master's": "master",
        "bachelors": "bachelor",
        "bachelor's": "bachelor"
    }
    
    normalized_degree = found_degree or "education"
    if normalized_degree in degree_mapping_normalization:
        normalized_degree = degree_mapping_normalization[normalized_degree]
        
    return {
        "degree_name": normalized_degree,
        "is_negated": is_negated
    }


def _classify_query_mode(query: str, parsed: dict) -> str:
    lowered = query.lower()
    if any(term in lowered for term in ["similar", "worked on", "related to", "experience with"]) and not parsed["skills"]:
        return "semantic"
    if any(term in lowered for term in ["rank", "top", "best", "shortlist"]):
        return "structured_rank"
    if parsed["skills"] or parsed["min_experience_years"] or parsed["location"] or parsed["max_notice_period_days"] or (parsed["education"] and not parsed["education"]["is_negated"]):
        return "structured_filter"
    if parsed["education"] and parsed["education"]["is_negated"]:
        return "structured_filter"
    return "hybrid"


def parse_search_query(query: str) -> dict:
    parsed = {
        "skills": _extract_skills(query),
        "title": _extract_title(query),
        "location": _extract_location(query),
        "min_experience_years": _extract_min_experience(query),
        "max_notice_period_days": _extract_max_notice_period(query),
        "education": _extract_education_dynamic(query),
    }
    parsed["mode"] = _classify_query_mode(query, parsed)
    return parsed


def _serialize_candidate(row: Any, *, score: float | None = None, score_breakdown: dict | None = None, evidence_snippets: list[dict] | None = None) -> dict:
    search_row, profile, document = row
    return {
        "resume_profile_id": profile.id,
        "document_id": document.id,
        "candidate_name": profile.candidate_name,
        "normalized_title": profile.normalized_title,
        "current_role": profile.current_role,
        "location_city": profile.location_city,
        "total_experience_months": profile.total_experience_months,
        "notice_period_days": profile.notice_period_days,
        "current_ctc": float(profile.current_ctc) if profile.current_ctc is not None else None,
        "expected_ctc": float(profile.expected_ctc) if profile.expected_ctc is not None else None,
        "highest_education": profile.highest_education,
        "skills_normalized": search_row.skills_normalized or [],
        "domains": search_row.domains or [],
        "summary_text": search_row.summary_text,
        "score": score,
        "score_breakdown": score_breakdown or {},
        "evidence_snippets": evidence_snippets or [],
        "review_status": document.review_status,
        "canonical_data_ready": document.canonical_data_ready,
        "uses_unreviewed_data": not document.canonical_data_ready,
    }


def _candidate_evidence(document_id: int, skills: list[str], limit: int = 3) -> list[dict]:
    if not skills:
        return []
    results = []
    hybrid = search_index_hybrid("resume", " ".join(skills), top_k=max(limit, 6))
    for row in hybrid:
        if row.get("document_id") != document_id:
            continue
        results.append(
            {
                "snippet": row.get("text", "")[:240],
                "page_start": row.get("page_start"),
                "section": row.get("section"),
            }
        )
        if len(results) >= limit:
            break
    return results


def get_structured_match_plan(tender_data: dict) -> dict:
    """
    Converts raw tender extraction into a structured matching plan with SQL.
    """
    structured_reqs = extract_structured_requirements(tender_data)
    sql_query = generate_matching_sql(structured_reqs)
    
    explanation = (
        f"Searching for roles matching '{structured_reqs['role']}' "
        f"with {structured_reqs['min_experience']}+ years experience. "
        f"Mandatory skills: {', '.join(structured_reqs['required_skills'])}. "
        f"Filtering by domain: {structured_reqs['domain']}."
    )
    
    return {
        "structured_requirements": structured_reqs,
        "sql_query": sql_query,
        "short_explanation": explanation
    }


def search_resumes(query: str, page: int = 1, page_size: int = 20) -> dict:
    parsed = parse_search_query(query)
    mode = parsed["mode"]
    offset = max(0, page - 1) * page_size

    with session_scope() as db:
        statement = (
            select(ResumeSearchIndex, ResumeProfile, Document)
            .join(ResumeProfile, ResumeProfile.id == ResumeSearchIndex.resume_profile_id)
            .join(Document, Document.id == ResumeProfile.document_id)
            .where(Document.processing_status == "stored", Document.document_type == "resume")
        )
        
        try:
            # === LLM SQL GENERATION ===
            generated_sql = generate_sql_for_query(query)
            
            # Execute LLM generated SQL to fetch valid candidate IDs
            matching_ids = [row[0] for row in db.execute(text(generated_sql)).fetchall()]
            
            if matching_ids:
                statement = statement.where(ResumeProfile.id.in_(matching_ids))
            else:
                statement = statement.where(ResumeProfile.id == -1)

        except Exception as e:
            generated_sql = f"LLM SQL generation failed: {e}\nFallback used."
            print(f"SQL Error: {e}")

        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = db.execute(
            statement.order_by(desc(ResumeProfile.total_experience_months), ResumeProfile.candidate_name.asc())
            .offset(offset)
            .limit(page_size)
        ).all()

    if mode == "semantic":
        semantic_results = search_resume_profiles_semantic(query, top_k=page_size)
        row_map = {row[1].id: row for row in rows}
        normalized_results = []
        for item in semantic_results:
            row = row_map.get(item["resume_profile_id"])
            if row:
                payload = _serialize_candidate(row)
            else:
                payload = {
                    "resume_profile_id": item["resume_profile_id"],
                    "document_id": item["document_id"],
                    "candidate_name": item.get("candidate_name"),
                    "normalized_title": item.get("normalized_title"),
                    "current_role": None,
                    "location_city": None,
                    "total_experience_months": None,
                    "notice_period_days": None,
                    "current_ctc": None,
                    "expected_ctc": None,
                    "highest_education": None,
                    "skills_normalized": item.get("skills", []),
                    "domains": [],
                    "summary_text": item.get("summary_text"),
                    "score": None,
                    "score_breakdown": {},
                    "evidence_snippets": [],
                    "review_status": item.get("review_status"),
                    "canonical_data_ready": item.get("canonical_data_ready", False),
                    "uses_unreviewed_data": item.get("uses_unreviewed_data", True),
                }
            payload["score"] = round(item.get("semantic_score", 0.0) * 100, 2)
            payload["score_breakdown"] = {"semantic_score": payload["score"]}
            normalized_results.append(payload)
        return {
            "mode": mode,
            "parsed_constraints": parsed,
            "total": len(normalized_results),
            "page": page,
            "page_size": page_size,
            "results": normalized_results,
            "uses_unreviewed_data": any(item.get("uses_unreviewed_data") for item in normalized_results),
            "fallback_notes": ["Semantic pgvector search was used."],
        }

    candidates = [_serialize_candidate(row) for row in rows]

    if mode in {"structured_rank", "hybrid"}:
        semantic_rankings = {
            item["resume_profile_id"]: item
            for item in search_resume_profiles_semantic(query, top_k=max(page_size, 20))
        }
        for candidate in candidates:
            matched_skills = [skill for skill in parsed["skills"] if skill in (candidate["skills_normalized"] or [])]
            experience_score = 0.0
            if parsed["min_experience_years"] is not None and candidate["total_experience_months"]:
                experience_score = min(
                    1.0,
                    candidate["total_experience_months"] / max(1, parsed["min_experience_years"] * 12),
                )
            title_score = 1.0 if parsed["title"] and candidate["normalized_title"] and parsed["title"] in candidate["normalized_title"] else 0.0
            skill_score = (len(matched_skills) / len(parsed["skills"])) if parsed["skills"] else 0.0
            semantic_score = semantic_rankings.get(candidate["resume_profile_id"], {}).get("semantic_score", 0.0)
            final_score = round((skill_score * 55) + (experience_score * 20) + (title_score * 10) + (semantic_score * 15), 2)
            candidate["score"] = final_score
            candidate["score_breakdown"] = {
                "skill_score": round(skill_score * 55, 2),
                "experience_score": round(experience_score * 20, 2),
                "title_score": round(title_score * 10, 2),
                "semantic_score": round(semantic_score * 15, 2),
            }
            candidate["evidence_snippets"] = _candidate_evidence(candidate["document_id"], parsed["skills"])

        candidates.sort(key=lambda item: (item.get("score", 0.0), item.get("total_experience_months") or 0), reverse=True)

    if mode == "hybrid" and not parsed["skills"] and not parsed["title"]:
        semantic_results = search_resume_profiles_semantic(query, top_k=max(page_size, 20))
        by_profile = {item["resume_profile_id"]: item for item in semantic_results}
        for candidate in candidates:
            semantic = by_profile.get(candidate["resume_profile_id"])
            if semantic:
                candidate["score"] = round((candidate.get("score") or 0.0) + (semantic["semantic_score"] * 25), 2)
                candidate["score_breakdown"]["semantic_rerank_bonus"] = round(semantic["semantic_score"] * 25, 2)
        candidates.sort(key=lambda item: item.get("score") or 0.0, reverse=True)

    return {
        "mode": mode,
        "parsed_constraints": parsed,
        "generated_sql": generated_sql,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "results": candidates,
        "uses_unreviewed_data": any(item.get("uses_unreviewed_data") for item in candidates),
        "fallback_notes": ["Hybrid semantic rerank used."] if mode == "hybrid" else [],
    }


def get_resume_profile_debug(document_id: int) -> dict | None:
    return get_resume_profile_with_relations(document_id)
