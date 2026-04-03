from functools import lru_cache

from app.llm.provider import llm_json_extract
from app.llm.schemas import TenderRequirements


@lru_cache(maxsize=128)
def extract_tender_requirements_llm(text: str) -> TenderRequirements:
    prompt = f"""
You are a production-grade Tender Analyst for a Hiring-Resume Matching System.

Goal:
Standardize hiring or project requirements from tender text into a deterministic JSON format to enable SQL matching.

Tasks:

1. Extract core requirements: role, domain, summary, skills_required, preferred_skills, experience_required, qualifications, and responsibilities.

2. Generate an "executive summary" (2-3 sentences) of the overall requirement.

3. Provide "summary_for_matching" containing "must_store_generic_values" representing the standardized IDs for matching.

4. For role, domain, skills, and qualifications, you MUST generate both "raw" (original phrase) and "generic" (normalized) values.

5. Generic Normalization Rules:
- Lowercase, underscore_separated, no punctuation, no duplicates.
- Map surface forms to a single canonical concept.
- Examples: 
  "M.Tech in Structures", "Master of Structural Engineering" -> "structural_engineering_master"
  "Python Developer", "Coding in Python" -> "python_programming"
  "HOD Roads", "Project Director highway" -> "highway_project_director"
  "Road projects", "Expressways", "National Highways" -> "road_transport_infrastructure"

6. Experience: Convert "10+ years", "Minimum 10 years" to integer 10.

Tender text (truncated if necessary):
{text[:200000]}

Return only valid JSON matching the provided schema.
"""

    raw_json = llm_json_extract(
        prompt=prompt,
        schema=TenderRequirements.model_json_schema(),
        task="extraction",
    )

    return TenderRequirements.model_validate_json(raw_json)
