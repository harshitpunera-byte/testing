from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import selectinload

from app.database.connection import session_scope
from app.models.db_models import (
    Document,
    DocumentChunk,
    FieldEvidence,
    FieldChangeAudit,
    MatchFeedback,
    ReviewItem,
    ReviewTask,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProfile,
    ResumeProject,
    ResumeSearchIndex,
    ResumeSkill,
)


def _canonical_structured_payload(document: Document) -> dict:
    if document.canonical_data_ready and document.reviewed_data_json:
        return document.reviewed_data_json or {}
    return document.structured_data_json or {}


def _document_to_dict(document: Document | None) -> dict | None:
    if document is None:
        return None

    return {
        "id": document.id,
        "document_type": document.document_type,
        "file_name": document.file_name,
        "original_filename": document.original_file_name,
        "stored_filename": document.file_name,
        "stored_path": document.stored_path,
        "file_hash": document.file_hash,
        "file_size": document.file_size,
        "mime_type": document.mime_type,
        "status": document.processing_status,
        "processing_status": document.processing_status,
        "total_pages": (document.metadata_json or {}).get("total_pages"),
        "extraction_backend": document.extraction_method,
        "structured_data": document.structured_data_json or {},
        "structured_data_json": document.structured_data_json or {},
        "reviewed_data": document.reviewed_data_json or {},
        "reviewed_data_json": document.reviewed_data_json or {},
        "canonical_structured_data": _canonical_structured_payload(document),
        "evidence_map": document.evidence_map_json or {},
        "evidence_map_json": document.evidence_map_json or {},
        "metadata_json": document.metadata_json or {},
        "review_status": document.review_status,
        "auto_approved": document.auto_approved,
        "approved_by": document.approved_by,
        "approved_at": document.approved_at,
        "has_human_corrections": document.has_human_corrections,
        "extraction_confidence": document.extraction_confidence,
        "canonical_data_ready": document.canonical_data_ready,
        "uses_review_queue": document.uses_review_queue,
        "review_summary": (document.metadata_json or {}).get("review_summary", {}),
        "review_issues": ((document.metadata_json or {}).get("review_summary", {}) or {}).get("issues", []),
        "raw_text": document.raw_text or "",
        "markdown_text": document.markdown_text or "",
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _chunk_to_dict(chunk: DocumentChunk, original_filename: str | None = None, document_type: str | None = None) -> dict:
    metadata = chunk.metadata_json or {}
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "chunk_index": chunk.chunk_index,
        "index_name": document_type or metadata.get("document_type"),
        "chunk_id": chunk.chunk_id,
        "text": chunk.content,
        "chunk_text": chunk.content,
        "section": chunk.section_title,
        "section_title": chunk.section_title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "embedding_backend": chunk.embedding_backend,
        "filename": metadata.get("filename", original_filename),
        "document_type": metadata.get("document_type", document_type),
        "metadata_json": metadata,
        "embedding": list(chunk.embedding) if chunk.embedding is not None else None,
    }


