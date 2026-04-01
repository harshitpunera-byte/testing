from functools import lru_cache

from app.llm.provider import llm_json_extract
from app.llm.schemas import ResumeProfile


@lru_cache(maxsize=256)
def extract_resume_profile_llm(text: str) -> ResumeProfile:
    prompt = f"""
You are a production-grade Resume Structuring and Normalization Engine for a Tender–Resume Matching System.

Goal:
Convert the resume into structured JSON and assign canonical generic values for fields that may have multiple surface forms, so the data can later be matched deterministically against tender requirements using SQL.

Tasks:

1. Extract structured resume data in JSON with fields: candidate_name, email, phone, location, education, qualifications, skills, certifications, projects, total_experience_years, role, and domain.

2. For qualifications, skills, and certifications, generate both "raw" (original snippet) and "generic" (normalized) values.

3. Also generate generic normalized values for "role_generic", "domain_generic", and "project_generic_tags".

4. Generic Normalization Rules:
- Must be canonical, reusable, and SQL-friendly.
- Lowercase, underscore_separated, no punctuation, no duplicates.
- Map multiple surface forms to single business concept (semantic understanding).
- Examples: 
  "B.Tech", "Bachelor of Engineering" -> "engineering_bachelor"
  "Python Developer", "Backend Python Engineer" -> "python_backend_developer"
  "Postgres", "PostgreSQL" -> "postgresql"
  "Highway", "Expressway", "Road Project" -> "road_transport_infrastructure"

5. Populate a "summary_for_matching" object containing "must_store_generic_values" which aggregates all generic IDs/tags for skills, qualifications, certifications, projects, role, and domain.

Resume text:
{text}

Return only valid JSON matching the provided schema.
"""

    raw_json = llm_json_extract(
        prompt=prompt,
        schema=ResumeProfile.model_json_schema(),
        task="extraction",
    )

    return ResumeProfile.model_validate_json(raw_json)
