import re
from typing import Any, Dict, List

from app.llm.tender_llm_extractor import extract_tender_requirements_llm


TENDER_SKILL_PATTERNS = [
    ("highway", "Highway Construction"),
    ("4 lanning", "Road Construction"),
    ("four-lane", "Road Construction"),
    ("road", "Road Construction"),
    ("bridge", "Bridge Engineering"),
    ("civil", "Civil Engineering"),
    ("project management", "Project Management"),
    ("construction", "Construction Management"),
]

PREFERRED_MARKERS = ["preferred", "preferably", "desirable"]
PERSONNEL_MARKERS = [
    "candidate",
    "staff",
    "personnel",
    "engineer",
    "expert",
    "manager",
    "consultant",
    "team leader",
    "professional",
    "key personnel",
    "highway engineer",
    "bridge engineer",
    "material engineer",
    "quantity surveyor",
    "project manager",
]

TENDER_REVIEW_THRESHOLD = 0.80
TENDER_CRITICAL_FIELDS = {
    "role",
    "skills_required",
    "experience_required",
    "domain",
}


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :-")


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []

    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)

    return result


def _extract_domain(text: str):
    lowered = text.lower()

    if "highway" in lowered or "nhai" in lowered or "hybrid annuity mode" in lowered:
        return "Highway Construction"

    if "bridge" in lowered:
        return "Bridge Engineering"

    if "civil" in lowered:
        return "Civil Engineering"

    if "python" in lowered or "machine learning" in lowered or "fastapi" in lowered:
        return "AI/ML"

    return None


def _is_noise_line(line: str) -> bool:
    lowered = line.lower()

    if len(line) < 15:
        return True

    noise_patterns = [
        "request for proposals",
        "table of contents",
        "notice inviting bid",
        "appendix",
        "section-",
        "section ",
        "bid security",
        "power of attorney",
        "general terms of bidding",
        "opening and evaluation",
        "authority shall",
        "bidder",
        "contractor(s)",
        "consultant(s)",
    ]

    return any(pattern in lowered for pattern in noise_patterns)


def _extract_role(text: str):
    compact_text = _normalize_whitespace(text[:5000])

    if re.search(r"construction of .{0,160}?(?:highway|road|lanning|lane)", compact_text, flags=re.IGNORECASE):
        return "Highway Construction Contractor"

    if re.search(r"construction of .{0,160}?bridge", compact_text, flags=re.IGNORECASE):
        return "Bridge Engineering Contractor"

    title_lines = []

    for raw_line in text.splitlines()[:80]:
        clean_line = _normalize_whitespace(raw_line)
        if not clean_line or _is_noise_line(clean_line):
            continue
        title_lines.append(clean_line)

    title_block = " ".join(title_lines[:12])

    if "highway" in title_block.lower() or "lanning" in title_block.lower():
        return "Highway Construction Contractor"

    if "bridge" in title_block.lower():
        return "Bridge Engineering Contractor"

    match = re.search(r"(construction of .{20,180}?)($| under | in the state| on hybrid annuity)", title_block, flags=re.IGNORECASE)
    if match:
        role = _normalize_whitespace(match.group(1))
        if role and not _is_noise_line(role):
            return role[:120]

    return None


def _extract_skills(text: str) -> List[str]:
    lowered = text.lower()
    skills = [skill for pattern, skill in TENDER_SKILL_PATTERNS if pattern in lowered]
    return _unique(skills)


def _extract_experience(text: str):
    clauses = re.split(r"[\n.;]", text)

    for clause in clauses:
        clean_clause = _normalize_whitespace(clause)
        lowered = clean_clause.lower()

        if not clean_clause:
            continue
        if not any(marker in lowered for marker in PERSONNEL_MARKERS):
            continue

        patterns = [
            r"(?:minimum|at least|not less than)\s+(\d+)\s+years?(?:\s+of)?\s+(?:total|professional|relevant)?\s*experience",
            r"(\d+)\+?\s+years?(?:\s+of)?\s+experience",
            r"experience\s*(?:of|not less than)?\s*(\d+)\s*years",
        ]

        for pattern in patterns:
            match = re.search(pattern, clean_clause, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))

    return None


