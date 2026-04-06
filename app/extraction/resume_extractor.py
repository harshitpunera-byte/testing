from datetime import date, datetime
import html
import re
from typing import Any, Dict, List

from app.llm.resume_llm_extractor import extract_resume_profile_llm


RESUME_SKILL_PATTERNS = [
    ("python", "Python"),
    ("fastapi", "FastAPI"),
    ("nlp", "NLP"),
    ("machine learning", "Machine Learning"),
    ("aws", "AWS"),
    ("highway", "Highway Construction"),
    ("road", "Road Construction"),
    ("bridge", "Bridge Engineering"),
    ("structural", "Structural Engineering"),
    ("civil engineering", "Civil Engineering"),
    ("construction supervision", "Construction Supervision"),
    ("project management", "Project Management"),
    ("construction management", "Construction Management"),
    ("project monitoring", "Project Monitoring"),
    ("quality control", "Quality Control"),
    ("survey", "Survey"),
    ("detailed project report", "Detailed Project Report"),
]

PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

NAME_NOISE_TOKENS = {
    "accounting",
    "address",
    "admit",
    "ai",
    "analyst",
    "about",
    "api",
    "app",
    "architect",
    "aws",
    "business",
    "candidate",
    "career",
    "card",
    "center",
    "city",
    "civil",
    "consultant",
    "curriculum",
    "data",
    "developer",
    "director",
    "docker",
    "economics",
    "education",
    "engineer",
    "email",
    "english",
    "exam",
    "examination",
    "experience",
    "fastapi",
    "foundation",
    "general",
    "github",
    "gmail",
    "hindi",
    "image",
    "intentionally",
    "instructions",
    "invigilator",
    "laws",
    "lead",
    "learning",
    "linkedin",
    "medium",
    "mobile",
    "machine",
    "manager",
    "name",
    "native",
    "nlp",
    "number",
    "objective",
    "omitted",
    "paper",
    "photo",
    "picture",
    "position",
    "profession",
    "profile",
    "project",
    "projects",
    "python",
    "qualification",
    "qualifications",
    "reasoning",
    "react",
    "registration",
    "resume",
    "role",
    "roll",
    "signature",
    "skill",
    "skills",
    "software",
    "specialist",
    "staff",
    "statistics",
    "structural",
    "summary",
    "table",
    "technologies",
    "technology",
    "time",
    "vitae",
}

ADDRESS_HINTS = {
    "address",
    "apartment",
    "block",
    "building",
    "colony",
    "district",
    "email",
    "floor",
    "house",
    "lane",
    "locality",
    "pin",
    "pincode",
    "po",
    "post",
    "road",
    "sector",
    "state",
    "street",
    "village",
}

RESUME_REVIEW_THRESHOLD = 0.80
RESUME_CRITICAL_FIELDS = {
    "candidate_name",
    "role",
    "total_experience_years",
    "skills",
}


def _normalize_whitespace(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", " : ", value, flags=re.IGNORECASE)
    value = re.sub(r"[*_`#~]+", " ", value)
    value = value.replace("|", " ")
    value = value.replace("•", " ")
    value = value.replace("·", " ")
    value = value.replace("‚", " ")
    value = value.replace("Â", " ")
    return re.sub(r"\s+", " ", value).strip(" |:-")


def _prepare_focus_text(text: str, char_limit: int = 12000) -> str:
    return _normalize_whitespace(text[:char_limit])


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []

    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)

    return result


def _dedupe_projects(values: List[str]) -> List[str]:
    unique_projects = []
    signatures = []

    for value in values:
        cleaned = _normalize_whitespace(value)
        signature = re.sub(r"[^a-z0-9]", "", cleaned.lower())

        if not signature:
            continue

        prefix = signature[:80]
        if any(prefix == existing_prefix[:80] for existing_prefix in signatures):
            continue
        if any(signature in existing or existing in signature for existing in signatures):
            continue

        signatures.append(signature)
        unique_projects.append(cleaned)

    return unique_projects


def _line_candidates(text: str, limit: int = 160) -> List[str]:
    return [_normalize_whitespace(line) for line in text.splitlines()[:limit] if _normalize_whitespace(line)]


