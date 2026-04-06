from __future__ import annotations

import re
from typing import Any


TENDER_MARKER_GROUPS: dict[str, tuple[str, ...]] = {
    "request for proposals": ("request for proposals", "rfp"),
    "bidder selection": ("private entity as the bidder", "selection of a private entity as the bidder", "selected bidder"),
    "technical capacity": ("technical capacity",),
    "financial capacity": ("financial capacity", "net worth"),
    "bid security": ("bid security", "bank guarantee for bid security", "surety bond for bid security"),
    "consortium requirements": ("consortium", "joint bidding agreement"),
    "power of attorney": ("power of attorney",),
    "dbot execution": ("design, build, operate and transfer", "dbot", "hybrid annuity"),
}

RESUME_MARKER_GROUPS: dict[str, tuple[str, ...]] = {
    "technical proposal": ("technical proposal",),
    "proposed position": ("proposed position",),
    "name of staff": ("name of staff", "candidate name"),
    "name of firm": ("name of firm",),
    "date of birth": ("date of birth", "dob"),
    "consultant context": ("independent engineer services", "authority engineer", "consultancy services"),
}

INDIAN_STATES = (
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "orissa",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_token(token: str) -> str:
    token = "".join(char for char in str(token).lower() if char.isalnum())
    if token.endswith("s") and len(token) > 4:
        token = token[:-1]
    return token


def _tokenize_phrase(value: Any) -> set[str]:
    return {_normalize_token(token) for token in str(value or "").split() if _normalize_token(token)}


def _phrase_match(a: Any, b: Any) -> bool:
    if not a or not b:
        return False

    a_str = _normalize_text(a).lower()
    b_str = _normalize_text(b).lower()

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


def _marker_hits(text: str, marker_groups: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = _normalize_text(text).lower()
    hits: list[str] = []

    for label, phrases in marker_groups.items():
        if any(phrase in lowered for phrase in phrases):
            hits.append(label)

    return hits


def _extract_states(text: str) -> list[str]:
    lowered = _normalize_text(text).lower()
    states = []

    for state in INDIAN_STATES:
        if state in lowered:
            normalized = "Odisha" if state == "orissa" else state.title()
            if normalized not in states:
                states.append(normalized)

    return states


def _first_matching_line(text: str, predicates: tuple[str, ...], limit: int = 60) -> str | None:
    for raw_line in str(text or "").splitlines()[:limit]:
        line = _normalize_text(raw_line)
        if not line:
            continue
        lowered = line.lower()
        if any(predicate in lowered for predicate in predicates):
            return line[:220]
    return None


def _extract_tender_project_title(text: str) -> str | None:
    compact = _normalize_text(text)
    match = re.search(
        r"(construction of .{40,220}?(?:hybrid annuity mode|under nh\(o\)))",
        compact,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" .")

    return _first_matching_line(
        text,
        ("construction of", "request for proposals", "international competitive bidding"),
    )


def _extract_resume_project_title(text: str) -> str | None:
    return _first_matching_line(
        text,
        ("independent engineer services", "authority engineer", "consultancy services"),
    )


def infer_tender_document_intent(text: str, structured_data: dict | None = None) -> dict[str, Any]:
    marker_hits = _marker_hits(text, TENDER_MARKER_GROUPS)
    bidder_markers = {
        "bidder selection",
        "technical capacity",
        "financial capacity",
        "bid security",
        "consortium requirements",
        "power of attorney",
    }
    bidder_score = sum(1 for hit in marker_hits if hit in bidder_markers)

    category = "general_tender"
    summary = "The tender appears to be a general project requirements document."
    if bidder_score >= 2:
        category = "company_bidder_tender"
        summary = (
            "The tender is primarily a bidder/company procurement document for selecting "
            "a private entity or consortium, not an individual candidate."
        )

    return {
        "category": category,
        "summary": summary,
        "evidence": marker_hits[:6],
        "project_title": _extract_tender_project_title(text),
        "states": _extract_states(text),
        "role": (structured_data or {}).get("role"),
    }


def infer_resume_document_intent(text: str, structured_data: dict | None = None) -> dict[str, Any]:
    marker_hits = _marker_hits(text, RESUME_MARKER_GROUPS)
    has_candidate_name = bool((structured_data or {}).get("candidate_name"))
    consultant_markers = {"technical proposal", "consultant context", "name of firm"}
    consultant_score = sum(1 for hit in marker_hits if hit in consultant_markers)
    individual_score = sum(
        1
        for hit in marker_hits
        if hit in {"proposed position", "name of staff", "date of birth"}
    ) + (1 if has_candidate_name else 0)

    category = "resume_profile"
    summary = "The resume appears to be a candidate profile."
    if individual_score >= 2 and consultant_score >= 1:
        category = "individual_consultant_cv"
        summary = (
            "The resume is an individual consultant CV for a proposed engineering role, "
            "not a bidder/company profile."
        )
    elif individual_score >= 2:
        category = "individual_candidate_profile"
        summary = "The resume is an individual candidate profile rather than a company bid."

    return {
        "category": category,
        "summary": summary,
        "evidence": marker_hits[:6],
        "project_title": _extract_resume_project_title(text),
        "states": _extract_states(text),
        "role": (structured_data or {}).get("role"),
        "candidate_name": (structured_data or {}).get("candidate_name"),
    }


def compare_tender_and_resume(
    tender_text: str,
    resume_text: str,
    tender_data: dict | None = None,
    resume_data: dict | None = None,
) -> dict[str, Any]:
    tender_intent = infer_tender_document_intent(tender_text, tender_data)
    resume_intent = infer_resume_document_intent(resume_text, resume_data)

    similarities: list[str] = []
    mismatches: list[str] = []
    critical_mismatches: list[str] = []
    confusion_reasons: list[str] = []

    tender_data = tender_data or {}
    resume_data = resume_data or {}
    tender_lower = _normalize_text(tender_text).lower()
    resume_lower = _normalize_text(resume_text).lower()

    shared_checks = [
        ("Both documents are in the highways / road infrastructure domain.", ("highway", "road", "nh")),
        ("Both documents reference four-lane road work.", ("4 lane", "four lane", "4 lanning")),
        ("Both documents mention NHAI-related context.", ("nhai",)),
        ("Both documents reference Hybrid Annuity or HAM-style project delivery.", ("hybrid annuity",)),
        ("Both documents mention bridge / structural work in a road project context.", ("bridge", "structural")),
    ]

    for statement, terms in shared_checks:
        if any(term in tender_lower and term in resume_lower for term in terms):
            similarities.append(statement)

    tender_domain = tender_data.get("domain")
    resume_domain = resume_data.get("domain")
    if tender_domain and resume_domain and _phrase_match(tender_domain, resume_domain):
        similarities.append(f"Both documents point to a related domain: {tender_domain}.")

    tender_skills = tender_data.get("skills_required", []) or []
    resume_skills = resume_data.get("skills", []) or []
    shared_skills = [
        skill
        for skill in tender_skills
        if any(_phrase_match(skill, candidate_skill) for candidate_skill in resume_skills)
    ]
    for skill in shared_skills[:2]:
        similarities.append(f"There is topical overlap on {skill}.")

    if tender_intent["category"] == "company_bidder_tender" and resume_intent["category"] in {
        "individual_consultant_cv",
        "individual_candidate_profile",
        "resume_profile",
    }:
        message = (
            "The tender is for a bidder/company/consortium, while the resume is an "
            "individual profile."
        )
        mismatches.append(message)
        critical_mismatches.append(message)

    if tender_intent["category"] == "company_bidder_tender" and resume_intent["category"] == "individual_consultant_cv":
        message = (
            "The tender is in contractor/bidder execution context, while the resume is "
            "for a consultant / independent engineer role."
        )
        mismatches.append(message)
        critical_mismatches.append(message)

    tender_role = tender_intent.get("role")
    resume_role = resume_intent.get("role")
    if tender_role and resume_role and not _phrase_match(tender_role, resume_role):
        mismatches.append(
            f"Role mismatch: the tender focuses on {tender_role}, while the resume is for {resume_role}."
        )
    elif resume_role and tender_intent["category"] == "company_bidder_tender":
        mismatches.append(
            f"Role mismatch: the resume is for {resume_role}, but the tender is not framed as an individual hiring role."
        )

    tender_states = tender_intent.get("states", [])
    resume_states = resume_intent.get("states", [])
    if tender_states and resume_states and not set(tender_states) & set(resume_states):
        mismatches.append(
            f"State mismatch: the tender points to {', '.join(tender_states[:2])}, while the resume points to {', '.join(resume_states[:2])}."
        )

    tender_project = tender_intent.get("project_title")
    resume_project = resume_intent.get("project_title")
    if tender_project and resume_project and not _phrase_match(tender_project, resume_project):
        mismatches.append(
            "Project mismatch: the tender and the resume refer to different project assignments."
        )

    if tender_intent["category"] == "company_bidder_tender":
        eligibility_markers = [
            marker
            for marker in tender_intent.get("evidence", [])
            if marker in {"technical capacity", "financial capacity", "bid security", "consortium requirements", "power of attorney"}
        ]
        if eligibility_markers:
            mismatches.append(
                "Eligibility mismatch: the tender requires bidder-level capacity/compliance items such as "
                + ", ".join(eligibility_markers)
                + "."
            )
            critical_mismatches.append(
                "Bidder-level eligibility requirements cannot be satisfied by an individual resume alone."
            )

    shared_confusion_terms = [
        term
        for term in ("nhai", "hybrid annuity", "highway", "road", "bridge", "4 lane", "four lane")
        if term in tender_lower and term in resume_lower
    ]
    if shared_confusion_terms:
        confusion_reasons.append(
            "Keyword overlap likely came from shared terms such as "
            + ", ".join(dict.fromkeys(shared_confusion_terms))
            + "."
        )

    if tender_intent["category"] == "company_bidder_tender":
        confusion_reasons.append(
            "The tender was reduced to generic infrastructure skills instead of being treated as a bidder/company procurement document."
        )
    if resume_intent["category"] == "individual_consultant_cv":
        confusion_reasons.append(
            "The resume describes an individual consultant CV, which can look relevant semantically even when it is not a valid bidder match."
        )

    similarities = list(dict.fromkeys(similarities))[:5]
    mismatches = list(dict.fromkeys(mismatches))[:5]
    critical_mismatches = list(dict.fromkeys(critical_mismatches))
    confusion_reasons = list(dict.fromkeys(confusion_reasons))[:4]

    if critical_mismatches:
        verdict = "Not a Valid Match"
        is_valid_match = False
    elif mismatches:
        # Regular mismatches (role, state, etc.) no longer invalidate the entire match.
        # They just lower the verdict.
        verdict = "Partial Match with Mismatches"
        is_valid_match = True
    else:
        verdict = "Strong Match"
        is_valid_match = True

    if not similarities:
        similarities.append("Both documents are related to transport / highway infrastructure.")

    return {
        "tender_intent": tender_intent,
        "resume_intent": resume_intent,
        "similarities": similarities,
        "mismatches": mismatches,
        "critical_mismatches": critical_mismatches,
        "confusion_reasons": confusion_reasons,
        "verdict": verdict,
        "is_valid_match": is_valid_match,
    }