def _extract_preferred_skills(text: str) -> List[str]:
    clauses = re.split(r"[\n.;]", text)
    preferred_skills = []

    for clause in clauses:
        clean_clause = _normalize_whitespace(clause)
        lowered = clean_clause.lower()

        if not clean_clause:
            continue
        if "undesirable" in lowered:
            continue
        if not any(marker in lowered for marker in PREFERRED_MARKERS):
            continue

        preferred_skills.extend(_extract_skills(clean_clause))

    return _unique(preferred_skills)


def _extract_qualifications(text: str) -> List[str]:
    lowered = text.lower()
    qualifications = []

    if "technical capacity" in lowered:
        qualifications.append("Technical capacity in similar infrastructure projects")
    if "financial capacity" in lowered or "net worth" in lowered:
        qualifications.append("Financial capacity / net worth compliance")
    if "eligibility" in lowered or "qualification" in lowered:
        qualifications.append("Eligibility and qualification compliance")
    if "experience certificate" in lowered:
        qualifications.append("Experience certificate for similar projects")
    if "bid security" in lowered:
        qualifications.append("Bid security submission")

    return qualifications[:5]


def _extract_responsibilities(text: str) -> List[str]:
    lowered = text.lower()
    responsibilities = []

    if "highway" in lowered or "road" in lowered or "lanning" in lowered:
        responsibilities.append("Execute highway and road construction works")
    if "bridge" in lowered:
        responsibilities.append("Deliver bridge and structural works where applicable")
    if "construction" in lowered or "project management" in lowered:
        responsibilities.append("Manage construction execution and project delivery")
    if "hybrid annuity mode" in lowered:
        responsibilities.append("Comply with Hybrid Annuity Mode project requirements")

    return responsibilities[:5]


def _heuristic_extract_tender(text: str) -> Dict:
    focus_text = "\n".join(text.splitlines()[:200])

    return {
        "role": _extract_role(focus_text),
        "domain": _extract_domain(focus_text),
        "skills_required": _extract_skills(focus_text),
        "preferred_skills": _extract_preferred_skills(focus_text),
        "experience_required": _extract_experience(focus_text),
        "qualifications": _extract_qualifications(focus_text),
        "responsibilities": _extract_responsibilities(focus_text),
    }


def extract_tender_requirements(text: str):
    heuristic = _heuristic_extract_tender(text)
    data = extract_tender_requirements_llm(text)

    # Convert Pydantic model to dict for easier return
    result = data.model_dump()

    # Heuristic fallback for simple fields if LLM missed them
    if not result.get("role") and heuristic.get("role"):
        result["role"] = heuristic["role"]
    
    if not result.get("domain") and heuristic.get("domain"):
        result["domain"] = heuristic["domain"]

    if result.get("experience_required") is None and heuristic.get("experience_required") is not None:
        result["experience_required"] = heuristic["experience_required"]

    # For structured list fields, we prefer LLM's raw/generic pairs.
    # If LLM returned nothing but heuristic found something, we can semi-populate.
    if not result.get("skills_required") and heuristic.get("skills_required"):
        result["skills_required"] = [{"raw": s, "generic": s.lower().replace(" ", "_")} for s in heuristic["skills_required"]]

    if not result.get("qualifications") and heuristic.get("qualifications"):
        result["qualifications"] = [{"raw": q, "generic": q.lower().replace(" ", "_")} for q in heuristic["qualifications"]]

    if not result.get("responsibilities") and heuristic.get("responsibilities"):
        result["responsibilities"] = heuristic["responsibilities"]

    if not result.get("summary") and result.get("role"):
        result["summary"] = f"Requirement for {result['role']} in {result.get('domain') or 'infrastructure'} domain."

    return result


def _review_is_missing(value: Any) -> bool:
    return value in (None, "", []) or (isinstance(value, list) and not [item for item in value if item not in (None, "")])