def _profile_to_dict(profile: ResumeProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "document_id": profile.document_id,
        "candidate_name": profile.candidate_name,
        "email": profile.email,
        "phone": profile.phone,
        "location_city": profile.location_city,
        "location_state": profile.location_state,
        "location_country": profile.location_country,
        "current_company": profile.current_company,
        "current_role": profile.current_role,
        "normalized_title": profile.normalized_title,
        "total_experience_months": profile.total_experience_months,
        "relevant_experience_months": profile.relevant_experience_months,
        "notice_period_days": profile.notice_period_days,
        "current_ctc": float(profile.current_ctc) if profile.current_ctc is not None else None,
        "expected_ctc": float(profile.expected_ctc) if profile.expected_ctc is not None else None,
        "highest_education": profile.highest_education,
        "summary": profile.summary,
        "domain_tags": profile.domain_tags or [],
        "confidence_score": profile.confidence_score,
        "raw_profile_json": profile.raw_profile_json or {},
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def get_document_by_hash(document_type: str, file_hash: str) -> dict | None:
    with session_scope() as db:
        document = db.scalar(
            select(Document).where(
                Document.document_type == document_type,
                Document.file_hash == file_hash,
            )
        )
        return _document_to_dict(document)


def get_document_by_id(document_id: int) -> dict | None:
    with session_scope() as db:
        document = db.scalar(select(Document).where(Document.id == document_id))
        return _document_to_dict(document)


def get_document_by_original_filename(document_type: str, original_filename: str) -> dict | None:
    with session_scope() as db:
        document = db.scalar(
            select(Document)
            .where(
                Document.document_type == document_type,
                Document.original_file_name == original_filename,
            )
            .order_by(desc(Document.updated_at), desc(Document.created_at))
        )
        return _document_to_dict(document)


def get_documents_by_ids(document_ids: list[int]) -> list[dict]:
    ordered_ids = []
    seen = set()
    for value in document_ids:
        try:
            document_id = int(value)
        except (TypeError, ValueError):
            continue
        if document_id in seen:
            continue
        seen.add(document_id)
        ordered_ids.append(document_id)

    if not ordered_ids:
        return []

    with session_scope() as db:
        documents = db.scalars(select(Document).where(Document.id.in_(ordered_ids))).all()

    documents_by_id = {document.id: _document_to_dict(document) for document in documents}
    return [documents_by_id[document_id] for document_id in ordered_ids if document_id in documents_by_id]


def get_latest_document(document_type: str) -> dict | None:
    with session_scope() as db:
        document = db.scalar(
            select(Document)
            .where(Document.document_type == document_type, Document.processing_status == "stored")
            .order_by(desc(Document.updated_at), desc(Document.created_at))
        )
        return _document_to_dict(document)


def create_document_record(**fields) -> dict:
    with session_scope() as db:
        metadata_json = dict(fields.pop("metadata_json", {}) or {})
        total_pages = fields.pop("total_pages", None)
        if total_pages is not None:
            metadata_json["total_pages"] = total_pages

        document = Document(
            document_type=fields["document_type"],
            file_name=fields.get("stored_filename") or fields.get("file_name"),
            original_file_name=fields.get("original_filename") or fields.get("original_file_name"),
            file_hash=fields["file_hash"],
            stored_path=fields["stored_path"],
            mime_type=fields.get("mime_type"),
            file_size=fields["file_size"],
            processing_status=fields.get("status", fields.get("processing_status", "processing")),
            extraction_method=fields.get("extraction_backend", fields.get("extraction_method")),
            raw_text=fields.get("raw_text", ""),
            markdown_text=fields.get("markdown_text", ""),
            structured_data_json=fields.get("structured_data", fields.get("structured_data_json", {})) or {},
            reviewed_data_json=fields.get("reviewed_data", fields.get("reviewed_data_json", {})) or {},
            evidence_map_json=fields.get("evidence_map", fields.get("evidence_map_json", {})) or {},
            metadata_json=metadata_json,
            review_status=fields.get("review_status", "not_needed"),
            auto_approved=bool(fields.get("auto_approved", False)),
            approved_by=fields.get("approved_by"),
            approved_at=fields.get("approved_at"),
            has_human_corrections=bool(fields.get("has_human_corrections", False)),
            extraction_confidence=fields.get("extraction_confidence"),
            canonical_data_ready=bool(fields.get("canonical_data_ready", False)),
            uses_review_queue=bool(fields.get("uses_review_queue", False)),
        )
        db.add(document)
        db.flush()
        db.refresh(document)
        return _document_to_dict(document) or {}


def update_document_record(document_id: int, **fields) -> dict | None:
    with session_scope() as db:
        document = db.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            return None

        mapping = {
            "original_filename": "original_file_name",
            "stored_filename": "file_name",
            "status": "processing_status",
            "processing_status": "processing_status",
            "extraction_backend": "extraction_method",
            "extraction_method": "extraction_method",
            "structured_data": "structured_data_json",
            "structured_data_json": "structured_data_json",
            "reviewed_data": "reviewed_data_json",
            "reviewed_data_json": "reviewed_data_json",
            "evidence_map": "evidence_map_json",
            "evidence_map_json": "evidence_map_json",
            "raw_text": "raw_text",
            "markdown_text": "markdown_text",
            "mime_type": "mime_type",
            "stored_path": "stored_path",
            "file_size": "file_size",
            "review_status": "review_status",
            "auto_approved": "auto_approved",
            "approved_by": "approved_by",
            "approved_at": "approved_at",
            "has_human_corrections": "has_human_corrections",
            "extraction_confidence": "extraction_confidence",
            "canonical_data_ready": "canonical_data_ready",
            "uses_review_queue": "uses_review_queue",
        }

        for key, value in fields.items():
            if key == "total_pages":
                metadata = dict(document.metadata_json or {})
                metadata["total_pages"] = value
                document.metadata_json = metadata
                continue
            if key == "metadata_json":
                metadata = dict(document.metadata_json or {})
                metadata.update(value or {})
                document.metadata_json = metadata
                continue
            attr = mapping.get(key)
            if attr:
                setattr(document, attr, value)

        document.updated_at = datetime.utcnow()
        db.add(document)
        db.flush()
        db.refresh(document)
        return _document_to_dict(document)


def replace_document_chunks(
    document_id: int,
    index_name: str,
    chunks: Iterable[dict],
    embeddings: list[list[float]] | None = None,
) -> int:
    chunk_list = list(chunks)
    embeddings = embeddings or [None] * len(chunk_list)

    with session_scope() as db:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

        for index, chunk in enumerate(chunk_list):
            metadata = dict(chunk)
            metadata.pop("text", None)
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=index,
                    chunk_id=int(chunk.get("chunk_id", index)),
                    chunk_type=chunk.get("chunk_type", "semantic"),
                    section_title=chunk.get("section") or chunk.get("section_title"),
                    page_start=chunk.get("page_start"),
                    page_end=chunk.get("page_end"),
                    token_count=int(chunk.get("token_count", len(str(chunk.get("text", "")).split()))),
                    content=chunk.get("text", ""),
                    metadata_json=metadata,
                    embedding_backend=chunk.get("embedding_backend", "pgvector"),
                    embedding=embeddings[index],
                )
            )

        return len(chunk_list)