def _extract_value_near_label(lines: List[str], labels: List[str], stop_labels: List[str]) -> str | None:
    normalized_labels = {label.lower().rstrip(":") for label in labels}
    normalized_stop_labels = {label.lower().rstrip(":") for label in stop_labels}

    for index, line in enumerate(lines):
        current = line.lower().rstrip(":")

        if current in normalized_labels:
            for next_index in range(index + 1, min(index + 4, len(lines))):
                candidate = lines[next_index]
                candidate_key = candidate.lower().rstrip(":")
                if candidate == ":" or candidate_key in normalized_stop_labels:
                    continue
                return candidate

        for label in normalized_labels:
            inline_match = re.match(
                rf"^{re.escape(label)}(?![A-Za-z])\s*:?\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if inline_match:
                candidate = _normalize_whitespace(inline_match.group(1))
                candidate_key = candidate.lower().rstrip(":")
                if candidate and candidate_key not in normalized_stop_labels:
                    return candidate

    return None


def _extract_between_labels(flat_text: str, labels: List[str], stop_labels: List[str], max_chars: int = 120) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    stop_pattern = "|".join(re.escape(label) for label in stop_labels)

    pattern = (
        rf"(?<![A-Za-z])(?:{label_pattern})(?![A-Za-z])\s*:?\s*(.+?)"
        rf"(?=\s+(?<![A-Za-z])(?:{stop_pattern})(?![A-Za-z])\s*:|$)"
    )
    match = re.search(pattern, flat_text, flags=re.IGNORECASE)

    if not match:
        return None

    value = _normalize_whitespace(match.group(1))
    if not value:
        return None

    return value[:max_chars].strip(" ,;:-")


def _sanitize_name(value: str | None) -> str | None:
    if not value:
        return None

    lowered_raw = value.lower()
    if "@" in lowered_raw or ".com" in lowered_raw or ".in" in lowered_raw:
        return None

    value = re.sub(r"[^A-Za-z.\s'-]", " ", value)
    value = _normalize_whitespace(value)
    tokens = [token for token in value.split() if token]

    if not 2 <= len(tokens) <= 6:
        return None

    filtered = [
        token
        for token in tokens
        if token.lower() not in {"name", "staff", "candidate", "profession", "firm", "position"}
    ]

    if len(filtered) < 2:
        return None

    lowered_tokens = {token.lower().strip(".") for token in filtered}
    if lowered_tokens & NAME_NOISE_TOKENS:
        return None

    if any(len(token) <= 1 for token in filtered):
        return None

    return " ".join(filtered[:6])


def _looks_like_address(line: str) -> bool:
    lowered = line.lower()

    if "@" in lowered or re.search(r"\d", line):
        return True

    return any(token in lowered for token in ADDRESS_HINTS)


def _looks_like_date_marker(line: str) -> bool:
    normalized = _normalize_whitespace(line)

    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", normalized):
        return True

    return bool(
        re.fullmatch(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*,?\s+\d{4}",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _score_name_line(lines: List[str], index: int) -> tuple[int, str | None]:
    sanitized = _sanitize_name(lines[index])
    if not sanitized:
        return 0, None

    score = 1
    lowered_window = " ".join(lines[max(0, index - 5):index]).lower()

    if any(label in lowered_window for label in ["name of staff", "name of candidate", "candidate name", "candidate's name"]):
        score += 3

    if index > 0 and _looks_like_date_marker(lines[index - 1]):
        score += 2

    if index + 1 < len(lines) and _looks_like_address(lines[index + 1]):
        score += 2

    if index <= 6:
        score += 2

    if 2 <= len(sanitized.split()) <= 4:
        score += 1

    return score, sanitized


def _extract_name_from_label_window(lines: List[str]) -> str | None:
    normalized_labels = {
        "name of staff",
        "name of candidate",
        "candidate name",
        "candidate's name",
    }
    normalized_stop_labels = {
        "candidate's address",
        "candidate address",
        "address",
        "roll no",
        "roll no.",
        "city",
        "candidate's signature",
        "signature",
        "medium",
        "registration no",
        "registration no.",
        "registration number",
        "mobile number",
        "mobile no",
        "center of examination",
        "centre of examination",
        "date of birth",
        "years with firm/entity",
        "nationality",
        "membership of professional societies",
        "detailed task assigned",
    }

    for index, line in enumerate(lines):
        current = line.lower().rstrip(":")
        if current not in normalized_labels:
            continue

        best_match = None
        best_score = 0

        for next_index in range(index + 1, min(index + 40, len(lines))):
            candidate = lines[next_index].lower().rstrip(":")
            if candidate in normalized_stop_labels:
                continue

            score, sanitized = _score_name_line(lines, next_index)
            if sanitized and score > best_score:
                best_match = sanitized
                best_score = score

        if best_match:
            return best_match

    return None


def _extract_name_from_scored_lines(lines: List[str]) -> str | None:
    best_match = None
    best_score = 0

    for index in range(min(len(lines), 80)):
        score, sanitized = _score_name_line(lines, index)
        if sanitized and score > best_score:
            best_match = sanitized
            best_score = score

    if best_match and best_score >= 3:
        return best_match

    return None


def _sanitize_role(value: str | None) -> str | None:
    if not value:
        return None

    value = re.sub(r"[^A-Za-z/&().,\-\s]", " ", value)
    value = _normalize_whitespace(value)

    if len(value) > 90:
        return None

    tokens = value.split()
    if not 1 <= len(tokens) <= 10:
        return None

    lowered_tokens = {token.lower().strip(".") for token in tokens}
    if lowered_tokens <= {"technical", "proposal"}:
        return None
    if lowered_tokens <= {"about", "me"}:
        return None
    if lowered_tokens <= {"career", "objective"}:
        return None
    if lowered_tokens <= {"professional", "summary"}:
        return None
    if lowered_tokens <= {"image"}:
        return None
    if {"picture", "omitted"} & lowered_tokens:
        return None
    if "engineering" in lowered_tokens and not lowered_tokens & {
        "engineer",
        "developer",
        "manager",
        "specialist",
        "consultant",
        "architect",
        "analyst",
        "lead",
        "director",
    }:
        return None

    return value


def _extract_summary_role(lines: List[str]) -> str | None:
    for line in lines[:10]:
        normalized_line = line
        for prefix in [
            "professional summary",
            "profile summary",
            "summary",
            "about me",
            "about",
        ]:
            lowered_line = normalized_line.lower()
            if lowered_line.startswith(f"{prefix} "):
                normalized_line = normalized_line[len(prefix):].strip()
                break

        summary_match = re.match(
            r"^([A-Za-z][A-Za-z/&().,\-\s]{2,80}?)\s+with\s+\d+\+?\s+years?\s+of\s+experience",
            normalized_line,
            flags=re.IGNORECASE,
        )
        if not summary_match:
            continue

        sanitized = _sanitize_role(summary_match.group(1))
        if sanitized:
            return sanitized

    return None


def _extract_header_role(lines: List[str]) -> str | None:
    for index, line in enumerate(lines[:12]):
        lowered = line.lower()
        if lowered in {"technical proposal", "curriculum vitae", "cv", "profile"}:
            continue

        if any(
            token in lowered
            for token in [
                "engineer",
                "manager",
                "specialist",
                "consultant",
                "developer",
                "architect",
                "analyst",
                "lead",
                "director",
            ]
        ):
            return _sanitize_role(line)

    return None


def _extract_candidate_name(text: str):
    lines = _line_candidates(text)
    flat_text = _prepare_focus_text(text)

    value = _extract_value_near_label(
        lines,
        ["Name of Staff", "Name of Candidate", "Candidate Name", "Candidate's Name"],
        [
            "Candidate's Address",
            "Address",
            "Roll No",
            "City",
            "Candidate's Signature",
            "Medium",
            "Registration No",
            "Mobile Number",
            "Center of Examination",
            "Profession",
            "Date of Birth",
            "Years with Firm/Entity",
            "Nationality",
            "Membership of Professional Societies",
        ],
    )
    if value:
        sanitized = _sanitize_name(value)
        if sanitized:
            return sanitized

    value = _extract_name_from_label_window(lines)
    if value:
        return value

    value = _extract_between_labels(
        flat_text,
        ["Name of Staff", "Name of Candidate", "Candidate Name", "Candidate's Name"],
        [
            "Candidate's Address",
            "Address",
            "Roll No",
            "City",
            "Candidate's Signature",
            "Medium",
            "Registration No",
            "Mobile Number",
            "Center of Examination",
            "Profession",
            "Date of Birth",
            "Years with Firm/Entity",
            "Nationality",
            "Membership of Professional Societies",
            "Detailed Task Assigned",
        ],
        max_chars=80,
    )
    if value:
        sanitized = _sanitize_name(value)
        if sanitized:
            return sanitized

    return _extract_name_from_scored_lines(lines)


def _extract_role(text: str):
    lines = _line_candidates(text)
    flat_text = _prepare_focus_text(text)

    value = _extract_value_near_label(
        lines,
        ["Proposed Position", "Position", "Role", "Profession"],
        ["Name of Firm", "Name of Staff", "Candidate Name", "Date of Birth", "Years with Firm/Entity", "Nationality"],
    )
    if value:
        sanitized = _sanitize_role(value)
        if sanitized:
            return sanitized

    value = _extract_between_labels(
        flat_text,
        ["Proposed Position", "Position", "Role", "Profession"],
        ["Name of Firm", "Name of Staff", "Candidate Name", "Date of Birth", "Years with Firm/Entity", "Nationality", "Membership of Professional Societies"],
        max_chars=90,
    )
    if value:
        sanitized = _sanitize_role(value)
        if sanitized:
            return sanitized

    value = _extract_summary_role(lines)
    if value:
        return value

    return _extract_header_role(lines)


def _extract_domain(text: str):
    lowered = text.lower()

    if "highway" in lowered or "nhai" in lowered:
        return "Highway Construction"

    if "bridge" in lowered or "structural" in lowered:
        return "Bridge Engineering"

    if "civil engineering" in lowered or "civil engineer" in lowered:
        return "Civil Engineering"

    if "python" in lowered or "machine learning" in lowered or "fastapi" in lowered:
        return "AI/ML"

    return None


def _extract_skills(text: str) -> List[str]:
    lowered = text.lower()
    skills = [skill for pattern, skill in RESUME_SKILL_PATTERNS if pattern in lowered]
    return _unique(skills)


def _extract_experience(text: str):
    direct_matches = [
        int(value)
        for value in re.findall(
            r"(?:total|overall|professional|relevant)?\s*(\d+)\+?\s+years?(?:\s+of)?\s+(?:professional\s+)?experience",
            text,
            flags=re.IGNORECASE,
        )
    ]
    if direct_matches:
        return max(direct_matches)

    labelled_patterns = [
        r"Years with Firm/Entity\s*:?\s*(\d{1,2})(?:\.\d+)?",
        r"Experience Details\s*:?\s*(\d{1,2})(?:\.\d+)?",
        r"Professional Experience\s*:?\s*(\d{1,2})(?:\.\d+)?",
    ]
    for pattern in labelled_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(float(match.group(1)))

    date_token = (
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        r"|\d{1,2}-[A-Za-z]{3}-\d{2,4}"
        r"|[A-Za-z]{3,9}\s+\d{4}"
        r"|[A-Za-z]{3}-\d{2,4}"
        r"|Till Date|Present|Current)"
    )
    pair_pattern = re.compile(
        rf"({date_token})\s+(?:to\s+)?({date_token})",
        flags=re.IGNORECASE,
    )

    ranges = []

    for match in pair_pattern.finditer(text):
        start = _parse_resume_date(match.group(1))
        end = _parse_resume_date(match.group(2))

        if not start or not end:
            continue
        if start.year < 1990 or end < start:
            continue

        span_years = (end - start).days / 365.25
        if 0.25 <= span_years <= 40:
            ranges.append((start, end))

    if ranges:
        earliest = min(start for start, _ in ranges)
        latest = max(end for _, end in ranges)
        years = round((latest - earliest).days / 365.25)
        if 1 <= years <= 40:
            return years

    return None


def _extract_projects(text: str) -> List[str]:
    focus_text = text[:40000]
    projects = []

    project_patterns = [
        r"(Independent Engineer Services for .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Consultancy Services for .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Construction of .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Widening and strengthening .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Rehabilitation and Upgradation .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Four laning .{30,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
        r"(Detailed Project Report .{20,220}?)(?=(?:\s+(?:India|Country|State|Employer Name|Project Status|Completion Certificate|View)\b|[.;]))",
    ]

    noise_patterns = [
        "authority of india would be at liberty",
        "certification by the candidate",
        "certification by the firm",
        "self-evaluation",
        "date of birth",
        "candidate_name",
        "signature of",
        "debar",
        "construction program and monitoring day-to-day site activities",
        "monitoring day-to-day site activities",
    ]

    for pattern in project_patterns:
        for match in re.finditer(pattern, focus_text, flags=re.IGNORECASE):
            snippet = _normalize_whitespace(match.group(1))
            lowered = snippet.lower()
            if any(noise in lowered for noise in noise_patterns):
                continue
            if 30 <= len(snippet) <= 220:
                projects.append(snippet[:200])

    return _dedupe_projects(_unique(projects))[:6]


def _parse_resume_date(value: str) -> date | None:
    raw_value = _normalize_whitespace(value).strip(".")
    lowered = raw_value.lower()

    if lowered in {"till date", "present", "current"}:
        return date.today()

    cleaned = re.sub(r"(\d)(st|nd|rd|th)", r"\1", raw_value, flags=re.IGNORECASE)
    cleaned = cleaned.replace("Â", " ")

    formats = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %B %Y",
        "%b-%Y",
        "%b-%y",
        "%b %Y",
        "%B %Y",
        "%Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            if fmt == "%Y":
                parsed = parsed.replace(month=1, day=1)
            elif fmt in {"%b-%Y", "%b-%y", "%b %Y", "%B %Y"}:
                parsed = parsed.replace(day=1)
            return parsed.date()
        except ValueError:
            continue

    return None


def _heuristic_extract_resume(text: str) -> Dict:
    focus_text = text[:50000]

    return {
        "candidate_name": _extract_candidate_name(focus_text),
        "phone": (PHONE_PATTERN.search(focus_text) or re.search(r"", "")).group(0) if PHONE_PATTERN.search(focus_text) else None,
        "email": (EMAIL_PATTERN.search(focus_text) or re.search(r"", "")).group(0) if EMAIL_PATTERN.search(focus_text) else None,
        "role": _extract_role(focus_text),
        "domain": _extract_domain(focus_text),
        "skills": _extract_skills(focus_text),
        "experience": _extract_experience(focus_text),
        "qualifications": [],
        "projects": _extract_projects(focus_text),
    }


def extract_resume_data(text: str):
    heuristic = _heuristic_extract_resume(text)
    data = extract_resume_profile_llm(text)

    # Convert Pydantic model to dict for easier merging/return
    result = data.model_dump()

    # Heuristic fallback for simple fields if LLM missed them
    if not result.get("candidate_name") and heuristic.get("candidate_name"):
        result["candidate_name"] = heuristic["candidate_name"]
    
    if result.get("total_experience_years") is None and heuristic.get("experience") is not None:
        result["total_experience_years"] = heuristic["experience"]

    if not result.get("role") and heuristic.get("role"):
        result["role"] = heuristic["role"]

    if not result.get("domain") and heuristic.get("domain"):
        result["domain"] = heuristic["domain"]

    if not result.get("phone") and heuristic.get("phone"):
        result["phone"] = heuristic["phone"]

    if not result.get("email") and heuristic.get("email"):
        result["email"] = heuristic["email"]

    if not result.get("education") and heuristic.get("education"):
        # Convert simple strings or lists from heuristic to the expected List[str]
        h_edu = heuristic.get("education")
        if isinstance(h_edu, list):
            result["education"] = h_edu
        elif isinstance(h_edu, str):
            result["education"] = [h_edu]

    # For complex list fields, we prefer LLM's structured raw/generic pairs.
    # If LLM returned nothing but heuristic found something, we can semi-populate.
    if not result.get("skills") and heuristic.get("skills"):
        result["skills"] = [{"raw": s, "generic": s.lower().replace(" ", "_")} for s in heuristic["skills"]]

    if not result.get("projects") and heuristic.get("projects"):
        result["projects"] = [{"raw": p, "generic_tags": []} for p in heuristic["projects"]]

    return result


def extract_candidate_name(text: str) -> str | None:
    return _extract_candidate_name(text)


def extract_candidate_role(text: str) -> str | None:
    return _extract_role(text)


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


def _resume_field_confidence(field_name: str, value: Any, evidence_value: Any) -> float:
    evidence_confidence = _review_average_confidence(evidence_value)

    if _review_is_missing(value):
        return 0.0

    if field_name == "candidate_name":
        token_count = len(str(value).split())
        heuristic = 0.94 if 2 <= token_count <= 4 else 0.72
        return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))

    if field_name == "role":
        heuristic = 0.84 if 1 <= len(str(value).split()) <= 8 else 0.62
        return _clamp_confidence((heuristic * 0.55) + (evidence_confidence * 0.45))

    if field_name == "total_experience_years":
        try:
            years = int(value)
        except (TypeError, ValueError):
            years = None
        heuristic = 0.86 if years is not None and 0 <= years <= 45 else 0.35
        return _clamp_confidence((heuristic * 0.65) + (evidence_confidence * 0.35))

    if field_name == "skills":
        count = len(value or [])
        if count >= 5:
            heuristic = 0.92
        elif count >= 3:
            heuristic = 0.82
        elif count >= 1:
            heuristic = 0.58
        else:
            heuristic = 0.0
        return _clamp_confidence((heuristic * 0.7) + (evidence_confidence * 0.3))

    if isinstance(value, list):
        heuristic = 0.72 if value else 0.0
        return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))

    heuristic = 0.72 if str(value).strip() else 0.0
    return _clamp_confidence((heuristic * 0.6) + (evidence_confidence * 0.4))


