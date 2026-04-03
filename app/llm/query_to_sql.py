import re
from app.llm.provider import llm_text_answer


SQL_PROMPT = """
YOU ARE A PRODUCTION-GRADE POSTGRESQL QUERY GENERATION ENGINE.

You convert a user's natural language resume search request into ONE safe PostgreSQL SELECT query.

==================================================
OBJECTIVE
==================================================
Translate the user's query into a valid PostgreSQL query for filtering candidate resumes.

The query MUST return EXACTLY these 3 columns in this exact order:
1. resume_profiles.id
2. resume_profiles.candidate_name
3. documents.id AS document_id

==================================================
DATABASE SCHEMA
==================================================

Table: documents
- id (Integer, primary_key)
- document_type (String: 'resume' or 'tender')
- processing_status (String: 'stored', 'processing', etc)

Table: resume_profiles
- id (Integer, primary_key)
- document_id (ForeignKey to documents.id)
- candidate_name (String)
- normalized_title (String)
- location_city (String)
- total_experience_months (Integer)
- notice_period_days (Integer)
- highest_education (String)

Table: resume_search_index
- id (Integer, primary_key)
- resume_profile_id (ForeignKey to resume_profiles.id)
- skills_normalized (JSONB array of strings)
- domains (JSONB array of strings)
- summary_text (Text)

Table: resume_skills
- id (Integer, primary_key)
- resume_profile_id (ForeignKey to resume_profiles.id)
- skill_name_normalized (String)

Table: resume_education
- id (Integer, primary_key)
- resume_profile_id (ForeignKey to resume_profiles.id)
- degree (String)
- generic_key (String)

==================================================
MANDATORY OUTPUT SQL SHAPE
==================================================
The query MUST start EXACTLY with:

SELECT DISTINCT resume_profiles.id, resume_profiles.candidate_name, documents.id AS document_id
FROM resume_profiles
JOIN documents ON documents.id = resume_profiles.document_id

==================================================
MANDATORY BASE FILTER
==================================================
The query MUST include this filter in the WHERE clause:

documents.processing_status = 'stored'
AND documents.document_type = 'resume'

==================================================
MAPPING RULES
==================================================

1. Skills
If the user asks for one or more skills, use EXISTS against resume_skills.
Example pattern:
EXISTS (
    SELECT 1
    FROM resume_skills
    WHERE resume_skills.resume_profile_id = resume_profiles.id
      AND resume_skills.skill_name_normalized = 'python'
)

- For multiple required skills, use multiple EXISTS with AND.
- For alternative skills ("python or java"), use OR between EXISTS blocks.
- Prefer resume_skills over JSONB skills_normalized for exact skill filtering.

2. Qualifications / Education
If the user asks for degree/qualification filters, use EXISTS against resume_education.generic_key when the value is normalized.

CRITICAL MAPPING:
The database uses strict canonical abbreviations, NOT full words or varying combinations.
You MUST map semantic requests to these exact strings:
- "btech": Bachelor of Technology / B.Tech / B.E / B-Tech
- "mtech": Master of Technology / M.Tech
- "me": Master of Engineering / M.E
- "bsc": Bachelor of Science / B.Sc / BS
- "msc": Master of Science / M.Sc / MS / Masters
- "bca": Bachelor of Computer Applications
- "mca": Master of Computer Applications
- "mba": Master of Business Administration
- "be": Bachelor of Engineering
- "diploma": Diploma variants
- "phd": Doctor of Philosophy

If the user asks a broad category like "masters", use an IN clause picking the appropriate master degrees:
EXISTS (
    SELECT 1
    FROM resume_education
    WHERE resume_education.resume_profile_id = resume_profiles.id
      AND resume_education.generic_key IN ('mtech', 'me', 'msc', 'mca', 'mba')
)

If the user asks for "bachelors", use:
`resume_education.generic_key IN ('btech', 'bsc', 'bca', 'be')`

If only raw education wording is clearly intended and no generic form is available, you may use degree with ILIKE conservatively.

3. Role / Title
Use:
resume_profiles.normalized_title = 'python_backend_developer'
or ILIKE only if the query is clearly non-normalized and exact normalized value is uncertain.

Prefer exact match when the role is clearly canonical.

4. Location
Use:
resume_profiles.location_city ILIKE '%delhi%'
or exact equality if clearly appropriate.

5. Experience
Convert years to months.
Examples:
- 1 year  -> 12
- 2 years -> 24
- 3 years -> 36

Use:
resume_profiles.total_experience_months >= 36

6. Notice Period
Use:
resume_profiles.notice_period_days <= 30
or similar numeric comparison based on the user query.

7. Domains
For domain filtering, use EXISTS with resume_search_index and JSONB containment where appropriate.
Example:
EXISTS (
    SELECT 1
    FROM resume_search_index
    WHERE resume_search_index.resume_profile_id = resume_profiles.id
      AND resume_search_index.domains @> '["road_transport_infrastructure"]'::jsonb
)

8. Summary / keyword fallback
Use resume_search_index.summary_text ILIKE only when a request cannot be mapped reliably to structured filters.
Use this conservatively, not as the first choice.

==================================================
STRICT SAFETY RULES
==================================================
- Return ONLY one raw SQL SELECT statement.
- Do NOT return markdown.
- Do NOT return backticks.
- Do NOT return explanations.
- Do NOT use DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE.
- Do NOT generate multiple statements.
- Do NOT include comments.
- Do NOT use SELECT *.
- Do NOT query tender documents.
- Do NOT omit the mandatory base filter.
- Prefer structured filters over summary_text search.
- If the user query is vague, return the base query with the mandatory filters and LIMIT 100.
- Always append LIMIT 100 unless the user explicitly asks for a smaller limit.

==================================================
LOGIC RULES
==================================================
- Translate only explicit or strongly implied filters.
- Do not invent ranking formulas.
- Do not hallucinate unavailable columns.
- Do not assume missing filters.
- Use AND when the user wants all conditions satisfied.
- Use OR only when the user explicitly asks for alternatives.
- Keep SQL simple, readable, and deterministic.

==================================================
USER QUERY
==================================================
{query}
"""


