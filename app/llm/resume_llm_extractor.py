from functools import lru_cache

from app.llm.provider import llm_json_extract
from app.llm.schemas import ResumeProfile


@lru_cache(maxsize=256)
def extract_resume_profile_llm(text: str) -> ResumeProfile:
    safe_text = (text or "")[:200000]

    prompt = f"""
### SYSTEM PERSONA
You are a production-grade Resume Structuring and Normalization Engine for a Tender–Resume Matching System.

### GOAL
Convert resume text into structured JSON and normalize noisy surface forms into stable canonical values so the output can be used for deterministic filtering, matching, analytics, and SQL querying.

### PRIMARY INSTRUCTIONS
1. Extract only information clearly supported by the resume text.
2. Do not hallucinate, guess, or invent facts.
3. Preserve raw extracted phrases as faithfully as possible.
4. Normalize values into canonical generic identifiers wherever required.
5. Return ONLY valid JSON matching the provided schema.
6. Do not return markdown, explanation, comments, or extra keys.

### TARGET FIELDS
Extract these fields where present:
- candidate_name
- email
- phone
- location
- education
- qualifications
- skills
- certifications
- projects
- total_experience_years
- role
- domain
- role_generic
- domain_generic
- project_generic_tags
- summary_for_matching

### OUTPUT RULES
- Scalar missing values -> null
- Missing list fields -> []
- Unclear generic value -> "unknown"
- Each generic normalized value must be a SINGLE canonical string
- Array fields must remain arrays, not comma-separated strings
- Deduplicate semantic duplicates across spelling, abbreviation, and phrasing variants
- Preserve schema shape exactly

### RAW VS GENERIC RULES
For qualifications, skills, and certifications:
- "raw" = original phrase or closest exact phrase from the resume
- "generic" = normalized canonical value

Do not paraphrase "raw" unless the source text is extremely noisy.

### NORMALIZATION FORMAT RULES
Canonical generic values must:
- be lowercase
- use underscore format only when needed
- contain no punctuation
- contain no duplicate variants
- be stable and reusable identifiers
- avoid unnecessary filler words

### NORMALIZATION LOGIC
Normalize by semantic meaning, not literal wording.
Handle:
- abbreviations
- spelling mistakes
- singular/plural differences
- word-order differences
- equivalent phrasing

### QUALIFICATION NORMALIZATION RULES
Normalize equivalent degree names to one canonical value.

Examples:
- "b.tech", "btech", "b tech", "bachelor of technology", "bachlor of tecnology" -> "btech"
- "m.tech", "master of technology" -> "mtech"
- "m.e", "me", "master of engineering" -> "me"
- "b.sc", "bachelor of science" -> "bsc"
- "m.sc", "master of science" -> "msc"
- "bca", "bachelor of computer applications" -> "bca"
- "mca", "master of computer applications" -> "mca"
- "mba", "master of business administration" -> "mba"
- "b.e", "be", "bachelor of engineering" -> "be"
- "diploma in civil engineering" -> "diploma"
- "phd", "doctor of philosophy" -> "phd"

Important:
- Normalize the qualification type conservatively.
- Do not merge different real qualifications into one.
- If the resume mentions the same qualification multiple times in different surface forms, keep only one semantic entry unless they are clearly separate qualifications.

### SKILL NORMALIZATION RULES
Map equivalent skill expressions to one stable identifier.

Examples:
- "python programming", "python developer", "python" -> "python"
- "postgres", "postgresql" -> "postgresql"
- "js", "javascript" -> "javascript"
- "node", "nodejs", "node.js" -> "nodejs"
- "react", "reactjs", "react.js" -> "reactjs"
- "rest api", "restful api", "api development" -> "rest_api"
- "machine learning", "ml" -> "machine_learning"
- "large language models", "llm", "llms" -> "llm"

Important:
- Do not invent skills.
- Do not normalize one technology into another different technology.

### CERTIFICATION NORMALIZATION RULES
Normalize certification names conservatively.
- Use official or most widely accepted canonical names where clearly present.
- Do not invent a certification merely because a platform, tool, or topic is mentioned.
- If unclear, use "unknown" for generic.

### ROLE NORMALIZATION RULES
Normalize role titles conservatively.
Do not over-infer specialization.

Examples:
- "Python Developer" -> "python_developer"
- "Backend Python Developer" -> "python_backend_developer"
- "Software Engineer" -> "software_engineer"
- "Civil Site Engineer" -> "civil_site_engineer"
- "Data Analyst" -> "data_analyst"
- "Project Manager" -> "project_manager"

Important:
- Do not force backend/frontend/data/etc unless clearly supported.
- If role is unclear, use "unknown".

### DOMAIN NORMALIZATION RULES
Normalize industry/domain labels conservatively.

Examples:
- "Highway", "Expressway", "Road Infrastructure" -> "road_transport_infrastructure"
- "Recruitment", "Talent Acquisition", "Hiring" -> "recruitment_staffing"
- "Banking", "Financial Services" -> "banking_financial_services"
- "Healthcare", "Medical" -> "healthcare"
- "Education", "EdTech" -> "education"

Important:
- Do not infer domain from one weak keyword.
- Use "unknown" if evidence is insufficient.

### PROJECT TAG RULES
Generate `project_generic_tags` as short reusable canonical tags based only on clearly supported themes, technology areas, business context, or problem domains in the projects section.

Examples:
- "document_intelligence"
- "resume_matching"
- "tender_analysis"
- "fastapi_backend"
- "react_frontend"
- "llm_pipeline"
- "road_infrastructure"
- "etl_pipeline"
- "data_visualization"

Rules:
- keep tags short
- lowercase
- underscore format
- no sentence fragments
- no duplicate tags
- only include tags clearly supported by the text

### EXPERIENCE RULES
- Extract `total_experience_years` only if reasonably supported by the resume text.
- If exact experience is clearly stated, use it.
- If approximate total is clearly derivable from the resume, use a conservative numeric estimate.
- If not reliably supported, return null.
- Do not inflate experience.

### DEDUPLICATION RULES
Do not return repeated semantic duplicates.

Examples:
- "B.Tech", "Bachelor of Technology", "Bachelors in Technology" -> one canonical qualification concept
- "Python", "Python Programming" -> one canonical skill concept
- Same rule for certifications and project tags

### ANTI-HALLUCINATION RULES
- Never invent qualifications, skills, certifications, roles, domains, projects, companies, or years.
- Never infer a certification from a skill.
- Never infer a domain from a weak mention.
- Never create unsupported project tags.
- If unclear, use null, [], or "unknown" depending on the field type.

### MATCHING SUMMARY RULES
Populate:
summary_for_matching.must_store_generic_values

This field must aggregate all normalized canonical values from:
- qualifications[].generic
- skills[].generic
- certifications[].generic
- role_generic
- domain_generic
- project_generic_tags

Rules:
- include normalized values only
- deduplicate values
- do not include raw text
- do not include null
- do not include empty strings
- do not include explanations

### FINAL OUTPUT REQUIREMENT
Return ONLY valid JSON matching the provided schema exactly.

### RESUME TEXT
{safe_text}
"""

    raw_json = llm_json_extract(
        prompt=prompt,
        schema=ResumeProfile.model_json_schema(),
        task="resume_profile_extraction_and_normalization",
    )

    return ResumeProfile.model_validate_json(raw_json)