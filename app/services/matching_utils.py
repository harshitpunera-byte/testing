from __future__ import annotations
import re
import json
from typing import Any, Dict, List

# Synonym Mappings for Qualifications
QUALIFICATION_MAP = {
    "btech": "engineering_bachelor",
    "be": "engineering_bachelor",
    "b.tech": "engineering_bachelor",
    "b.e.": "engineering_bachelor",
    "mtech": "engineering_master",
    "me": "engineering_master",
    "m.tech": "engineering_master",
    "mba": "business_administration_master",
    "bca": "computer_applications_bachelor",
    "mca": "computer_applications_master",
    "bsc": "science_bachelor",
    "msc": "science_master",
}

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
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

def map_synonyms(value: str, mapping: Dict[str, str]) -> str:
    """Map a value to its canonical form if exists."""
    normalized = normalize_value(value)
    # Check if the normalized value or its variations exist in mapping
    clean_val = normalized.replace("_", "")
    if clean_val in mapping:
        return mapping[clean_val]
    return normalized

def extract_structured_requirements(tender_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes raw tender extraction into structured requirements.
    """
    reqs = {
        "role": normalize_value(tender_data.get("role", "")),
        "required_skills": [normalize_value(s) for s in tender_data.get("skills_required", [])],
        "preferred_skills": [normalize_value(s) for s in tender_data.get("preferred_skills", [])],
        "min_experience": tender_data.get("experience_required", 0),
        "domain": map_synonyms(tender_data.get("domain", ""), DOMAIN_MAP),
        "qualifications": [map_synonyms(q, QUALIFICATION_MAP) for q in tender_data.get("qualifications", [])],
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
        where_clauses.append(f"resumes.experience_years >= {reqs['min_experience']}")
        
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
        
    # Qualifications (Using IN if multiple)
    if reqs["qualifications"]:
        quals_str = ", ".join([f"'{q}'" for q in reqs["qualifications"]])
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM resume_qualifications rq WHERE rq.resume_id = resumes.id AND rq.qualification_group IN ({quals_str}))"
        )

    query = "SELECT resumes.* FROM resumes"
    if where_clauses:
        query += "\nWHERE " + "\n  AND ".join(where_clauses)
        
    return query