def _review_evidence_entries(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _review_best_evidence(value: Any) -> dict:
    entries = _review_evidence_entries(value)
    if not entries:
        return {}
    return max(entries, key=lambda entry: float(entry.get("confidence", 0.0) or 0.0))


def _review_average_confidence(value: Any) -> float:
    entries = _review_evidence_entries(value)
    if not entries:
        return 0.0
    return round(sum(float(entry.get("confidence", 0.0) or 0.0) for entry in entries) / len(entries), 2)


def _clamp_confidence(value: float) -> float:
    return round(max(0.0, min(0.99, value)), 2)


def _tender_field_confidence(field_name: str, value: Any, evidence_value: Any) -> float:
    evidence_confidence = _review_average_confidence(evidence_value)

    if _review_is_missing(value):
        return 0.0

    if field_name == "skills_required":
        count = len(value or [])
        if count >= 4:
            heuristic = 0.92
        elif count >= 2:
            heuristic = 0.82
        else:
            heuristic = 0.55
        return _clamp_confidence((heuristic * 0.7) + (evidence_confidence * 0.3))

    if field_name == "preferred_skills":
        heuristic = 0.72 if value else 0.0
        return _clamp_confidence((heuristic * 0.65) + (evidence_confidence * 0.35))

    if field_name == "experience_required":
        try:
            years = int(value)
        except (TypeError, ValueError):
            years = None
        heuristic = 0.82 if years is not None and 0 <= years <= 45 else 0.35
        return _clamp_confidence((heuristic * 0.65) + (evidence_confidence * 0.35))

    if field_name == "role":
        heuristic = 0.86 if 2 <= len(str(value).split()) <= 12 else 0.62
        return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))

    if field_name == "domain":
        heuristic = 0.78 if str(value).strip() else 0.0
        return _clamp_confidence((heuristic * 0.65) + (evidence_confidence * 0.35))

    if isinstance(value, list):
        heuristic = 0.7 if value else 0.0
        return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))

    heuristic = 0.7 if str(value).strip() else 0.0
    return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))


def build_tender_review_payload(
    text: str,
    structured_data: dict[str, Any],
    evidence_map: dict[str, Any],
    *,
    extraction_backend: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    missing_critical_fields: list[str] = []

    for field_name, value in (structured_data or {}).items():
        evidence = _review_best_evidence((evidence_map or {}).get(field_name))
        confidence = _tender_field_confidence(field_name, value, (evidence_map or {}).get(field_name))
        is_critical = field_name in TENDER_CRITICAL_FIELDS

        if is_critical and _review_is_missing(value):
            missing_critical_fields.append(field_name)

        fields[field_name] = {
            "value": value,
            "confidence": confidence,
            "evidence_page": evidence.get("page"),
            "evidence_text": evidence.get("source_text"),
            "is_critical": is_critical,
        }

        if is_critical and confidence < TENDER_REVIEW_THRESHOLD:
            issues.append(f"low_confidence_{field_name}")

    if missing_critical_fields:
        for field_name in missing_critical_fields:
            issues.append(f"missing_{field_name}")

    if extraction_backend and "ocr" in extraction_backend.lower():
        issues.append("ocr_used")

    if len((text or "").strip()) < 500:
        issues.append("limited_extracted_text")

    required_skill_count = len(structured_data.get("skills_required") or [])
    preferred_skill_count = len(structured_data.get("preferred_skills") or [])
    if required_skill_count == 0 and preferred_skill_count == 0:
        issues.append("empty_skill_requirements")
    elif required_skill_count < 2:
        issues.append("sparse_required_skills")

    overall_scores = [field["confidence"] for field in fields.values() if field["value"] not in (None, "", [])]
    overall_confidence = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0

    if "ocr_used" in issues:
        overall_confidence -= 0.12
    if "limited_extracted_text" in issues:
        overall_confidence -= 0.08
    if "empty_skill_requirements" in issues:
        overall_confidence -= 0.14
    if "sparse_required_skills" in issues:
        overall_confidence -= 0.08
    if missing_critical_fields:
        overall_confidence -= 0.10 * len(missing_critical_fields)

    overall_confidence = _clamp_confidence(overall_confidence)
    recommended_review = (
        overall_confidence < TENDER_REVIEW_THRESHOLD
        or bool(missing_critical_fields)
        or "ocr_used" in issues
        or "empty_skill_requirements" in issues
        or "sparse_required_skills" in issues
    )

    return {
        "fields": fields,
        "overall_confidence": overall_confidence,
        "issues": list(dict.fromkeys(issues)),
        "missing_critical_fields": missing_critical_fields,
        "recommended_review": recommended_review,
        "raw_profile": structured_data or {},
    }
