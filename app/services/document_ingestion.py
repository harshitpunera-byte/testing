import os

from app.extraction.resume_extractor import extract_resume_data
from app.extraction.tender_extractor import extract_tender_requirements
from app.rag.chunker import chunk_document_pages
from app.rag.cleaner import clean_pages
from app.rag.embeddings import create_embeddings
from app.rag.loader import flatten_pages, load_pdf_pages
from app.rag.vector_store import invalidate_index, store_document_chunks
from app.services.document_repository import (
    create_document_record,
    get_document_by_hash,
    get_document_by_id,
    get_persisted_document_chunks,
    get_resume_profile_with_relations,
    purge_document_artifacts,
    rename_document_chunks,
    replace_document_chunks,
    update_document_record,
)
from app.services.evidence_service import build_evidence_map
from app.services.evidence_service import persist_evidence_map
from app.services.profile_normalizer import normalize_resume_profile
from app.services.review_service import preferred_structured_data, sync_document_review_state
from app.utils.file_hash import compute_sha256_bytes
from app.utils.file_storage import build_storage_name, save_file_bytes
from app.utils.file_validator import validate_pdf_upload


UPLOAD_DIRS = {
    "tender": "uploads/tenders",
    "resume": "uploads/resumes",
}

INDEX_NAMES = {
    "tender": "tender",
    "resume": "resume",
}

STRUCTURED_EXTRACTORS = {
    "tender": extract_tender_requirements,
    "resume": extract_resume_data,
}

CHUNK_CONFIG = {
    "tender": {"chunk_size": 800, "overlap": 150},
    "resume": {"chunk_size": 800, "overlap": 150},
}

INGESTION_PIPELINE_VERSION = "2026-03-26-exact-facts-v1"


def _build_error_response(filename: str, message: str, status: str) -> dict:
    return {
        "filename": filename,
        "status": status,
        "message": message,
        "chunks": 0,
        "stored_chunks": 0,
        "document_id": None,
        "normalization": None,
    }


def _can_reuse_existing_document(existing: dict | None) -> bool:
    if not existing or existing.get("status") == "failed":
        return False

    metadata_json = existing.get("metadata_json") or {}
    return metadata_json.get("pipeline_version") == INGESTION_PIPELINE_VERSION


