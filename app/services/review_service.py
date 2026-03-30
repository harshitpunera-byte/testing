from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import selectinload

from app.database.connection import session_scope
from app.extraction.resume_extractor import RESUME_REVIEW_THRESHOLD, build_resume_review_payload
from app.extraction.tender_extractor import TENDER_REVIEW_THRESHOLD, build_tender_review_payload
from app.models.db_models import Document, FieldChangeAudit, MatchFeedback, ReviewItem, ReviewTask
from app.services.document_repository import get_document_by_id, get_resume_profile_with_relations
from app.services.evidence_service import persist_evidence_map
from app.services.profile_normalizer import normalize_resume_profile


REVIEWABLE_TASK_STATUSES = {"pending", "in_review", "rejected"}
AUTO_APPROVAL_THRESHOLDS = {
    "resume": RESUME_REVIEW_THRESHOLD,
    "tender": TENDER_REVIEW_THRESHOLD,
}
TASK_TYPES = {
    "resume": "extraction_review",
    "tender": "tender_criteria_review",
}
PRIORITY_RANK = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def preferred_structured_data(document: dict | None) -> dict:
    if not document:
        return {}
    if document.get("canonical_data_ready") and document.get("reviewed_data"):
        return document.get("reviewed_data") or {}
    return document.get("structured_data") or {}


def document_uses_unreviewed_data(document: dict | None) -> bool:
    if not document:
        return True
    return not bool(document.get("canonical_data_ready"))


def evaluate_document_review(
    *,
    document_type: str,
    text: str,
    structured_data: dict[str, Any],
    evidence_map: dict[str, Any],
    extraction_backend: str | None = None,
) -> dict[str, Any]:
    if document_type == "resume":
        return build_resume_review_payload(
            text,
            structured_data,
            evidence_map,
            extraction_backend=extraction_backend,
        )

    return build_tender_review_payload(
        text,
        structured_data,
        evidence_map,
        extraction_backend=extraction_backend,
    )


def _task_priority(review_summary: dict[str, Any]) -> str:
    if review_summary.get("missing_critical_fields") or float(review_summary.get("overall_confidence", 0.0) or 0.0) < 0.60:
        return "high"
    if review_summary.get("recommended_review"):
        return "medium"
    return "low"


def _task_status_order(task: dict) -> tuple:
    return (
        PRIORITY_RANK.get(task.get("priority", "medium"), 9),
        -(task.get("created_at").timestamp() if task.get("created_at") else 0.0),
    )


