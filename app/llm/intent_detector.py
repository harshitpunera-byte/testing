from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ValidationError
import json
import logging
import re

from app.llm.provider import llm_json_extract

logger = logging.getLogger(__name__)


class QueryIntent(BaseModel):
    intent: str  # One of: SEARCH_RESUMES, SEARCH_TENDER, MATCHING, GENERAL
    granularity: str  # One of: GLOBAL, LOCAL
    target_document: Optional[str] = None
    sub_queries: List[str]
    detected_entities: Dict[str, str]
    semantic_expansion_terms: List[str]
    is_complex: bool


INTENT_PROMPT = """Analyze the user query for a Tender-Resume Matching RAG system.

<UploadedDocumentsSnapshots>
{document_context}
</UploadedDocumentsSnapshots>

<DiscoveryEvidenceDetected>
{discovery_evidence}
</DiscoveryEvidenceDetected>

MISSION:
Identify the primary intent and granularity by matching the user's query against the document snapshots above.

INTENT TYPES:
1. SEARCH_RESUMES: Query is about people, candidates, or attributes found in RESUME snapshots.
2. SEARCH_TENDER: Query is about the project, authority, requirements, or facts found in TENDER snapshots.
3. MATCHING: Evaluate a specific person against the tender requirements.
4. GENERAL: Greeting, help question, or non-relevant question.

ROUTING RULES:
- SEMANTIC MATCH: If the user asks for "Authority", "Project Details", or "Site Location", prefer the TENDER snapshot containing those concepts.
- IDENTITY MATCH: If the user asks for a person, use the DISCOVERY EVIDENCE to identify which filename belongs to that person.
- If the DISCOVERY EVIDENCE contains a candidate name matching the query, set target_document to that specific filename and use LOCAL granularity.
- **AGGREGATION RULE**: If the query asks for "phone numbers of all", "list of emails", "how many candidates", or any bulk data retrieval, you MUST use intent="SEARCH_RESUMES" and granularity="GLOBAL". **Do NOT use LOCAL or MATCHING for bulk data listing.**
- "This tender" or "The tender" refers to the primary TENDER snapshot when one exists.
- Return strict JSON only.

User Query:
{query}

OUTPUT FORMAT:
{{
    "intent": "SEARCH_TENDER | SEARCH_RESUMES | MATCHING | GENERAL",
    "granularity": "GLOBAL | LOCAL",
    "target_document": "string or null",
    "sub_queries": ["rewritten sub-query 1"],
    "detected_entities": {{"key": "value"}},
    "semantic_expansion_terms": ["synonym1", "synonym2"],
    "is_complex": true
}}
"""