async def process_uploaded_document(file, document_type: str) -> dict:
    if document_type not in {"tender", "resume"}:
        raise ValueError(f"Unsupported document_type: {document_type}")

    original_filename = file.filename or f"{document_type}.pdf"
    file_bytes = await file.read()

    validation = validate_pdf_upload(
        filename=original_filename,
        content_type=getattr(file, "content_type", None),
        data=file_bytes,
    )

    if not validation["is_valid"]:
        return _build_error_response(original_filename, validation["error"], status="invalid")

    file_hash = compute_sha256_bytes(file_bytes)
    existing = get_document_by_hash(document_type, file_hash)
    can_reuse_existing = _can_reuse_existing_document(existing)

    if can_reuse_existing and existing:
        updated_existing = update_document_record(
            existing["id"],
            original_filename=original_filename,
            status="stored",
        ) or existing
        reused_chunks = get_persisted_document_chunks(existing["id"])
        rename_document_chunks(existing["id"], original_filename)
        invalidate_index(INDEX_NAMES[document_type])

        return {
            "filename": original_filename,
            "status": "duplicate",
            "message": f"Duplicate {document_type} upload detected. Reusing existing parsed data.",
            "chunks": len(reused_chunks),
            "stored_chunks": len(reused_chunks),
            "document_id": updated_existing.get("id"),
            "file_hash": file_hash,
            "saved_path": updated_existing.get("stored_path"),
            "structured_data": updated_existing.get("structured_data", {}),
            "evidence_map": updated_existing.get("evidence_map", {}),
            "pages": updated_existing.get("total_pages"),
            "extraction_backend": updated_existing.get("extraction_backend"),
            "review_status": updated_existing.get("review_status"),
            "auto_approved": updated_existing.get("auto_approved"),
            "canonical_data_ready": updated_existing.get("canonical_data_ready"),
            "uses_review_queue": updated_existing.get("uses_review_queue"),
            "extraction_confidence": updated_existing.get("extraction_confidence"),
            "review_summary": updated_existing.get("review_summary", {}),
            "normalization": (
                get_resume_profile_with_relations(updated_existing.get("id"))
                if document_type == "resume" and updated_existing.get("id") is not None
                else None
            ),
        }

    upload_dir = UPLOAD_DIRS[document_type]
    os.makedirs(upload_dir, exist_ok=True)

    stored_filename = build_storage_name(original_filename)
    saved_path = save_file_bytes(file_bytes, upload_dir, stored_filename)

    document_record = None
    try:
        if existing and not can_reuse_existing:
            document_record = update_document_record(
                existing["id"],
                original_filename=original_filename,
                stored_filename=stored_filename,
                stored_path=saved_path,
                file_size=len(file_bytes),
                status="processing",
                structured_data={},
                reviewed_data={},
                evidence_map={},
                canonical_data_ready=False,
                auto_approved=False,
                review_status="not_needed",
                metadata_json={"pipeline_version": INGESTION_PIPELINE_VERSION},
            )
        else:
            document_record = create_document_record(
                document_type=document_type,
                original_filename=original_filename,
                stored_filename=stored_filename,
                stored_path=saved_path,
                file_hash=file_hash,
                file_size=len(file_bytes),
                mime_type=getattr(file, "content_type", None),
                status="processing",
                structured_data={},
                evidence_map={},
                metadata_json={"pipeline_version": INGESTION_PIPELINE_VERSION},
            )

        extracted = load_pdf_pages(file_bytes, document_name=original_filename)
        cleaned_pages = clean_pages(extracted.pages)
        full_text = flatten_pages(cleaned_pages)

        if not full_text.strip():
            update_document_record(
                document_record["id"],
                status="failed",
                extraction_backend=extracted.backend,
                total_pages=len(cleaned_pages),
                raw_text="",
                markdown_text="",
            )
            return _build_error_response(original_filename, "No readable text found in PDF", status="invalid")

        chunk_config = CHUNK_CONFIG[document_type]
        chunk_records = chunk_document_pages(
            cleaned_pages,
            document_type=document_type,
            chunk_size=chunk_config["chunk_size"],
            overlap=chunk_config["overlap"],
            filename=original_filename,
            document_id=document_record["id"],
        )

        if not chunk_records:
            update_document_record(
                document_record["id"],
                status="failed",
                extraction_backend=extracted.backend,
                total_pages=len(cleaned_pages),
                raw_text=full_text,
                markdown_text=full_text,
            )
            return _build_error_response(original_filename, "No chunks created from extracted text", status="failed")

        embeddings = create_embeddings([chunk["text"] for chunk in chunk_records]).tolist()
        stored_count = store_document_chunks(INDEX_NAMES[document_type], chunk_records, filename=original_filename)
        replace_document_chunks(
            document_record["id"],
            INDEX_NAMES[document_type],
            chunk_records,
            embeddings=embeddings,
        )
        invalidate_index(INDEX_NAMES[document_type])

        extractor = STRUCTURED_EXTRACTORS[document_type]
        structured_data = extractor(full_text)
        evidence_map = build_evidence_map(structured_data, chunk_records)

        updated_document = update_document_record(
            document_record["id"],
            status="stored",
            extraction_backend=extracted.backend,
            total_pages=len(cleaned_pages),
            raw_text=full_text,
            markdown_text=full_text,
            structured_data=structured_data,
            evidence_map=evidence_map,
            metadata_json={
                "total_pages": len(cleaned_pages),
                "chunk_count": len(chunk_records),
                "pipeline_version": INGESTION_PIPELINE_VERSION,
            },
        )
        review_state = sync_document_review_state(
            document_id=(updated_document or document_record)["id"],
            document_type=document_type,
            text=full_text,
            structured_data=structured_data,
            evidence_map=evidence_map,
            extraction_backend=extracted.backend,
        )
        updated_document = get_document_by_id((updated_document or document_record)["id"])
        normalization_result = None
        if document_type == "resume":
            normalization_result = normalize_resume_profile(
                updated_document["id"] if updated_document else document_record["id"],
                preferred_structured_data(updated_document) or structured_data,
                full_text,
                evidence_map,
                confidence_score=(updated_document or {}).get("extraction_confidence"),
                source_kind="canonical_reviewed" if (updated_document or {}).get("canonical_data_ready") else "raw_extraction",
            )
            persist_evidence_map(
                updated_document["id"] if updated_document else document_record["id"],
                evidence_map,
                resume_profile_id=(normalization_result or {}).get("profile", {}).get("id"),
                entity_type="resume_profile",
                entity_id=(normalization_result or {}).get("profile", {}).get("id"),
            )
        else:
            persist_evidence_map(
                updated_document["id"] if updated_document else document_record["id"],
                evidence_map,
                entity_type="tender_requirements",
                entity_id=updated_document["id"] if updated_document else document_record["id"],
            )

        return {
            "filename": original_filename,
            "status": "stored",
            "message": f"{document_type.capitalize()} stored successfully",
            "chunks": len(chunk_records),
            "stored_chunks": stored_count,
            "document_id": updated_document["id"] if updated_document else document_record["id"],
            "file_hash": file_hash,
            "saved_path": saved_path,
            "pages": len(cleaned_pages),
            "extraction_backend": extracted.backend,
            "structured_data": structured_data,
            "evidence_map": evidence_map,
            "review_status": (updated_document or {}).get("review_status"),
            "auto_approved": (updated_document or {}).get("auto_approved"),
            "canonical_data_ready": (updated_document or {}).get("canonical_data_ready"),
            "uses_review_queue": (updated_document or {}).get("uses_review_queue"),
            "extraction_confidence": (updated_document or {}).get("extraction_confidence"),
            "review_task_id": review_state.get("review_task_id"),
            "review_summary": review_state.get("review_summary", {}),
            "normalization": normalization_result,
        }
    except Exception as exc:
        if document_record:
            purge_document_artifacts(document_record["id"])
            update_document_record(document_record["id"], status="failed")
        return _build_error_response(original_filename, f"Processing failed: {exc}", status="failed")
