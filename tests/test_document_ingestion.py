from app.services.document_ingestion import (
    INGESTION_PIPELINE_VERSION,
    _can_reuse_existing_document,
)


def test_can_reuse_existing_document_only_when_pipeline_version_matches():
    assert _can_reuse_existing_document(None) is False
    assert _can_reuse_existing_document({"status": "failed", "metadata_json": {}}) is False
    assert _can_reuse_existing_document({"status": "stored", "metadata_json": {}}) is False
    assert (
        _can_reuse_existing_document(
            {
                "status": "stored",
                "metadata_json": {"pipeline_version": INGESTION_PIPELINE_VERSION},
            }
        )
        is True
    )