def get_persisted_document_chunks(document_id: int, limit: int | None = None) -> list[dict]:
    with session_scope() as db:
        rows = db.execute(
            select(DocumentChunk, Document.original_file_name, Document.document_type)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        ).all()

        if limit is not None:
            rows = rows[:limit]

        return [_chunk_to_dict(chunk, original_filename, document_type) for chunk, original_filename, document_type in rows]


def rename_document_chunks(document_id: int, filename: str) -> int:
    with session_scope() as db:
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document_id)).all()
        for chunk in chunks:
            metadata = dict(chunk.metadata_json or {})
            metadata["filename"] = filename
            chunk.metadata_json = metadata
            db.add(chunk)
        return len(chunks)


def get_index_chunks(index_name: str, document_id: int | None = None) -> list[dict]:
    with session_scope() as db:
        statement = (
            select(DocumentChunk, Document.original_file_name, Document.document_type)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.document_type == index_name, Document.processing_status == "stored")
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
            
        rows = db.execute(statement.order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())).all()
        return [_chunk_to_dict(chunk, original_filename, document_type) for chunk, original_filename, document_type in rows]


def delete_all_documents() -> dict[str, int]:
    with session_scope() as db:
        counts = {
            "documents_deleted": db.scalar(select(func.count()).select_from(Document)) or 0,
            "chunks_deleted": db.scalar(select(func.count()).select_from(DocumentChunk)) or 0,
            "resume_profiles_deleted": db.scalar(select(func.count()).select_from(ResumeProfile)) or 0,
            "evidence_deleted": db.scalar(select(func.count()).select_from(FieldEvidence)) or 0,
            "review_tasks_deleted": db.scalar(select(func.count()).select_from(ReviewTask)) or 0,
            "review_items_deleted": db.scalar(select(func.count()).select_from(ReviewItem)) or 0,
            "match_feedback_deleted": db.scalar(select(func.count()).select_from(MatchFeedback)) or 0,
            "field_change_audit_deleted": db.scalar(select(func.count()).select_from(FieldChangeAudit)) or 0,
        }

        db.execute(delete(ReviewItem))
        db.execute(delete(ReviewTask))
        db.execute(delete(MatchFeedback))
        db.execute(delete(FieldChangeAudit))
        db.execute(delete(FieldEvidence))
        db.execute(delete(ResumeSearchIndex))
        db.execute(delete(ResumeSkill))
        db.execute(delete(ResumeExperience))
        db.execute(delete(ResumeProject))
        db.execute(delete(ResumeEducation))
        db.execute(delete(ResumeCertification))
        db.execute(delete(ResumeProfile))
        db.execute(delete(DocumentChunk))
        db.execute(delete(Document))
        return {key: int(value) for key, value in counts.items()}


