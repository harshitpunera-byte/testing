from typing import Dict, List, Optional
from pydantic import BaseModel
import json
from app.llm.provider import llm_json_extract

class QueryIntent(BaseModel):
    intent: str  # One of: SEARCH_RESUMES, SEARCH_TENDER, MATCHING, GENERAL
    granularity: str # One of: GLOBAL (all documents), LOCAL (specific file/person)
    target_document: Optional[str] = None # The filename or name of the person if scope is LOCAL
    sub_queries: List[str]
    detected_entities: Dict[str, str]
    semantic_expansion_terms: List[str]
    is_complex: bool

INTENT_PROMPT = """
Analyze the following user query for a Tender-Resume Matching RAG system.
Identify the primary intent and the GRANULARITY (is the user talking about EVERYONE or ONE SPECIFIC FILE/PERSON?).

INTENT TYPES:
- SEARCH_RESUMES: Looking for types of candidates or list of people (e.g., "find btech developers").
- SEARCH_TENDER: Looking for facts, dates, requirements, or overview from the TENDER/RFP document (e.g., "key points of tender", "what is the net worth requirement?", "explain clause 3").
  - IMPORTANT: If the query contains "tender", "RFP", "project requirements", or "document overview" and does NOT mention a candidate name, set the intent to SEARCH_TENDER.
- MATCHING: Comparing a candidate against the tender (e.g., "how does Mohan match the tender?").
- GENERAL: Greetings or general non-document talk.

GRANULARITY TYPES:
- GLOBAL: The query is about the entire database or generic requirements (e.g., "find all BTech devs", "how many candidates matching?").
- LOCAL: The query specifies a specific entity, person, or FILENAME (e.g., "list companies in BE.pdf", "Mohan's companies", "Vishwa Nath's role").
  - IMPORTANT: If a proper name (like "Mohan" or "John") is mentioned, it is ALWAYS LOCAL unless it's explicitly about a large group of people with that name.
  - IMPORTANT: If the user asks for "the tender" or "this tender", it is LOCAL to the uploaded tender document.


CLEAN TARGET EXTRACTION:
- If a user mentions a filename (e.g., "BE.pdf"), extract the CLEAN NAME without extension (e.g., "BE").
- If a user mentions a person (e.g., "Vishwa Nath's resume"), extract the CLEAN PERSON NAME (e.g., "Vishwa Nath").
- This allows our fuzzy resolver to find the correct document even with partial matches.

User Query: {query}

Return the results in the following JSON format:
{{
    "intent": "INTENT_NAME",
    "granularity": "GLOBAL/LOCAL",
    "target_document": "Clean name or null",
    "sub_queries": ["sub_query_1"],
    "detected_entities": {{"qualification": "...", "target_name": "..."}},
    "semantic_expansion_terms": ["synonym1"],
    "is_complex": true/false
}}
"""

def detect_query_intent(query: str) -> QueryIntent:
    schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["SEARCH_RESUMES", "SEARCH_TENDER", "MATCHING", "GENERAL"]},
            "granularity": {"type": "string", "enum": ["GLOBAL", "LOCAL"]},
            "target_document": {"type": ["string", "null"]},
            "sub_queries": {"type": "array", "items": {"type": "string"}},
            "detected_entities": {"type": "object", "additionalProperties": {"type": "string"}},
            "semantic_expansion_terms": {"type": "array", "items": {"type": "string"}},
            "is_complex": {"type": "boolean"}
        },
        "required": ["intent", "granularity", "sub_queries", "detected_entities", "semantic_expansion_terms", "is_complex"]
    }
    
    prompt = INTENT_PROMPT.format(query=query)
    raw_response = llm_json_extract(prompt, schema)
    data = json.loads(raw_response)
    
    return QueryIntent(**data)