def build_resume_review_payload(
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
        confidence = _resume_field_confidence(field_name, value, (evidence_map or {}).get(field_name))
        is_critical = field_name in RESUME_CRITICAL_FIELDS
        if is_critical and _review_is_missing(value):
            missing_critical_fields.append(field_name)

        fields[field_name] = {
            "value": value,
            "confidence": confidence,
            "evidence_page": evidence.get("page"),
            "evidence_text": evidence.get("source_text"),
            "is_critical": is_critical,
        }

        if is_critical and confidence < RESUME_REVIEW_THRESHOLD:
            issues.append(f"low_confidence_{field_name}")

    if missing_critical_fields:
        for field_name in missing_critical_fields:
            issues.append(f"missing_{field_name}")

    if extraction_backend and "ocr" in extraction_backend.lower():
        issues.append("ocr_used")

    normalized_text = (text or "").strip()
    if len(normalized_text) < 400:
        issues.append("limited_extracted_text")

    skill_count = len(structured_data.get("skills") or [])
    if skill_count < 2:
        issues.append("sparse_skills")

    scored_fields = [field["confidence"] for field in fields.values() if field["value"] not in (None, "", [])]
    overall_confidence = sum(scored_fields) / len(scored_fields) if scored_fields else 0.0

    if "ocr_used" in issues:
        overall_confidence -= 0.12
    if "limited_extracted_text" in issues:
        overall_confidence -= 0.08
    if "sparse_skills" in issues:
        overall_confidence -= 0.06
    if missing_critical_fields:
        overall_confidence -= 0.10 * len(missing_critical_fields)

    overall_confidence = _clamp_confidence(overall_confidence)
    recommended_review = (
        overall_confidence < RESUME_REVIEW_THRESHOLD
        or bool(missing_critical_fields)
        or "ocr_used" in issues
        or "sparse_skills" in issues
    )

    return {
        "fields": fields,
        "overall_confidence": overall_confidence,
        "issues": list(dict.fromkeys(issues)),
        "missing_critical_fields": missing_critical_fields,
        "recommended_review": recommended_review,
        "raw_profile": structured_data or {},
    }
