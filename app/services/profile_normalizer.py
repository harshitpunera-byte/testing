from __future__ import annotations

import re
from datetime import date, datetime

from app.rag.embeddings import create_embedding
from app.services.document_repository import (
    replace_resume_certifications,
    replace_resume_education,
    replace_resume_experiences,
    replace_resume_projects,
    replace_resume_skills,
    upsert_resume_profile,
    upsert_resume_search_index,
)
from app.services.matching_utils import resolve_qualification_generic_key


# Improved Regex for Phones (International/Local with various separators)
PHONE_PATTERN = re.compile(r"(?:(?:\+|00)\d{1,3}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}")
# Improved Regex for Emails
EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", re.IGNORECASE)
NOTICE_PATTERN = re.compile(r"notice\s+period\s*[:\-]?\s*(\d{1,3})\s*(?:days?|day)", re.IGNORECASE)
CTC_PATTERN = re.compile(r"(current|expected)\s+ctc\s*[:\-]?\s*([\d.]+)", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"(?:location|address|city)\s*[:\-]?\s*([A-Za-z][A-Za-z\s,.-]{2,80})", re.IGNORECASE)


def _get_val(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return item if key == "generic" or key == "raw" else default


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" ,:-")
    return cleaned or None


def _normalize_title(value: str | None) -> str | None:
    value = _clean_text(value)
    return value.lower() if value else None


def _extract_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text or "")
    return match.group(1) if match else None


def _extract_phone(text: str) -> str | None:
    if not text: return None
    # Look for common phone patterns
    matches = PHONE_PATTERN.findall(text)
    if not matches:
        return None
    # Take the one that looks most like a phone number (longest digit string)
    best_match = max(matches, key=lambda m: len(re.sub(r"\D", "", m)))
    cleaned = re.sub(r"[^\d+]", "", best_match)
    # Basic length filter (8-16 digits)
    if 8 <= len(re.sub(r"\D", "", cleaned)) <= 16:
        return best_match.strip()
    return None


def _extract_notice_period_days(text: str) -> int | None:
    match = NOTICE_PATTERN.search(text or "")
    return int(match.group(1)) if match else None


def _extract_ctc(text: str, label: str) -> float | None:
    for found_label, amount in CTC_PATTERN.findall(text or ""):
        if found_label.lower() == label.lower():
            try:
                return float(amount)
            except ValueError:
                return None
    return None


def _extract_location(text: str) -> tuple[str | None, str | None, str | None]:
    match = LOCATION_PATTERN.search(text or "")
    if not match:
        return None, None, None
    parts = [part.strip() for part in match.group(1).split(",") if part.strip()]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


