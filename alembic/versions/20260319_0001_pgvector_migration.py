"""pgvector production schema

Revision ID: 20260319_0001
Revises: None
Create Date: 2026-03-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260319_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("extraction_method", sa.String(length=64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("markdown_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("structured_data_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_map_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_type", "file_hash", name="uq_documents_type_hash"),
    )
    op.create_index("ix_documents_document_type", "documents", ["document_type"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_processing_status", "documents", ["processing_status"])
    op.create_index("ix_documents_document_type_status", "documents", ["document_type", "processing_status"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=32), nullable=False),
        sa.Column("section_title", sa.String(length=128), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding_backend", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "chunk_id", name="uq_document_chunks_doc_chunk"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_document_chunk", "document_chunks", ["document_id", "chunk_index"])
    op.create_index("ix_document_chunks_section_title", "document_chunks", ["section_title"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_ivfflat "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("location_city", sa.String(length=128), nullable=True),
        sa.Column("location_state", sa.String(length=128), nullable=True),
        sa.Column("location_country", sa.String(length=128), nullable=True),
        sa.Column("current_company", sa.String(length=255), nullable=True),
        sa.Column("current_role", sa.String(length=255), nullable=True),
        sa.Column("normalized_title", sa.String(length=255), nullable=True),
        sa.Column("total_experience_months", sa.Integer(), nullable=True),
        sa.Column("relevant_experience_months", sa.Integer(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=True),
        sa.Column("current_ctc", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_ctc", sa.Numeric(12, 2), nullable=True),
        sa.Column("highest_education", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("domain_tags", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("raw_profile_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", name="uq_resume_profiles_document_id"),
    )
    op.create_index("ix_resume_profiles_normalized_title", "resume_profiles", ["normalized_title"])
    op.create_index("ix_resume_profiles_total_experience_months", "resume_profiles", ["total_experience_months"])
    op.create_index("ix_resume_profiles_notice_period_days", "resume_profiles", ["notice_period_days"])
    op.create_index("ix_resume_profiles_location_city", "resume_profiles", ["location_city"])
    op.create_index("ix_resume_profiles_current_ctc", "resume_profiles", ["current_ctc"])
    op.create_index("ix_resume_profiles_expected_ctc", "resume_profiles", ["expected_ctc"])

    op.create_table(
        "resume_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_name_raw", sa.String(length=255), nullable=False),
        sa.Column("skill_name_normalized", sa.String(length=255), nullable=False),
        sa.Column("skill_category", sa.String(length=64), nullable=True),
        sa.Column("years_used_months", sa.Integer(), nullable=True),
        sa.Column("last_used_year", sa.Integer(), nullable=True),
        sa.Column("proficiency_score", sa.Float(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("source_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_resume_skills_resume_profile_id", "resume_skills", ["resume_profile_id"])
    op.create_index("ix_resume_skills_skill_name_normalized", "resume_skills", ["skill_name_normalized"])
    op.create_index("ix_resume_skills_profile_skill", "resume_skills", ["resume_profile_id", "skill_name_normalized"])

    for table_name in ["resume_experiences", "resume_projects", "resume_education", "resume_certifications"]:
        pass

    op.create_table(
        "resume_experiences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("normalized_job_title", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain_tags", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("source_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "resume_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("tech_stack", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("source_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "resume_education",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("degree", sa.String(length=255), nullable=True),
        sa.Column("specialization", sa.String(length=255), nullable=True),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("grade", sa.String(length=64), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("source_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "resume_certifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("certification_name", sa.String(length=255), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("source_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "field_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("section_name", sa.String(length=128), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_field_evidence_document_id", "field_evidence", ["document_id"])
    op.create_index("ix_field_evidence_resume_profile_id", "field_evidence", ["resume_profile_id"])
    op.create_index("ix_field_evidence_field_name", "field_evidence", ["field_name"])

    op.create_table(
        "resume_search_index",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_profile_id", sa.Integer(), sa.ForeignKey("resume_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=True),
        sa.Column("normalized_title", sa.String(length=255), nullable=True),
        sa.Column("location_city", sa.String(length=128), nullable=True),
        sa.Column("total_experience_months", sa.Integer(), nullable=True),
        sa.Column("relevant_experience_months", sa.Integer(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=True),
        sa.Column("current_ctc", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_ctc", sa.Numeric(12, 2), nullable=True),
        sa.Column("highest_education", sa.String(length=255), nullable=True),
        sa.Column("skills_normalized", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("domains", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("companies", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("fulltext_tsv", sa.Text(), nullable=True),
        sa.Column("summary_embedding", Vector(384), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("resume_profile_id", name="uq_resume_search_index_profile_id"),
    )
    op.create_index("ix_resume_search_index_normalized_title", "resume_search_index", ["normalized_title"])
    op.create_index("ix_resume_search_index_location_city", "resume_search_index", ["location_city"])
    op.create_index("ix_resume_search_index_total_experience_months", "resume_search_index", ["total_experience_months"])
    op.create_index("ix_resume_search_index_notice_period_days", "resume_search_index", ["notice_period_days"])
    op.create_index("ix_resume_search_index_current_ctc", "resume_search_index", ["current_ctc"])
    op.create_index("ix_resume_search_index_expected_ctc", "resume_search_index", ["expected_ctc"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_summary_embedding_ivfflat "
        "ON resume_search_index USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_fulltext "
        "ON resume_search_index USING gin (to_tsvector('english', coalesce(summary_text, '')))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_skills_gin "
        "ON resume_search_index USING gin (skills_normalized)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_domains_gin "
        "ON resume_search_index USING gin (domains)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_metadata_gin "
        "ON documents USING gin (metadata_json)"
    )


def downgrade() -> None:
    for table in [
        "resume_search_index",
        "field_evidence",
        "resume_certifications",
        "resume_education",
        "resume_projects",
        "resume_experiences",
        "resume_skills",
        "resume_profiles",
        "document_chunks",
        "documents",
    ]:
        op.drop_table(table)
