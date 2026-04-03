from functools import lru_cache

from app.llm.provider import llm_json_extract
from app.llm.schemas import TenderRequirements


@lru_cache(maxsize=128)
def extract_tender_requirements_llm(text: str) -> TenderRequirements:
    safe_text = (text or "")[:200000]

    prompt = f"""
### SYSTEM PERSONA
You are a production-grade Tender Analysis and Normalization Engine for a Tender–Resume Matching System.

### GOAL
Convert tender text into structured JSON and normalize noisy surface forms into stable canonical values so the output can be matched deterministically against candidate resumes using SQL.

### PRIMARY INSTRUCTIONS
1. Extract only information clearly supported by the tender text.
2. Do not hallucinate, guess, or invent facts.
3. Preserve raw extracted phrases as faithfully as possible.
4. Normalize values into canonical generic identifiers wherever required.
5. Return ONLY valid JSON matching the provided schema.
6. Do not return markdown, explanation, comments, or extra keys.

### TARGET FIELDS
Extract these fields where present:
- role
- domain
- summary
- skills_required
- preferred_skills
- experience_required
- qualifications
- responsibilities
- role_generic
- domain_generic
- summary_for_matching (with must_store_generic_values)

### OUTPUT RULES
- Scalar missing values -> null
- Missing list fields -> []
- Unclear generic value -> "unknown"
- Each generic normalized value must be a SINGLE canonical string
- Deduplicate semantic duplicates across spelling, abbreviation, and phrasing variants
- Preserve schema shape exactly

### QUALIFICATION NORMALIZATION RULES
Normalize equivalent degree names to one canonical value.
Examples:
- "b.tech", "btech", "bachelor of technology" -> "btech"
- "m.tech", "master of technology" -> "mtech"
- "b.sc", "bachelor of science" -> "bsc"
- "m.sc", "master of science", "masters" -> "msc"
- "bca", "bachelor of computer applications" -> "bca"
- "mca", "master of computer applications" -> "mca"
- "mba", "master of business administration" -> "mba"
- "b.e", "be", "bachelor of engineering" -> "be"
- "diploma in civil engineering" -> "diploma"
- "phd", "doctor of philosophy" -> "phd"

### SKILL NORMALIZATION RULES
Map equivalent skill expressions to one stable identifier.
Examples:
- "python programming", "python developer", "python" -> "python"
- "postgres", "postgresql" -> "postgresql"
- "js", "javascript" -> "javascript"
- "node", "nodejs", "node.js" -> "nodejs"
- "react", "reactjs", "react.js" -> "reactjs"

### ROLE NORMALIZATION RULES
Normalize role titles conservatively.
Examples:
- "Python Developer" -> "python_developer"
- "Backend Python Developer" -> "python_backend_developer"
- "Civil Site Engineer" -> "civil_site_engineer"
- "Project Manager" -> "project_manager"

### DOMAIN NORMALIZATION RULES
Normalize industry/domain labels conservatively.
Examples:
- "Highway", "Expressway", "Road Infrastructure" -> "road_transport_infrastructure"
- "Banking", "Financial Services" -> "banking_financial_services"
- "Healthcare", "Medical" -> "healthcare"

### EXPERIENCE RULES
- `experience_required`: Convert phrases like "Min 10 years", "10+ years" into integer `10`.

### TENDER TEXT
{safe_text}
"""

    raw_json = llm_json_extract(
        prompt=prompt,
        schema=TenderRequirements.model_json_schema(),
        task="extraction",
    )

    return TenderRequirements.model_validate_json(raw_json)