def purge_document_artifacts(document_id: int) -> None:
    with session_scope() as db:
        profile_ids = db.scalars(
            select(ResumeProfile.id).where(ResumeProfile.document_id == document_id)
        ).all()

        if profile_ids:
            db.execute(delete(FieldEvidence).where(FieldEvidence.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeSearchIndex).where(ResumeSearchIndex.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeSkill).where(ResumeSkill.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeExperience).where(ResumeExperience.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeProject).where(ResumeProject.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeEducation).where(ResumeEducation.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeCertification).where(ResumeCertification.resume_profile_id.in_(profile_ids)))
            db.execute(delete(ResumeProfile).where(ResumeProfile.id.in_(profile_ids)))

        db.execute(delete(FieldEvidence).where(FieldEvidence.document_id == document_id))
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))


def upsert_resume_profile(document_id: int, profile_payload: dict) -> dict:
    with session_scope() as db:
        profile = db.scalar(select(ResumeProfile).where(ResumeProfile.document_id == document_id))
        if profile is None:
            profile = ResumeProfile(document_id=document_id)
            db.add(profile)
            db.flush()

        for key, value in profile_payload.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        db.add(profile)
        db.flush()
        db.refresh(profile)
        return _profile_to_dict(profile) or {}


def replace_resume_skills(resume_profile_id: int, rows: list[dict]) -> int:
    with session_scope() as db:
        db.execute(delete(ResumeSkill).where(ResumeSkill.resume_profile_id == resume_profile_id))
        for row in rows:
            db.add(ResumeSkill(resume_profile_id=resume_profile_id, **row))
        return len(rows)


def replace_resume_experiences(resume_profile_id: int, rows: list[dict]) -> int:
    with session_scope() as db:
        db.execute(delete(ResumeExperience).where(ResumeExperience.resume_profile_id == resume_profile_id))
        for row in rows:
            db.add(ResumeExperience(resume_profile_id=resume_profile_id, **row))
        return len(rows)


def replace_resume_projects(resume_profile_id: int, rows: list[dict]) -> int:
    with session_scope() as db:
        db.execute(delete(ResumeProject).where(ResumeProject.resume_profile_id == resume_profile_id))
        for row in rows:
            db.add(ResumeProject(resume_profile_id=resume_profile_id, **row))
        return len(rows)


def replace_resume_education(resume_profile_id: int, rows: list[dict]) -> int:
    with session_scope() as db:
        db.execute(delete(ResumeEducation).where(ResumeEducation.resume_profile_id == resume_profile_id))
        for row in rows:
            db.add(ResumeEducation(resume_profile_id=resume_profile_id, **row))
        return len(rows)


def replace_resume_certifications(resume_profile_id: int, rows: list[dict]) -> int:
    with session_scope() as db:
        db.execute(delete(ResumeCertification).where(ResumeCertification.resume_profile_id == resume_profile_id))
        for row in rows:
            db.add(ResumeCertification(resume_profile_id=resume_profile_id, **row))
        return len(rows)