def _extract_company(text: str) -> str | None:
    patterns = [
        r"(?:current company|company|employer)\s*[:\-]?\s*([A-Za-z0-9&.,() \-]{3,100})",
        r"(?:working at|worked at)\s+([A-Za-z0-9&.,() \-]{3,100})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1))
    return None


def _months_from_years(years: int | None) -> int | None:
    if years is None:
        return None
    return max(0, int(years) * 12)


def _parse_education_rows(qualifications: list[dict]) -> list[dict]:
    rows = []
    for item in qualifications or []:
        raw = _get_val(item, "raw")
        generic = _get_val(item, "generic")
        rows.append(
            {
                "degree": _clean_text(raw),
                "generic_key": generic or resolve_qualification_generic_key(raw),
                "specialization": None,
                "institution": None,
                "start_year": None,
                "end_year": None,
                "grade": None,
                "source_confidence": 0.8,
                "source_json": {"source": "structured_normalization"},
            }
        )
    return rows


def _parse_project_rows(projects: list[dict], role: str | None, domain: str | None) -> list[dict]:
    rows = []
    for item in projects or []:
        raw = _get_val(item, "raw")
        tags = _get_val(item, "generic_tags", [])
        rows.append(
            {
                "project_name": _clean_text(raw) or "Project",
                "role": role,
                "domain": domain,
                "tech_stack": tags,
                "description": _clean_text(raw),
                "start_date": None,
                "end_date": None,
                "source_confidence": 0.8,
                "source_json": {"source": "structured_normalization"},
            }
        )
    return rows


def _parse_experience_rows(full_text: str, structured_data: dict) -> list[dict]:
    role = structured_data.get("role")
    domain = structured_data.get("domain")
    exp_years = structured_data.get("total_experience_years")
    months = _months_from_years(exp_years)
    company = _extract_company(full_text)
    description = _clean_text((full_text or "")[:500])

    if not any([role, company, months, description]):
        return []

    return [
        {
            "company_name": company,
            "job_title": role,
            "normalized_job_title": _normalize_title(structured_data.get("role_generic") or role),
            "start_date": None,
            "end_date": None,
            "is_current": True,
            "duration_months": months,
            "location": _extract_location(full_text)[0],
            "description": description,
            "domain_tags": [structured_data.get("domain_generic") or domain] if (domain or structured_data.get("domain_generic")) else [],
            "source_confidence": 0.7,
            "source_json": {"source": "synthetic_from_profile"},
        }
    ]


def _parse_certification_rows(certifications: list[dict]) -> list[dict]:
    rows = []
    for item in certifications or []:
        raw = _get_val(item, "raw")
        generic = _get_val(item, "generic")
        rows.append(
            {
                "certification_name": _clean_text(raw)[:255],
                "issuer": None,
                "issued_at": None,
                "expires_at": None,
                "source_confidence": 0.8,
                "source_json": {"source": "structured_normalization", "generic": generic},
            }
        )
    return rows


def _skill_rows(skills: list[dict], total_experience_months: int | None) -> list[dict]:
    rows = []
    for index, item in enumerate(skills or []):
        raw = _get_val(item, "raw")
        generic = _get_val(item, "generic")
        normalized = generic or _normalize_title(raw)
        if not normalized:
            continue
        rows.append(
            {
                "skill_name_raw": raw,
                "skill_name_normalized": normalized,
                "skill_category": None,
                "years_used_months": total_experience_months,
                "last_used_year": date.today().year,
                "proficiency_score": 0.9 if index < 5 else 0.7,
                "is_primary": index < 10,
                "source_confidence": 0.9,
                "source_json": {"source": "structured_normalization"},
            }
        )
    return rows


def _build_summary(structured_data: dict, full_text: str) -> str:
    skills_raw = [_get_val(s, "raw") for s in structured_data.get("skills", []) if _get_val(s, "raw")]
    parts = [
        structured_data.get("candidate_name"),
        structured_data.get("role"),
        structured_data.get("domain"),
        ", ".join(skills_raw[:10]) if skills_raw else None,
    ]
    summary = " | ".join(part for part in parts if part)
    if summary:
        return summary
    return _clean_text((full_text or "")[:1000]) or ""


def normalize_resume_profile(
    document_id: int,
    structured_data: dict,
    full_text: str,
    evidence_map: dict,
    *,
    confidence_score: float | None = None,
    source_kind: str = "raw_extraction",
) -> dict:
    email = structured_data.get("email") or _extract_email(full_text)
    phone = structured_data.get("phone") or _extract_phone(full_text)
    location = structured_data.get("location")
    location_city, location_state, location_country = _extract_location(location or full_text)
    notice_period_days = _extract_notice_period_days(full_text)
    current_ctc = _extract_ctc(full_text, "current")
    expected_ctc = _extract_ctc(full_text, "expected")
    
    exp_years = structured_data.get("total_experience_years")
    total_experience_months = _months_from_years(exp_years)
    summary = _build_summary(structured_data, full_text)

    education_rows = _parse_education_rows(structured_data.get("qualifications") or [])
    
    profile_payload = {
        "candidate_name": structured_data.get("candidate_name"),
        "email": email,
        "phone": phone,
        "location_city": location_city,
        "location_state": location_state,
        "location_country": location_country,
        "current_company": _extract_company(full_text),
        "current_role": structured_data.get("role"),
        "normalized_title": structured_data.get("role_generic") or _normalize_title(structured_data.get("role")),
        "total_experience_months": total_experience_months,
        "relevant_experience_months": total_experience_months,
        "notice_period_days": notice_period_days,
        "current_ctc": current_ctc,
        "expected_ctc": expected_ctc,
        "highest_education": education_rows[0]["degree"] if education_rows else None,
        "summary": summary,
        "domain_tags": [structured_data.get("domain_generic") or structured_data.get("domain")] if (structured_data.get("domain_generic") or structured_data.get("domain")) else [],
        "confidence_score": confidence_score if confidence_score is not None else 0.85,
        "raw_profile_json": structured_data, # Store the exact requested JSON
    }
    profile = upsert_resume_profile(document_id, profile_payload)
    resume_profile_id = profile["id"]

    skill_rows = _skill_rows(structured_data.get("skills") or [], total_experience_months)
    experience_rows = _parse_experience_rows(full_text, structured_data)
    project_rows = _parse_project_rows(
        structured_data.get("projects") or [],
        structured_data.get("role"),
        structured_data.get("domain"),
    )
    certification_rows = _parse_certification_rows(structured_data.get("certifications") or [])

    replace_resume_skills(resume_profile_id, skill_rows)
    replace_resume_experiences(resume_profile_id, experience_rows)
    replace_resume_projects(resume_profile_id, project_rows)
    replace_resume_education(resume_profile_id, education_rows)
    replace_resume_certifications(resume_profile_id, certification_rows)

    search_payload = {
        "candidate_name": structured_data.get("candidate_name"),
        "normalized_title": _normalize_title(structured_data.get("role")),
        "location_city": location_city,
        "total_experience_months": total_experience_months,
        "relevant_experience_months": total_experience_months,
        "notice_period_days": notice_period_days,
        "current_ctc": current_ctc,
        "expected_ctc": expected_ctc,
        "highest_education": education_rows[0]["degree"] if education_rows else None,
        "skills_normalized": [row["skill_name_normalized"] for row in skill_rows],
        "domains": [structured_data.get("domain")] if structured_data.get("domain") else [],
        "companies": [profile_payload["current_company"]] if profile_payload["current_company"] else [],
        "summary_text": summary,
        "fulltext_tsv": summary,
        "summary_embedding": create_embedding(summary).tolist() if summary else None,
    }
    upsert_resume_search_index(resume_profile_id, search_payload)

    return {
        "profile": profile,
        "skills_count": len(skill_rows),
        "experiences_count": len(experience_rows),
        "projects_count": len(project_rows),
        "education_count": len(education_rows),
        "certifications_count": len(certification_rows),
    }
