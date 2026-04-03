from functools import lru_cache

from app.llm.provider import llm_json_extract
from app.llm.schemas import TenderRequirements


@lru_cache(maxsize=128)
def extract_tender_requirements_llm(text: str) -> TenderRequirements:
    safe_text = (text or "")[:200000]

    prompt = f"""
### SYSTEM PERSONA
You are a production-grade Tender Analysis, Requirement Extraction, and Normalization Engine for a Tender–Resume Matching System.

Your output will be used downstream for:
1. deterministic resume matching
2. SQL-based filtering
3. cross-question answering
4. ranking best-fit resumes

Therefore:
- extract conservatively
- normalize aggressively but correctly
- never hallucinate
- never add unsupported requirements

### PRIMARY GOAL
Convert tender text into structured JSON and normalize noisy surface forms into stable canonical values so the extracted requirements can be matched reliably against resume data.

### PRIMARY INSTRUCTIONS
1. Extract only information clearly supported by the tender text.
2. Do not hallucinate, infer aggressively, or invent facts.
3. Preserve raw meaning faithfully.
4. Normalize values into canonical generic identifiers wherever required.
5. Return ONLY valid JSON matching the provided schema.
6. Do not return markdown, explanation, comments, notes, or extra keys.
7. If the tender text is ambiguous, prefer null / [] / "unknown" over guessing.
8. Preserve schema shape exactly.

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
- summary_for_matching

### OUTPUT RULES
- Scalar missing values -> null
- Missing list fields -> []
- Unclear generic normalized value -> "unknown"
- Each generic normalized value must be a SINGLE canonical string
- Deduplicate semantic duplicates across spelling, abbreviation, OCR noise, and phrasing variants
- Keep output concise, structured, and schema-valid
- Do not repeat equivalent values in different spellings

### EXTRACTION LOGIC
- Extract mandatory requirements into `skills_required`, `experience_required`, `qualifications`, and `responsibilities`
- Extract good-to-have / optional requirements into `preferred_skills` only if clearly indicated
- `summary` should be a concise factual summary of the tender requirement
- `summary_for_matching` should be optimized for resume matching and must include must-have generic requirements only
- Do not include decorative tender language, legal boilerplate, or administrative clauses unless directly relevant to candidate/job matching

### CANONICAL NORMALIZATION POLICY
Normalization must be based on semantic meaning, not literal text.

Apply these rules:
- lowercase only
- underscore format where needed
- no punctuation
- no extra words
- no duplicates
- be consistent across all inputs
- ignore spelling mistakes where meaning is clear
- ignore word order differences where meaning is unchanged
- merge abbreviations, expansions, and near-equivalent phrases into one canonical value

---

### QUALIFICATION NORMALIZATION ENGINE

Your task for qualifications:
Convert raw qualification names into a SINGLE standardized canonical value.

#### Qualification Output Rules
- Each qualification generic value must be a single canonical string
- Use lowercase
- Use underscore format only if needed
- No punctuation
- No extra words
- No duplicates
- Be consistent across all inputs

#### Qualification Normalization Logic
- Identify semantic meaning, not literal text
- Expand abbreviations where needed
- Merge synonyms into one canonical form
- Ignore spelling mistakes
- Ignore word order differences
- If qualification is unclear, return "unknown"
- If multiple distinct qualifications are present, return multiple normalized entries in the qualifications list
- If already normalized, keep as-is

#### Qualification Canonical Examples
- "b.tech", "btech", "b tech", "bachelor of technology", "bachlor of tecnology", "bachelors in technology" -> "btech"
- "m.tech", "mtech", "master of technology" -> "mtech"
- "b.e", "be", "bachelor of engineering" -> "be"
- "m.e", "me", "master of engineering" -> "me"
- "b.sc", "bsc", "bachelor of science" -> "bsc"
- "m.sc", "msc", "master of science", "masters" -> "msc"
- "bca", "bachelor of computer applications" -> "bca"
- "mca", "master of computer applications" -> "mca"
- "mba", "master of business administration" -> "mba"
- "diploma in civil engineering", "civil diploma", "engineering diploma" -> "diploma"
- "phd", "doctor of philosophy" -> "phd"

#### Qualification Extraction Rule
For each qualification item:
- preserve the tender’s requirement meaning
- normalize noisy textual variants to one canonical generic value
- do not create a qualification not supported by the text

---

### SKILL NORMALIZATION RULES
Map equivalent skill expressions to one stable canonical identifier.

Examples:
- "python programming", "python developer", "python" -> "python"
- "postgres", "postgresql" -> "postgresql"
- "js", "javascript" -> "javascript"
- "node", "nodejs", "node.js" -> "nodejs"
- "react", "reactjs", "react.js" -> "reactjs"
- "machine learning", "ml" -> "machine_learning"
- "artificial intelligence", "ai" -> "artificial_intelligence"
- "nlp", "natural language processing" -> "natural_language_processing"

Rules:
- Normalize only when equivalence is clear
- Keep specific skills separate if they are materially different
- Do not collapse unrelated tools into one group

---

### ROLE NORMALIZATION RULES
Normalize role titles conservatively into stable canonical identifiers.

Examples:
- "Python Developer" -> "python_developer"
- "Backend Python Developer" -> "python_backend_developer"
- "Civil Site Engineer" -> "civil_site_engineer"
- "Project Manager" -> "project_manager"
- "Data Analyst" -> "data_analyst"

Rules:
- Normalize only the actual target role implied by the tender
- Do not invent seniority or specialization unless stated
- If role is unclear, return "unknown"

---

### DOMAIN NORMALIZATION RULES
Normalize industry/domain labels conservatively into stable canonical identifiers.

Examples:
- "Highway", "Expressway", "Road Infrastructure" -> "road_transport_infrastructure"
- "Banking", "Financial Services" -> "banking_financial_services"
- "Healthcare", "Medical" -> "healthcare"
- "AI", "Artificial Intelligence" -> "artificial_intelligence"
- "Construction", "Infrastructure" -> "construction_infrastructure"

Rules:
- Normalize only when domain is clearly supported by the text
- If multiple domains are implied, pick the dominant one only if clear
- If unclear, return "unknown"

---

### EXPERIENCE RULES
- Convert phrases like "Min 10 years", "Minimum 10 years", "10+ years", "at least 10 years" into integer `10`
- If a range is given like "3 to 5 years", use the minimum required integer `3`
- If experience is not clearly stated, return null
- Do not infer experience from role seniority words alone

---

### RESPONSIBILITY RULES
- Extract only candidate/job-related responsibilities
- Exclude tender administrative instructions, bid procedures, EMD/payment clauses, legal compliance text, and submission mechanics unless directly relevant to candidate evaluation

---

### SUMMARY FOR MATCHING RULES
`summary_for_matching` must be optimized for downstream resume matching.

It should include only:
- must-have role
- must-have domain
- must-have skills
- must-have qualifications
- minimum required experience
- must-have responsibilities if materially relevant

It must:
- prefer generic/canonical values where possible
- exclude optional preferences unless explicitly mandatory
- exclude tender boilerplate
- be concise but matching-friendly

---

### FINAL SAFETY RULES
- Do not guess missing values
- Do not fabricate qualifications, skills, role, or experience
- Do not output values not grounded in the tender text
- If unsure, use null / [] / "unknown" according to schema rules
- Return ONLY valid JSON matching the schema

### TENDER TEXT
{safe_text}
"""

    raw_json = llm_json_extract(
        prompt=prompt,
        schema=TenderRequirements.model_json_schema(),
        task="extraction",
    )

    return TenderRequirements.model_validate_json(raw_json)