def _sanitize_for_prompt(text: str, max_len: int | None = None) -> str:
    sanitized = str(text or "")
    sanitized = sanitized.replace("{", "(").replace("}", ")")
    sanitized = sanitized.replace("```", "'''")
    sanitized = sanitized.replace("\x00", " ")
    sanitized = re.sub(r"[\r\n\t]+", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if max_len is not None:
        sanitized = sanitized[:max_len]
    return sanitized


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


def _safe_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_intent_payload(data: dict[str, Any], original_query: str) -> dict[str, Any]:
    allowed_intents = {"SEARCH_RESUMES", "SEARCH_TENDER", "MATCHING", "GENERAL"}
    allowed_granularity = {"GLOBAL", "LOCAL"}

    intent = _safe_string(data.get("intent")) or "GENERAL"
    if intent not in allowed_intents:
        intent = "GENERAL"

    granularity = _safe_string(data.get("granularity")) or "GLOBAL"
    if granularity not in allowed_granularity:
        granularity = "GLOBAL"

    target_document = _safe_string(data.get("target_document"))

    sub_queries_raw = data.get("sub_queries", [])
    if isinstance(sub_queries_raw, list):
        sub_queries = [str(item).strip() for item in sub_queries_raw if str(item).strip()]
    else:
        sub_queries = []

    if not sub_queries:
        sub_queries = [original_query]

    detected_entities_raw = data.get("detected_entities", {})
    detected_entities: Dict[str, str] = {}
    if isinstance(detected_entities_raw, dict):
        for key, value in detected_entities_raw.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if key_str and value_str:
                detected_entities[key_str] = value_str

    semantic_terms_raw = data.get("semantic_expansion_terms", [])
    if isinstance(semantic_terms_raw, list):
        semantic_expansion_terms = [str(item).strip() for item in semantic_terms_raw if str(item).strip()]
    else:
        semantic_expansion_terms = []

    is_complex_raw = data.get("is_complex", False)
    is_complex = bool(is_complex_raw)

    return {
        "intent": intent,
        "granularity": granularity,
        "target_document": target_document,
        "sub_queries": sub_queries,
        "detected_entities": detected_entities,
        "semantic_expansion_terms": semantic_expansion_terms,
        "is_complex": is_complex,
    }


def _fallback_intent(query: str, error_message: str | None = None) -> QueryIntent:
    detected_entities = {}
    if error_message:
        detected_entities["fallback_reason"] = error_message[:300]

    return QueryIntent(
        intent="GENERAL",
        granularity="GLOBAL",
        target_document=None,
        sub_queries=[query],
        detected_entities=detected_entities,
        semantic_expansion_terms=[],
        is_complex=False,
    )


def detect_query_intent(
    query: str,
    document_context: str = "No documents currently uploaded.",
    discovery_evidence: str = "",
) -> QueryIntent:
    schema = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["SEARCH_RESUMES", "SEARCH_TENDER", "MATCHING", "GENERAL"],
            },
            "granularity": {
                "type": "string",
                "enum": ["GLOBAL", "LOCAL"],
            },
            "target_document": {"type": ["string", "null"]},
            "sub_queries": {"type": "array", "items": {"type": "string"}},
            "detected_entities": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "semantic_expansion_terms": {
                "type": "array",
                "items": {"type": "string"},
            },
            "is_complex": {"type": "boolean"},
        },
        "required": [
            "intent",
            "granularity",
            "target_document",
            "sub_queries",
            "detected_entities",
            "semantic_expansion_terms",
            "is_complex",
        ],
    }

    safe_query = _sanitize_for_prompt(query, max_len=1500)
    safe_document_context = _sanitize_for_prompt(document_context, max_len=12000)
    safe_discovery_evidence = _sanitize_for_prompt(discovery_evidence, max_len=8000)
    
    prompt = INTENT_PROMPT.format(
        query=safe_query, 
        document_context=safe_document_context,
        discovery_evidence=safe_discovery_evidence
    )

    try:
        raw_response = llm_json_extract(prompt, schema)

        if isinstance(raw_response, dict):
            data = raw_response
        elif isinstance(raw_response, str):
            parsed = _extract_json_object(raw_response)
            if parsed is None:
                logger.warning("detect_query_intent: could not parse JSON from llm_json_extract response")
                return _fallback_intent(query, "invalid_json_from_llm")
            data = parsed
        else:
            logger.warning(
                "detect_query_intent: unexpected llm_json_extract response type: %s",
                type(raw_response).__name__,
            )
            return _fallback_intent(query, "unexpected_llm_response_type")

        normalized = _normalize_intent_payload(data, query)
        return QueryIntent(**normalized)

    except ValidationError as exc:
        logger.exception("detect_query_intent: pydantic validation failed")
        return _fallback_intent(query, f"validation_error:{exc.__class__.__name__}")
    except json.JSONDecodeError as exc:
        logger.exception("detect_query_intent: JSON decode failed")
        return _fallback_intent(query, f"json_decode_error:{exc.__class__.__name__}")
    except Exception as exc:
        logger.exception("detect_query_intent: unexpected failure")
        return _fallback_intent(query, f"unexpected_error:{exc.__class__.__name__}")