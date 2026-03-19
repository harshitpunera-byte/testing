from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.connection import Base, EMBEDDING_DIM
from app.database.vector import PGVECTOR_INSTALLED, vector_column_type


json_type = JSON().with_variant(JSONB, "postgresql")
vector_type = vector_column_type(EMBEDDING_DIM)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("document_type", "file_hash", name="uq_documents_type_hash"),
        Index("ix_documents_document_type_status", "document_type", "processing_status"),
        Index("ix_documents_file_hash", "file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), default="processing", nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    markdown_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    structured_data_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)
    evidence_map_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    resume_profile: Mapped["ResumeProfile | None"] = relationship(
        "ResumeProfile",
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )
    field_evidence: Mapped[list["FieldEvidence"]] = relationship(
        "FieldEvidence",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_id", name="uq_document_chunks_doc_chunk"),
        Index("ix_document_chunks_document_chunk", "document_id", "chunk_index"),
        Index("ix_document_chunks_section_title", "section_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), default="semantic", nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)
    embedding_backend: Mapped[str] = mapped_column(String(64), default="pgvector", nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(vector_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")


class ResumeProfile(Base, TimestampMixin):
    __tablename__ = "resume_profiles"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_resume_profiles_document_id"),
        Index("ix_resume_profiles_normalized_title", "normalized_title"),
        Index("ix_resume_profiles_total_experience_months", "total_experience_months"),
        Index("ix_resume_profiles_notice_period_days", "notice_period_days"),
        Index("ix_resume_profiles_location_city", "location_city"),
        Index("ix_resume_profiles_current_ctc", "current_ctc"),
        Index("ix_resume_profiles_expected_ctc", "expected_ctc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevant_experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_ctc: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_ctc: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    highest_education: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_tags: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_profile_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="resume_profile")
    skills: Mapped[list["ResumeSkill"]] = relationship(
        "ResumeSkill",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    experiences: Mapped[list["ResumeExperience"]] = relationship(
        "ResumeExperience",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list["ResumeProject"]] = relationship(
        "ResumeProject",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    education_rows: Mapped[list["ResumeEducation"]] = relationship(
        "ResumeEducation",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    certifications: Mapped[list["ResumeCertification"]] = relationship(
        "ResumeCertification",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    evidence_rows: Mapped[list["FieldEvidence"]] = relationship(
        "FieldEvidence",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    search_index: Mapped["ResumeSearchIndex | None"] = relationship(
        "ResumeSearchIndex",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ResumeSkill(Base):
    __tablename__ = "resume_skills"
    __table_args__ = (
        Index("ix_resume_skills_resume_profile_id", "resume_profile_id"),
        Index("ix_resume_skills_skill_name_normalized", "skill_name_normalized"),
        Index("ix_resume_skills_profile_skill", "resume_profile_id", "skill_name_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False)
    skill_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_name_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    years_used_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_used_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proficiency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="skills")


class ResumeExperience(Base):
    __tablename__ = "resume_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_tags: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="experiences")


class ResumeProject(Base):
    __tablename__ = "resume_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tech_stack: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="projects")


class ResumeEducation(Base):
    __tablename__ = "resume_education"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    degree: Mapped[str | None] = mapped_column(String(255), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="education_rows")


class ResumeCertification(Base):
    __tablename__ = "resume_certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    certification_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_json: Mapped[dict] = mapped_column(json_type, default=dict, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="certifications")


class FieldEvidence(Base):
    __tablename__ = "field_evidence"
    __table_args__ = (
        Index("ix_field_evidence_document_id", "document_id"),
        Index("ix_field_evidence_resume_profile_id", "resume_profile_id"),
        Index("ix_field_evidence_field_name", "field_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    resume_profile_id: Mapped[int | None] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="field_evidence")
    resume_profile: Mapped[ResumeProfile | None] = relationship("ResumeProfile", back_populates="evidence_rows")


class ResumeSearchIndex(Base):
    __tablename__ = "resume_search_index"
    __table_args__ = (
        UniqueConstraint("resume_profile_id", name="uq_resume_search_index_profile_id"),
        Index("ix_resume_search_index_normalized_title", "normalized_title"),
        Index("ix_resume_search_index_location_city", "location_city"),
        Index("ix_resume_search_index_total_experience_months", "total_experience_months"),
        Index("ix_resume_search_index_notice_period_days", "notice_period_days"),
        Index("ix_resume_search_index_current_ctc", "current_ctc"),
        Index("ix_resume_search_index_expected_ctc", "expected_ctc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False)
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevant_experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_ctc: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_ctc: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    highest_education: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skills_normalized: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    domains: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    companies: Mapped[list | dict] = mapped_column(json_type, default=list, nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fulltext_tsv: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_embedding: Mapped[list[float] | None] = mapped_column(vector_type, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    resume_profile: Mapped[ResumeProfile] = relationship("ResumeProfile", back_populates="search_index")