def _serialize_review_item(item: ReviewItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "review_task_id": item.review_task_id,
        "field_name": item.field_name,
        "extracted_value": item.extracted_value,
        "corrected_value": item.corrected_value,
        "confidence": item.confidence,
        "evidence_page": item.evidence_page,
        "evidence_text": item.evidence_text,
        "is_critical": item.is_critical,
        "review_status": item.review_status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _serialize_review_task(task: ReviewTask) -> dict[str, Any]:
    document = task.document
    metadata_json = dict(document.metadata_json or {}) if document else {}
    review_summary = metadata_json.get("review_summary", {}) if metadata_json else {}
    return {
        "id": task.id,
        "document_id": task.document_id,
        "document_type": task.document_type,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "assigned_to": task.assigned_to,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "review_notes": task.review_notes,
        "document_name": document.original_file_name if document else None,
        "document_review_status": document.review_status if document else None,
        "extraction_confidence": document.extraction_confidence if document else None,
        "canonical_data_ready": document.canonical_data_ready if document else False,
        "issues": review_summary.get("issues", []),
    }


def _document_summary(document: Document) -> dict[str, Any]:
    metadata_json = dict(document.metadata_json or {})
    review_summary = metadata_json.get("review_summary", {})
    return {
        "id": document.id,
        "document_type": document.document_type,
        "file_name": document.file_name,
        "original_file_name": document.original_file_name,
        "stored_path": document.stored_path,
        "status": document.processing_status,
        "review_status": document.review_status,
        "auto_approved": document.auto_approved,
        "approved_by": document.approved_by,
        "approved_at": document.approved_at,
        "has_human_corrections": document.has_human_corrections,
        "extraction_confidence": document.extraction_confidence,
        "canonical_data_ready": document.canonical_data_ready,
        "uses_review_queue": document.uses_review_queue,
        "structured_data": document.structured_data_json or {},
        "reviewed_data": document.reviewed_data_json or {},
        "canonical_structured_data": (document.reviewed_data_json or {}) if document.canonical_data_ready and document.reviewed_data_json else (document.structured_data_json or {}),
        "evidence_map": document.evidence_map_json or {},
        "metadata_json": metadata_json,
        "review_summary": review_summary,
        "raw_text_preview": (document.raw_text or "")[:1500],
    }


def _upsert_review_task(
    db,
    *,
    document: Document,
    review_summary: dict[str, Any],
) -> ReviewTask:
    task = db.scalar(
        select(ReviewTask)
        .where(
            ReviewTask.document_id == document.id,
            ReviewTask.task_type == TASK_TYPES[document.document_type],
            ReviewTask.status.in_(REVIEWABLE_TASK_STATUSES),
        )
        .order_by(desc(ReviewTask.updated_at), desc(ReviewTask.created_at))
    )

    if task is None:
        task = ReviewTask(
            document_id=document.id,
            document_type=document.document_type,
            task_type=TASK_TYPES[document.document_type],
        )
        db.add(task)
        db.flush()

    task.status = "pending"
    task.priority = _task_priority(review_summary)
    task.review_notes = None
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.flush()

    db.execute(delete(ReviewItem).where(ReviewItem.review_task_id == task.id))

    for field_name, field in (review_summary.get("fields") or {}).items():
        value = field.get("value")
        if value in (None, "", []) and not field.get("is_critical"):
            continue

        db.add(
            ReviewItem(
                review_task_id=task.id,
                field_name=field_name,
                extracted_value=value,
                corrected_value=None,
                confidence=field.get("confidence"),
                evidence_page=field.get("evidence_page"),
                evidence_text=field.get("evidence_text"),
                is_critical=bool(field.get("is_critical")),
                review_status="pending",
            )
        )

    return task


def sync_document_review_state(
    *,
    document_id: int,
    document_type: str,
    text: str,
    structured_data: dict[str, Any],
    evidence_map: dict[str, Any],
    extraction_backend: str | None = None,
) -> dict[str, Any]:
    review_summary = evaluate_document_review(
        document_type=document_type,
        text=text,
        structured_data=structured_data,
        evidence_map=evidence_map,
        extraction_backend=extraction_backend,
    )

    task_id: int | None = None
    with session_scope() as db:
        document = db.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        metadata_json = dict(document.metadata_json or {})
        metadata_json["review_summary"] = review_summary
        metadata_json["review_last_evaluated_at"] = datetime.utcnow().isoformat()
        document.metadata_json = metadata_json
        document.extraction_confidence = float(review_summary.get("overall_confidence", 0.0) or 0.0)

        if review_summary.get("recommended_review"):
            document.review_status = "needs_review"
            document.auto_approved = False
            document.approved_by = None
            document.approved_at = None
            document.has_human_corrections = False
            document.canonical_data_ready = False
            document.uses_review_queue = True
            document.reviewed_data_json = {}
            task = _upsert_review_task(db, document=document, review_summary=review_summary)
            task_id = task.id
        else:
            document.review_status = "approved"
            document.auto_approved = True
            document.approved_by = "system"
            document.approved_at = datetime.utcnow()
            document.has_human_corrections = False
            document.canonical_data_ready = True
            document.uses_review_queue = False
            document.reviewed_data_json = dict(document.structured_data_json or {})

        db.add(document)

    return {
        "review_status": "needs_review" if review_summary.get("recommended_review") else "approved",
        "auto_approved": not review_summary.get("recommended_review"),
        "canonical_data_ready": not review_summary.get("recommended_review"),
        "extraction_confidence": review_summary.get("overall_confidence"),
        "review_task_id": task_id,
        "review_summary": review_summary,
    }


def list_review_tasks(
    *,
    status: str | None = None,
    task_type: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    with session_scope() as db:
        statement = (
            select(ReviewTask)
            .options(selectinload(ReviewTask.document))
            .order_by(desc(ReviewTask.created_at))
        )
        if status:
            statement = statement.where(ReviewTask.status == status)
        if task_type:
            statement = statement.where(ReviewTask.task_type == task_type)
        if document_type:
            statement = statement.where(ReviewTask.document_type == document_type)

        tasks = db.scalars(statement).all()

    serialized = [_serialize_review_task(task) for task in tasks]
    serialized.sort(key=_task_status_order)
    return {
        "total": len(serialized),
        "tasks": serialized,
    }


def get_review_task_detail(task_id: int) -> dict[str, Any] | None:
    with session_scope() as db:
        task = db.scalar(
            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .options(
                selectinload(ReviewTask.items),
                selectinload(ReviewTask.document),
            )
        )
        if task is None:
            return None

        document = task.document
        normalization = None
        if document and document.document_type == "resume":
            normalization = get_resume_profile_with_relations(document.id)

        return {
            **_serialize_review_task(task),
            "document": _document_summary(document) if document else None,
            "items": [_serialize_review_item(item) for item in sorted(task.items, key=lambda row: (not row.is_critical, row.field_name))],
            "normalization": normalization,
        }


def list_open_review_tasks_for_documents(document_ids: list[int]) -> list[dict[str, Any]]:
    ordered_document_ids = []
    seen_document_ids = set()

    for value in document_ids:
        try:
            document_id = int(value)
        except (TypeError, ValueError):
            continue

        if document_id in seen_document_ids:
            continue

        seen_document_ids.add(document_id)
        ordered_document_ids.append(document_id)

    if not ordered_document_ids:
        return []

    with session_scope() as db:
        tasks = db.scalars(
            select(ReviewTask)
            .where(
                ReviewTask.document_id.in_(ordered_document_ids),
                ReviewTask.status.in_(REVIEWABLE_TASK_STATUSES),
            )
            .options(selectinload(ReviewTask.document))
            .order_by(desc(ReviewTask.updated_at), desc(ReviewTask.created_at))
        ).all()

    tasks_by_document_id = {}
    for task in tasks:
        if task.document_id in tasks_by_document_id:
            continue
        tasks_by_document_id[task.document_id] = _serialize_review_task(task)

    return [
        tasks_by_document_id[document_id]
        for document_id in ordered_document_ids
        if document_id in tasks_by_document_id
    ]


def _refresh_resume_projection(document_id: int) -> dict[str, Any] | None:
    document = get_document_by_id(document_id)
    if not document or document.get("document_type") != "resume":
        return None

    canonical_data = preferred_structured_data(document)
    normalization_result = normalize_resume_profile(
        document_id,
        canonical_data,
        document.get("raw_text", ""),
        document.get("evidence_map", {}),
        confidence_score=document.get("extraction_confidence"),
        source_kind="canonical_reviewed" if document.get("canonical_data_ready") else "raw_extraction",
    )

    profile_id = (normalization_result or {}).get("profile", {}).get("id")
    if profile_id is not None:
        persist_evidence_map(
            document_id,
            document.get("evidence_map", {}),
            resume_profile_id=profile_id,
            entity_type="resume_profile",
            entity_id=profile_id,
        )
    return normalization_result


def _mark_remaining_items(items: list[ReviewItem]) -> None:
    for item in items:
        if item.review_status != "pending":
            continue
        item.review_status = "approved"
        if item.corrected_value is None:
            item.corrected_value = item.extracted_value


def approve_review_task(task_id: int, *, reviewer: str | None = None, review_notes: str | None = None) -> dict[str, Any]:
    document_id: int | None = None
    with session_scope() as db:
        task = db.scalar(
            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .options(selectinload(ReviewTask.items), selectinload(ReviewTask.document))
        )
        if task is None or task.document is None:
            raise ValueError(f"Review task {task_id} not found")

        document = task.document
        document.reviewed_data_json = dict(document.reviewed_data_json or document.structured_data_json or {})
        document.review_status = "approved"
        document.auto_approved = False
        document.approved_by = reviewer
        document.approved_at = datetime.utcnow()
        document.has_human_corrections = False
        document.canonical_data_ready = True
        document.uses_review_queue = True

        _mark_remaining_items(task.items)
        task.status = "approved"
        task.assigned_to = reviewer
        task.review_notes = review_notes
        task.updated_at = datetime.utcnow()

        metadata_json = dict(document.metadata_json or {})
        review_summary = dict(metadata_json.get("review_summary", {}) or {})
        review_summary["last_review_action"] = "approved"
        review_summary["last_reviewed_at"] = datetime.utcnow().isoformat()
        metadata_json["review_summary"] = review_summary
        document.metadata_json = metadata_json

        db.add(document)
        db.add(task)
        document_id = document.id

    if document_id is not None:
        _refresh_resume_projection(document_id)
    return get_review_task_detail(task_id) or {}


def _find_task_item(task: ReviewTask, *, review_item_id: int | None = None, field_name: str | None = None) -> ReviewItem | None:
    for item in task.items:
        if review_item_id is not None and item.id == review_item_id:
            return item
        if field_name and item.field_name == field_name:
            return item
    return None


def correct_review_task(
    task_id: int,
    *,
    reviewer: str | None = None,
    review_notes: str | None = None,
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    corrections = corrections or []
    document_id: int | None = None
    with session_scope() as db:
        task = db.scalar(
            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .options(selectinload(ReviewTask.items), selectinload(ReviewTask.document))
        )
        if task is None or task.document is None:
            raise ValueError(f"Review task {task_id} not found")

        document = task.document
        canonical_data = dict(document.reviewed_data_json or document.structured_data_json or {})
        has_changes = False

        for correction in corrections:
            field_name = correction.get("field_name")
            item = _find_task_item(
                task,
                review_item_id=correction.get("review_item_id"),
                field_name=field_name,
            )
            if item is None:
                continue

            new_value = correction.get("corrected_value")
            old_value = canonical_data.get(item.field_name)
            canonical_data[item.field_name] = new_value
            item.corrected_value = new_value
            item.review_status = "corrected" if new_value != old_value else "approved"
            item.updated_at = datetime.utcnow()

            if new_value != old_value:
                has_changes = True
                db.add(
                    FieldChangeAudit(
                        document_id=document.id,
                        field_name=item.field_name,
                        old_value=old_value,
                        new_value=new_value,
                        changed_by=reviewer,
                        changed_at=datetime.utcnow(),
                        source="human_review",
                    )
                )

        _mark_remaining_items(task.items)

        document.reviewed_data_json = canonical_data
        document.review_status = "corrected" if has_changes else "approved"
        document.auto_approved = False
        document.approved_by = reviewer
        document.approved_at = datetime.utcnow()
        document.has_human_corrections = has_changes
        document.canonical_data_ready = True
        document.uses_review_queue = True

        metadata_json = dict(document.metadata_json or {})
        review_summary = dict(metadata_json.get("review_summary", {}) or {})
        review_summary["last_review_action"] = "corrected" if has_changes else "approved"
        review_summary["last_reviewed_at"] = datetime.utcnow().isoformat()
        metadata_json["review_summary"] = review_summary
        document.metadata_json = metadata_json

        task.status = "corrected" if has_changes else "approved"
        task.assigned_to = reviewer
        task.review_notes = review_notes
        task.updated_at = datetime.utcnow()

        db.add(document)
        db.add(task)
        document_id = document.id

    if document_id is not None:
        _refresh_resume_projection(document_id)
    return get_review_task_detail(task_id) or {}


def reject_review_task(task_id: int, *, reviewer: str | None = None, review_notes: str | None = None) -> dict[str, Any]:
    with session_scope() as db:
        task = db.scalar(
            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .options(selectinload(ReviewTask.items), selectinload(ReviewTask.document))
        )
        if task is None or task.document is None:
            raise ValueError(f"Review task {task_id} not found")

        document = task.document
        document.review_status = "needs_review"
        document.auto_approved = False
        document.approved_by = None
        document.approved_at = None
        document.has_human_corrections = False
        document.canonical_data_ready = False
        document.reviewed_data_json = {}
        document.uses_review_queue = True

        for item in task.items:
            if item.review_status == "pending":
                item.review_status = "rejected"
            item.updated_at = datetime.utcnow()

        task.status = "rejected"
        task.assigned_to = reviewer
        task.review_notes = review_notes
        task.updated_at = datetime.utcnow()

        metadata_json = dict(document.metadata_json or {})
        review_summary = dict(metadata_json.get("review_summary", {}) or {})
        review_summary["last_review_action"] = "rejected"
        review_summary["last_reviewed_at"] = datetime.utcnow().isoformat()
        metadata_json["review_summary"] = review_summary
        document.metadata_json = metadata_json

        db.add(document)
        db.add(task)

    return get_review_task_detail(task_id) or {}


def _ensure_document_review_task(document_id: int) -> ReviewTask:
    with session_scope() as db:
        task = db.scalar(
            select(ReviewTask)
            .where(
                ReviewTask.document_id == document_id,
                ReviewTask.status.in_(REVIEWABLE_TASK_STATUSES),
            )
            .order_by(desc(ReviewTask.updated_at), desc(ReviewTask.created_at))
            .options(selectinload(ReviewTask.document))
        )
        if task is not None:
            return task

        document = db.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        review_summary = (document.metadata_json or {}).get("review_summary")
        if not review_summary:
            review_summary = evaluate_document_review(
                document_type=document.document_type,
                text=document.raw_text or "",
                structured_data=document.structured_data_json or {},
                evidence_map=document.evidence_map_json or {},
                extraction_backend=document.extraction_method,
            )
            metadata_json = dict(document.metadata_json or {})
            metadata_json["review_summary"] = review_summary
            document.metadata_json = metadata_json
            db.add(document)

        task = _upsert_review_task(db, document=document, review_summary=review_summary)
        db.flush()
        db.refresh(task)
        return task


def approve_tender_criteria(
    document_id: int,
    *,
    reviewer: str | None = None,
    review_notes: str | None = None,
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task = _ensure_document_review_task(document_id)
    if corrections:
        return correct_review_task(
            task.id,
            reviewer=reviewer,
            review_notes=review_notes,
            corrections=corrections,
        )
    return approve_review_task(task.id, reviewer=reviewer, review_notes=review_notes)


def record_match_feedback(
    *,
    tender_document_id: int,
    resume_document_id: int,
    system_score: float | None = None,
    human_decision: str,
    reason_code: str | None = None,
    review_comment: str | None = None,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    with session_scope() as db:
        feedback = MatchFeedback(
            tender_document_id=tender_document_id,
            resume_document_id=resume_document_id,
            system_score=system_score,
            human_decision=human_decision,
            reason_code=reason_code,
            review_comment=review_comment,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.utcnow(),
        )
        db.add(feedback)
        db.flush()
        db.refresh(feedback)

        return {
            "id": feedback.id,
            "tender_document_id": feedback.tender_document_id,
            "resume_document_id": feedback.resume_document_id,
            "system_score": feedback.system_score,
            "human_decision": feedback.human_decision,
            "reason_code": feedback.reason_code,
            "review_comment": feedback.review_comment,
            "reviewed_by": feedback.reviewed_by,
            "reviewed_at": feedback.reviewed_at,
        }
