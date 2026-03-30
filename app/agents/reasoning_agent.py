from typing import Dict, List


def _build_candidate_reasoning(match: Dict) -> str:
    filename = match.get("filename", "unknown.pdf")
    score = match.get("score", 0)
    verdict = match.get("verdict", "Unknown")
    matched_skills = match.get("matched_skills", [])
    missing_skills = match.get("missing_skills", [])
    candidate_experience = match.get("candidate_experience")
    required_experience = match.get("required_experience")
    experience_match = match.get("experience_match", False)
    disqualifiers = match.get("disqualifiers", [])
    comparison_mismatches = match.get("comparison_mismatches", [])

    reasons: List[str] = []

    if disqualifiers:
        reasons.append(
            "This appears to be a false positive because "
            + "; ".join(disqualifiers)
            + "."
        )

    if matched_skills:
        reasons.append(
            f"{filename} matches these required skills: {', '.join(matched_skills)}."
        )
    else:
        reasons.append(
            f"{filename} does not match any of the extracted required skills."
        )

    if experience_match:
        reasons.append(
            f"Experience requirement is satisfied because the candidate has {candidate_experience} years against the required {required_experience} years."
        )
    else:
        if required_experience is not None and candidate_experience is not None:
            reasons.append(
                f"Experience requirement is not satisfied because the candidate has {candidate_experience} years but the tender requires {required_experience} years."
            )
        else:
            reasons.append(
                "Experience comparison could not be fully validated from the extracted text."
            )

    if missing_skills:
        reasons.append(
            f"Missing or not detected skills: {', '.join(missing_skills)}."
        )
    else:
        reasons.append("No required skills are missing based on current extraction.")

    if comparison_mismatches and not disqualifiers:
        reasons.append(
            "Important context mismatches were also detected: "
            + "; ".join(comparison_mismatches)
            + "."
        )

    reasons.append(f"Overall suitability score is {score}% and verdict is {verdict}.")

    return " ".join(reasons)


def reasoning_agent(state: Dict) -> Dict:
    matches = state.get("matches", [])

    enriched_matches = []
    shortlist = []
    rejected = []

    for match in matches:
        explanation = _build_candidate_reasoning(match)

        enriched_match = {
            **match,
            "reasoning": explanation
        }
        enriched_matches.append(enriched_match)

        if match.get("score", 0) >= 80 and match.get("experience_match", False):
            shortlist.append(match.get("filename", "unknown.pdf"))
        elif match.get("score", 0) < 50:
            rejected.append(match.get("filename", "unknown.pdf"))

    summary_parts = []
    valid_matches = [
        match for match in enriched_matches
        if match.get("eligibility_intent_match", True)
    ]

    if valid_matches:
        best = valid_matches[0]
        summary_parts.append(
            f"Top candidate is {best.get('filename', 'unknown.pdf')} with score {best.get('score', 0)}%."
        )
    elif enriched_matches:
        summary_parts.append(
            "No valid candidate match was found; retrieved resumes only had superficial keyword overlap."
        )
    else:
        summary_parts.append("No matching resumes were found.")

    if shortlist:
        summary_parts.append(
            f"Shortlisted candidates: {', '.join(shortlist)}."
        )

    if rejected:
        summary_parts.append(
            f"Low suitability candidates: {', '.join(rejected)}."
        )

    summary = " ".join(summary_parts)

    return {
        **state,
        "matches": enriched_matches,
        "reasoning_summary": summary
    }