def replace_field_evidence(
    document_id: int,
    evidence_rows: list[dict],
    resume_profile_id: int | None = None,
) -> int:
    with session_scope() as db:
        statement = delete(FieldEvidence).where(FieldEvidence.document_id == document_id)
        if resume_profile_id is not None:
            statement = statement.where(FieldEvidence.resume_profile_id == resume_profile_id)
        db.execute(statement)
        for row in evidence_rows:
            db.add(FieldEvidence(document_id=document_id, resume_profile_id=resume_profile_id, **row))
        return len(evidence_rows)


def upsert_resume_search_index(resume_profile_id: int, payload: dict) -> dict:
    with session_scope() as db:
        row = db.scalar(select(ResumeSearchIndex).where(ResumeSearchIndex.resume_profile_id == resume_profile_id))
        if row is None:
            row = ResumeSearchIndex(resume_profile_id=resume_profile_id)
            db.add(row)
            db.flush()

        for key, value in payload.items():
            if hasattr(row, key):
                setattr(row, key, value)

        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        db.refresh(row)
        return {
            "id": row.id,
            "resume_profile_id": row.resume_profile_id,
            "candidate_name": row.candidate_name,
            "normalized_title": row.normalized_title,
        }


def get_resume_profile_by_document_id(document_id: int) -> dict | None:
    with session_scope() as db:
        profile = db.scalar(select(ResumeProfile).where(ResumeProfile.document_id == document_id))
        return _profile_to_dict(profile)


def get_resume_profile_with_relations(document_id: int) -> dict | None:
    with session_scope() as db:
        profile = db.scalar(
            select(ResumeProfile)
            .where(ResumeProfile.document_id == document_id)
            .options(
                selectinload(ResumeProfile.skills),
                selectinload(ResumeProfile.experiences),
                selectinload(ResumeProfile.projects),
                selectinload(ResumeProfile.education_rows),
                selectinload(ResumeProfile.certifications),
                selectinload(ResumeProfile.search_index),
            )
        )
        if profile is None:
            return None

        return {
            **(_profile_to_dict(profile) or {}),
            "skills": [
                {
                    "skill_name_raw": row.skill_name_raw,
                    "skill_name_normalized": row.skill_name_normalized,
                    "skill_category": row.skill_category,
                    "years_used_months": row.years_used_months,
                    "last_used_year": row.last_used_year,
                    "proficiency_score": row.proficiency_score,
                    "is_primary": row.is_primary,
                    "source_confidence": row.source_confidence,
                    "source_json": row.source_json or {},
                }
                for row in profile.skills
            ],
            "experiences": [
                {
                    "company_name": row.company_name,
                    "job_title": row.job_title,
                    "normalized_job_title": row.normalized_job_title,
                    "start_date": row.start_date.isoformat() if row.start_date else None,
                    "end_date": row.end_date.isoformat() if row.end_date else None,
                    "is_current": row.is_current,
                    "duration_months": row.duration_months,
                    "location": row.location,
                    "description": row.description,
                    "domain_tags": row.domain_tags or [],
                }
                for row in profile.experiences
            ],
            "projects": [
                {
                    "project_name": row.project_name,
                    "role": row.role,
                    "domain": row.domain,
                    "tech_stack": row.tech_stack or [],
                    "description": row.description,
                }
                for row in profile.projects
            ],
            "education": [
                {
                    "degree": row.degree,
                    "specialization": row.specialization,
                    "institution": row.institution,
                    "start_year": row.start_year,
                    "end_year": row.end_year,
                    "grade": row.grade,
                }
                for row in profile.education_rows
            ],
            "certifications": [
                {
                    "certification_name": row.certification_name,
                    "issuer": row.issuer,
                    "issued_at": row.issued_at.isoformat() if row.issued_at else None,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                }
                for row in profile.certifications
            ],
        }
