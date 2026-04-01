from typing import Any, List, Optional

from pydantic import BaseModel, Field


class TenderRequirements(BaseModel):
    role: Optional[str] = None
    role_generic: Optional[str] = None
    domain: Optional[str] = None
    domain_generic: Optional[str] = None
    skills_required: List[RawGenericItem] = Field(default_factory=list)
    preferred_skills: List[RawGenericItem] = Field(default_factory=list)
    experience_required: Optional[int] = None
    qualifications: List[RawGenericItem] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)


class RawGenericItem(BaseModel):
    raw: str = ""
    generic: str = ""


class ProjectItem(BaseModel):
    raw: str = ""
    generic_tags: List[str] = Field(default_factory=list)


class MustStoreGenericValues(BaseModel):
    skill_generic: List[str] = Field(default_factory=list)
    qualification_generic: List[str] = Field(default_factory=list)
    certification_generic: List[str] = Field(default_factory=list)
    project_generic: List[str] = Field(default_factory=list)
    role_generic: str = ""
    domain_generic: str = ""


class MatchingSummary(BaseModel):
    must_store_generic_values: MustStoreGenericValues


class ResumeProfile(BaseModel):
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    education: List[str] = Field(default_factory=list)
    qualifications: List[RawGenericItem] = Field(default_factory=list)
    skills: List[RawGenericItem] = Field(default_factory=list)
    certifications: List[RawGenericItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    total_experience_years: Optional[int] = None
    role: Optional[str] = None
    role_generic: Optional[str] = None
    domain: Optional[str] = None
    domain_generic: Optional[str] = None
    project_generic_tags: List[str] = Field(default_factory=list)
    summary_for_matching: MatchingSummary


class EvidenceRecord(BaseModel):
    value: Any = None
    source_text: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    confidence: float = 0.0
