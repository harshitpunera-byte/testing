"""human in the loop review layer

Revision ID: 20260319_0002
Revises: 20260319_0001
Create Date: 2026-03-19 21:45:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260319_0002"
down_revision = "20260319_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def table_exists(table_name: str) -> bool:
        return table_name in inspector.get_table_names(schema="public")

    def column_names(table_name: str) -> set[str]:
        return {column["name"] for column in inspector.get_columns(table_name)}

    def index_names(table_name: str) -> set[str]:
        return {index["name"] for index in inspector.get_indexes(table_name)}

    existing_document_columns = column_names("documents")
    if "reviewed_data_json" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("reviewed_data_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if "review_status" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default="not_needed"),
        )
    if "auto_approved" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "approved_by" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("approved_by", sa.String(length=255), nullable=True),
        )
    if "approved_at" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("approved_at", sa.DateTime(), nullable=True),
        )
    if "has_human_corrections" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("has_human_corrections", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "extraction_confidence" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("extraction_confidence", sa.Float(), nullable=True),
        )
    if "canonical_data_ready" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("canonical_data_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "uses_review_queue" not in existing_document_columns:
        op.add_column(
            "documents",
            sa.Column("uses_review_queue", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "ix_documents_review_status" not in index_names("documents"):
        op.create_index("ix_documents_review_status", "documents", ["review_status"])

    if not table_exists("review_tasks"):
        op.create_table(
            "review_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_type", sa.String(length=32), nullable=False),
            sa.Column("task_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
            sa.Column("assigned_to", sa.String(length=255), nullable=True),
            sa.Column("review_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "ix_review_tasks_document_status" not in index_names("review_tasks"):
        op.create_index("ix_review_tasks_document_status", "review_tasks", ["document_id", "status"])
    if "ix_review_tasks_document_type_status" not in index_names("review_tasks"):
        op.create_index("ix_review_tasks_document_type_status", "review_tasks", ["document_type", "status"])
    if "ix_review_tasks_task_type_status" not in index_names("review_tasks"):
        op.create_index("ix_review_tasks_task_type_status", "review_tasks", ["task_type", "status"])
    if "ix_review_tasks_priority" not in index_names("review_tasks"):
        op.create_index("ix_review_tasks_priority", "review_tasks", ["priority"])

    if not table_exists("review_items"):
        op.create_table(
            "review_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("review_task_id", sa.Integer(), sa.ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field_name", sa.String(length=128), nullable=False),
            sa.Column("extracted_value", JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("corrected_value", JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("evidence_page", sa.Integer(), nullable=True),
            sa.Column("evidence_text", sa.Text(), nullable=True),
            sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "ix_review_items_task_status" not in index_names("review_items"):
        op.create_index("ix_review_items_task_status", "review_items", ["review_task_id", "review_status"])
    if "ix_review_items_field_name" not in index_names("review_items"):
        op.create_index("ix_review_items_field_name", "review_items", ["field_name"])

    if not table_exists("match_feedback"):
        op.create_table(
            "match_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tender_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("resume_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("system_score", sa.Float(), nullable=True),
            sa.Column("human_decision", sa.String(length=32), nullable=False),
            sa.Column("reason_code", sa.String(length=128), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.String(length=255), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "ix_match_feedback_tender_resume" not in index_names("match_feedback"):
        op.create_index("ix_match_feedback_tender_resume", "match_feedback", ["tender_document_id", "resume_document_id"])
    if "ix_match_feedback_human_decision" not in index_names("match_feedback"):
        op.create_index("ix_match_feedback_human_decision", "match_feedback", ["human_decision"])

    if not table_exists("field_change_audit"):
        op.create_table(
            "field_change_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field_name", sa.String(length=128), nullable=False),
            sa.Column("old_value", JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("new_value", JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("changed_by", sa.String(length=255), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("source", sa.String(length=64), nullable=False),
        )
    if "ix_field_change_audit_document_field" not in index_names("field_change_audit"):
        op.create_index("ix_field_change_audit_document_field", "field_change_audit", ["document_id", "field_name"])
    if "ix_field_change_audit_changed_at" not in index_names("field_change_audit"):
        op.create_index("ix_field_change_audit_changed_at", "field_change_audit", ["changed_at"])


def downgrade() -> None:
    op.drop_table("field_change_audit")
    op.drop_table("match_feedback")
    op.drop_table("review_items")
    op.drop_table("review_tasks")
    op.drop_index("ix_documents_review_status", table_name="documents")
    op.drop_column("documents", "uses_review_queue")
    op.drop_column("documents", "canonical_data_ready")
    op.drop_column("documents", "extraction_confidence")
    op.drop_column("documents", "has_human_corrections")
    op.drop_column("documents", "approved_at")
    op.drop_column("documents", "approved_by")
    op.drop_column("documents", "auto_approved")
    op.drop_column("documents", "review_status")
    op.drop_column("documents", "reviewed_data_json")
