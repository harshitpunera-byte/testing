import re
import json
from typing import Any, Dict, List, Optional
from app.database.connection import session_scope
from app.models.db_models import QualificationMaster, QualificationAlias

# Qualification mappings are now handled via database tables:
# qualification_master and qualification_alias.

# Domain Mappings
DOMAIN_MAP = {
    "highway": "road_transport_infrastructure",
    "road": "road_transport_infrastructure",
    "expressway": "road_transport_infrastructure",
    "bridge": "civil_infrastructure",
    "tunnel": "civil_infrastructure",
    "construction": "civil_works",
    "it": "information_technology",
    "software": "information_technology",
    "banking": "finance_and_banking",
}

def normalize_value(value: str) -> str:
    """Lowercase and clean special characters."""
    if not value: return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

def map_synonyms(value: str, mapping: Dict[str, str]) -> str:
    """Map a value to its canonical form if exists."""
    normalized = normalize_value(value)
    # Check if the normalized value or its variations exist in mapping
    clean_val = normalized.replace(" ", "_")
    if clean_val in mapping:
        return mapping[clean_val]
    return normalized

def resolve_qualification_generic_key(raw_value: str) -> Optional[str]:
    """Resolves raw qualification to a generic_key using the database."""
    normalized = normalize_value(raw_value)
    if not normalized: return None
    
    with session_scope() as session:
        # 1. Try direct match with generic_key
        master = session.get(QualificationMaster, normalized.replace(" ", "_"))
        if master: return master.generic_key
        
        # 2. Try match with aliases
        alias = session.query(QualificationAlias).filter(
            QualificationAlias.alias_value == normalized
        ).first()
        if alias: return alias.generic_key
        
    return None

def get_aliases_for_generic_key(generic_key: str) -> List[str]:
    """Fetches all aliases for a given generic_key."""
    with session_scope() as session:
        aliases = session.query(QualificationAlias.alias_value).filter(
            QualificationAlias.generic_key == generic_key
        ).all()
        return [a[0] for a in aliases]

def extract_structured_requirements(tender_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes raw tender extraction into structured requirements.
    """
    qualifications_raw = tender_data.get("qualifications", [])
    resolved_quals = []
    for item in qualifications_raw:
        # qualification is now a dict {"raw": "...", "generic": "..."}
        raw = item.get("raw") if isinstance(item, dict) else item
        generic = item.get("generic") if isinstance(item, dict) else None
        
        gkey = generic or resolve_qualification_generic_key(raw)
        if gkey:
            resolved_quals.append({
                "generic_key": gkey,
                "aliases": get_aliases_for_generic_key(gkey)
            })
        else:
            resolved_quals.append({
                "generic_key": None,
                "aliases": [normalize_value(raw)]
            })

    # Flatten skills for matching plan
    req_skills_raw = [s.get("generic") or normalize_value(s.get("raw")).replace(" ", "_") 
                      for s in tender_data.get("skills_required", []) if isinstance(s, dict)]
    pref_skills_raw = [s.get("generic") or normalize_value(s.get("raw")).replace(" ", "_") 
                       for s in tender_data.get("preferred_skills", []) if isinstance(s, dict)]

    reqs = {
        "role": tender_data.get("role_generic") or normalize_value(tender_data.get("role", "")),
        "required_skills": req_skills_raw,
        "preferred_skills": pref_skills_raw,
        "min_experience": tender_data.get("experience_required", 0),
        "domain": tender_data.get("domain_generic") or map_synonyms(tender_data.get("domain", ""), DOMAIN_MAP),
        "qualifications": resolved_quals,
    }
    
    # Ensure min_experience is an integer
    try:
        reqs["min_experience"] = int(reqs["min_experience"])
    except (ValueError, TypeError):
        reqs["min_experience"] = 0
        
    return reqs

def generate_matching_sql(reqs: Dict[str, Any]) -> str:
    """
    Generates a PostgreSQL query based on structured requirements.
    """
    where_clauses = []
    
    # Required Experience
    if reqs["min_experience"] > 0:
        where_clauses.append(f"resumes.total_experience_years >= {reqs['min_experience']}")
        
    # Domain matching (Flexible)
    if reqs["domain"]:
        where_clauses.append(f"resumes.domain ILIKE '%{reqs['domain']}%'")
        
    # Role matching (Flexible)
    if reqs["role"]:
        where_clauses.append(f"resumes.role ILIKE '%{reqs['role']}%'")
        
    # Required Skills (Using EXISTS for strict AND matching)
    for skill in reqs["required_skills"]:
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM resume_skills rs WHERE rs.resume_id = resumes.id AND rs.skill_name = '{skill}')"
        )
        
    # Qualifications (Filtering using generic_key or alias array)
    for qual in reqs["qualifications"]:
        if qual["generic_key"]:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM resume_education re WHERE re.resume_profile_id = resumes.id AND re.generic_key = '{qual['generic_key']}')"
            )
        else:
            # Fallback to aliases if no generic_key resolved
            aliases_str = ", ".join([f"'{a}'" for a in qual["aliases"]])
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM resume_education re WHERE re.resume_profile_id = resumes.id AND re.degree IN ({aliases_str}))"
            )

    query = "SELECT resumes.* FROM resumes"
    if where_clauses:
        query += "\nWHERE " + "\n  AND ".join(where_clauses)
        
    return query
