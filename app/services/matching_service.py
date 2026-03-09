from app.extraction.tender_extractor import extract_tender_requirements
from app.extraction.resume_extractor import extract_resume_data
from app.rag.retriever import search_resume_vectors


def match_resumes_with_tender(tender_text):

    tender_data = extract_tender_requirements(tender_text)

    matches = search_resume_vectors(tender_text)

    results = []

    for resume_text in matches:

        resume_data = extract_resume_data(resume_text)

        skill_matches = list(
            set(tender_data["skills_required"])
            & set(resume_data["skills"])
        )

        score = len(skill_matches) / max(
            1, len(tender_data["skills_required"])
        )

        results.append({
            "resume_excerpt": resume_text[:300],
            "matched_skills": skill_matches,
            "score": round(score * 100, 2)
        })

    return {
        "tender_requirements": tender_data,
        "matches": results
    }