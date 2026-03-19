import re
from typing import Any

from app.services.document_repository import replace_field_evidence


def _normalize_token(token: str) -> str:
    return "".join(char for char in str(token).lower() if char.isalnum())


def _token_set(value: Any) -> set[str]:
    return {_normalize_token(token) for token in str(value).split() if _normalize_token(token)}


def _extract_snippet(text: str, needle: str | None, max_chars: int = 240) -> tuple[str, int | None, int | None]:
    normalized_needle = (needle or "").strip()
    clean_text = re.sub(r"\s+", " ", text).strip()

    if not clean_text:
        return "", None, None

    if not normalized_needle:
        snippet = clean_text[:max_chars]
        return snippet, 0, len(snippet)

    lowered_text = clean_text.lower()
    lowered_needle = normalized_needle.lower()
    index = lowered_text.find(lowered_needle)

    if index == -1:
        snippet = clean_text[:max_chars]
        return snippet, 0, len(snippet)

    start = max(0, index - 60)
    end = min(len(clean_text), index + len(normalized_needle) + 120)
    return clean_text[start:end].strip(), start, end


def _score_chunk_for_value(value: Any, chunk: dict) -> float:
    if value is None or value == "" or value == []:
        return 0.0

    text = str(chunk.get("text", "") or "")
    lowered_text = text.lower()
    lowered_value = str(value).strip().lower()

    if not lowered_text or not lowered_value:
        return 0.0

    if lowered_value in lowered_text:
        return 0.98

    value_tokens = _token_set(lowered_value)
    chunk_tokens = _token_set(lowered_text)

    if not value_tokens or not chunk_tokens:
        return 0.0

    overlap = value_tokens & chunk_tokens
    if not overlap:
        return 0.0

    return round(len(overlap) / max(1, len(value_tokens)), 2)


def _build_evidence_entry(value: Any, chunks: list[dict]) -> dict:
    best_chunk = None
    best_score = 0.0

    for chunk in chunks:
        score = _score_chunk_for_value(value, chunk)
        if score > best_score:
            best_score = score
            best_chunk = chunk

    if best_chunk is None:
        return {
            "value": value,
            "source_text": None,
            "page": None,
            "section": None,
            "confidence": 0.0,
            "char_start": None,
            "char_end": None,
        }

    snippet, char_start, char_end = _extract_snippet(
        best_chunk.get("text", ""),
        str(value) if value is not None else None,
    )
    return {
        "value": value,
        "source_text": snippet,
        "page": best_chunk.get("page_start"),
        "section": best_chunk.get("section"),
        "confidence": float(best_score),
        "char_start": char_start,
        "char_end": char_end,
    }


def build_evidence_map(structured_data: dict[str, Any], chunks: list[dict]) -> dict[str, Any]:
    evidence_map: dict[str, Any] = {}

    for field, value in structured_data.items():
        if isinstance(value, list):
            evidence_map[field] = [
                _build_evidence_entry(item, chunks)
                for item in value
                if item not in (None, "", [])
            ]
            continue

        evidence_map[field] = _build_evidence_entry(value, chunks)

    return evidence_map


def persist_evidence_map(
    document_id: int,
    evidence_map: dict[str, Any],
    *,
    resume_profile_id: int | None = None,
    entity_type: str = "document",
    entity_id: int | None = None,
) -> int:
    rows = []
    for field_name, value in (evidence_map or {}).items():
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field_name": field_name,
                    "page_no": entry.get("page"),
                    "section_name": entry.get("section"),
                    "snippet": entry.get("source_text"),
                    "char_start": entry.get("char_start"),
                    "char_end": entry.get("char_end"),
                    "confidence": float(entry.get("confidence", 0.0) or 0.0),
                }
            )

    return replace_field_evidence(document_id, rows, resume_profile_id=resume_profile_id)