FORBIDDEN_SQL_PATTERNS = [
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"--",
    r"/\*",
    r"\*/",
]


REQUIRED_SQL_START = (
    "SELECT DISTINCT resume_profiles.id, resume_profiles.candidate_name, documents.id AS document_id\n"
    "FROM resume_profiles\n"
    "JOIN documents ON documents.id = resume_profiles.document_id"
)


REQUIRED_WHERE_PARTS = [
    "documents.processing_status = 'stored'",
    "documents.document_type = 'resume'",
]


def _strip_code_fences(response: str) -> str:
    response = response.strip()

    if response.startswith("```sql"):
        response = response[len("```sql"):].strip()
    elif response.startswith("```"):
        response = response[len("```"):].strip()

    if response.endswith("```"):
        response = response[:-3].strip()

    return response


def _normalize_sql(sql: str) -> str:
    sql = sql.strip()

    # Remove trailing semicolons and extra whitespace
    sql = re.sub(r";+\s*$", "", sql.strip())

    # Normalize repeated blank lines
    sql = re.sub(r"\n{3,}", "\n\n", sql)

    return sql.strip()


def _validate_sql(sql: str) -> None:
    upper_sql = sql.upper()

    if not upper_sql.startswith("SELECT DISTINCT RESUME_PROFILES.ID, RESUME_PROFILES.CANDIDATE_NAME, DOCUMENTS.ID AS DOCUMENT_ID"):
        raise ValueError(
            "Generated SQL does not start with the required SELECT clause."
        )

    if "FROM RESUME_PROFILES" not in upper_sql:
        raise ValueError("Generated SQL is missing FROM resume_profiles.")

    if "JOIN DOCUMENTS ON DOCUMENTS.ID = RESUME_PROFILES.DOCUMENT_ID" not in upper_sql:
        raise ValueError("Generated SQL is missing the required documents join.")

    for required_part in REQUIRED_WHERE_PARTS:
        if required_part.upper() not in upper_sql:
            raise ValueError(f"Generated SQL is missing required filter: {required_part}")

    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, sql, flags=re.IGNORECASE):
            raise ValueError(f"Generated SQL contains forbidden pattern: {pattern}")

    # Ensure single statement only
    if ";" in sql:
        raise ValueError("Generated SQL must contain only one statement.")

    # Prevent SELECT *
    if re.search(r"SELECT\s+\*", sql, flags=re.IGNORECASE):
        raise ValueError("Generated SQL must not use SELECT *.")


def _ensure_limit(sql: str, default_limit: int = 100) -> str:
    if re.search(r"\bLIMIT\s+\d+\b", sql, flags=re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {default_limit}"


def _fallback_sql() -> str:
    return """SELECT DISTINCT resume_profiles.id, resume_profiles.candidate_name, documents.id AS document_id
FROM resume_profiles
JOIN documents ON documents.id = resume_profiles.document_id
WHERE documents.processing_status = 'stored'
  AND documents.document_type = 'resume'
LIMIT 100"""


def generate_sql_for_query(query: str) -> str:
    user_query = (query or "").strip()

    if not user_query:
        return _fallback_sql()

    prompt = SQL_PROMPT.format(query=user_query)
    response = llm_text_answer(prompt)

    if not response or not response.strip():
        return _fallback_sql()

    sql = _strip_code_fences(response)
    sql = _normalize_sql(sql)
    sql = _ensure_limit(sql)

    try:
        _validate_sql(sql)
        return sql
    except Exception:
        return _fallback_sql()