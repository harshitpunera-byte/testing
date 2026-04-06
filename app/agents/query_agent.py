import json


MATCH_KEYWORDS = {
    "match",
    "matching",
    "shortlist",
    "matching profile",
    "matching profiles",
    "suitable candidate",
    "suitable resume",
    "best resume",
    "best resumes",
    "best profile",
    "best profiles",
    "top candidate",
    "top candidates",
    "top profile",
    "top profiles",
    "rank candidate",
    "rank resume",
    "rank profiles",
    "find resumes",
    "find candidates",
    "list profiles",
    "show profiles",
}

TENDER_HINTS = {
    "tender",
    "rfp",
    "eligibility",
    "scope",
    "bid",
    "authority",
    "qualification",
    "requirements",
    "loa",
    "clause",
    "definition",
    "glossary",
    "net worth",
    "financial",
    "chainage",
    "ch.",
    "project cost",
    "amount",
    "value",
    "contract",
}

RESUME_HINTS = {
    "resume",
    "cv",
    "candidate",
    "candidate name",
    "applicant",
    "applicant name",
    "profile",
    "skill",
    "experience",
    "project",
    "staff",
    "member",
    "personnel",
    "resource",
    "dob",
    "birth",
}

COLLECTION_HINTS = {
    "how many",
    "total",
    "all candidates",
    "all resumes",
    "list all",
    "show all",
    "count",
    "many",
}


def classify_query_intent(query: str, has_tender: bool, has_resume: bool) -> dict:
    lowered = " ".join(query.lower().split())

    # Check for matching intent first
    is_match_query = has_tender and has_resume and any(keyword in lowered for keyword in MATCH_KEYWORDS)
    if is_match_query:
        return {"mode": "matching", "scope": "both"}

    # Smart Routing logic
    tender_hint = any(keyword in lowered for keyword in TENDER_HINTS)
    resume_hint = any(keyword in lowered for keyword in RESUME_HINTS)

    # 1. Both found (or ambiguous) -> Search Both for safety
    if (tender_hint and resume_hint) or (not tender_hint and not resume_hint and has_tender and has_resume):
        if has_tender and has_resume:
            return {"mode": "qa", "scope": "both"}

    # 2. Only Tender signal found
    if tender_hint or (has_tender and not has_resume):
        return {"mode": "qa", "scope": "tender"}

    # 3. Only Resume signal found
    if resume_hint or (has_resume and not has_tender):
        return {"mode": "qa", "scope": "resume"}

    # Default Fallback
    return {"mode": "none", "scope": "none"}


def build_answer_prompt(query: str, scope_label: str, structured_contexts: list[dict], chunks: list[dict]) -> str:
    structured_json = json.dumps(structured_contexts[:2], ensure_ascii=True, indent=2)

    rendered_chunks = []
    for index, chunk in enumerate(chunks[:20], start=1):
        filename = chunk.get("filename", "unknown.pdf")
        page_start = chunk.get("page_start") or "?"
        page_end = chunk.get("page_end") or page_start
        section = chunk.get("section") or "general"
        text = chunk.get("text", "").strip()
        compact_text = " ".join(text.split())
        rendered_chunks.append(
            f"[{index}] file={filename} page={page_start}-{page_end} section={section}\n{compact_text}"
        )

    chunk_block = "\n\n".join(rendered_chunks)

    prompt = f"""
YOU ARE A DATA EXTRACTION SPECIALIST AND AGGREGATOR. 
I am providing you with context from TWO DIFFERENT DATA SOURCES (Tenders and Resumes).
Your job is to answer the user's question without mixing data between these two documents.

The evidence below is already SOURCE-LABELED and intentionally INTERLEAVED.
Read it in the order provided so neither source type gets ignored.

========= STRUCTURED CONTEXT (BEST EFFORT) =========
{structured_json}

========= ORDERED EVIDENCE SNIPPETS =========
{chunk_block}

USER QUESTION: {query}

MISSION RULES:
1. Every answer must use the SPECIFIC source label on the evidence snippet ([TENDER SOURCE] or [RESUME SOURCE]).
2. If the user asks for candidate name or DOB, you MUST EXTRACT IT directly. DO NOT provide external links or say "it can be found at this link".
3. If the user asks for Project Name, LOA, or Clauses, use ONLY [TENDER SOURCE] evidence.
4. For Financial values (Net Worth/Cost), provide the EXACT NUMBER (e.g., 332.59 Cr).
5. DO NOT provide URLs or Links. Provide the actual information from the text.
6. Explicitly mention which source label provided which part of the answer.
7. If the context has a DOB, you MUST say it.
8. PRECISION SOURCE RULE: If a specific filename was identified as the 'Target' of the query (e.g. BE.pdf), FOCUS 100% on the evidence labeled with that filename. IGNORE other documents if they contradict the target document.
9. If a snippet contains a direct field/value pair or glossary-style mapping (for example, "Date of Birth: 1st July 1970" or "LOA As defined in Clause 3.8.4"), copy that exact value instead of inferring.


"""
    return prompt.strip()


def build_collection_summary_prompt(query: str, total_count: int, matched_candidates: list[dict], clusters: dict | None = None) -> str:
    candidates_text = "\n".join(
        f"- {c.get('candidate_name', 'Unknown')} (ID: {c.get('resume_profile_id')}, Title: {c.get('normalized_title', 'Unknown')}, Education: {c.get('highest_education', 'Unknown')}, Exp: {round((c.get('total_experience_months') or 0)/12, 1)} yrs)"
        for c in matched_candidates[:20]
    )
    
    return f"""
YOU ARE A RECRUITMENT ANALYST.
The user is asking a specific question that requires an answer from the candidate database.
I have performed a high-precision structured search and found the following facts:

TOTAL MATCHES FOUND: {total_count}

CANDIDATES DATA:
{candidates_text}

USER QUESTION: {query}

MISSION:
1. AT FIRST, provide a DIRECT ANSWER to the user question. 
   - If the user asks for a LIST OF NAMES, provide the names in a clean Markdown list.
   - If the user asks HOW MANY, state the number clearly.
2. After the direct answer, provide a 1-2 sentence factual reasoning (e.g., "All 3 found candidates have a recorded M.Tech degree").
3. STRICT NEGATIVE RULE: If the list is empty or none of the candidates actually meet the requirement (e.g. they only have BTech when user wants Masters), say: "I could not find any candidates matching this specific requirement."
4. STRICTURE: DO NOT use generic or flattering phrases like "the pool is well-suited for a client demo", "impressive skills", or "highlights of the pool". Be professional, direct, and critical.
3. TRUTHFULNESS RULE: The structured search logic has ALREADY verified these candidates against the user's criteria (e.g., BTech degree, Science background, Company names).
4. CRITICAL: NEVER say "I don't know" or "Context is insufficient" if candidates are listed above. If they are in the list, they ARE the answer.
5. If some candidates have "Unknown" in their education field but are in this list, it is because their DEEP text (which you don't see here but the search engine saw) matches the user's specific degree requirement. DO NOT point out that their education is "Unknown" in your answer. Just trust they are valid.
6. Keep the response concise and data-driven.
""".strip()



def build_exact_fact_summary_prompt(query: str, extracted_facts: str, chunks: list[dict]) -> str:
    rendered_chunks = []
    for index, chunk in enumerate(chunks[:8], start=1):
        filename = chunk.get("filename", "unknown.pdf")
        page_start = chunk.get("page_start") or "?"
        page_end = chunk.get("page_end") or page_start
        text = " ".join(str(chunk.get("text", "")).split())
        rendered_chunks.append(
            f"[{index}] file={filename} page={page_start}-{page_end}\n{text[:500]}"
        )

    evidence_block = "\n\n".join(rendered_chunks)

    return f"""
YOU ARE A PRECISION ANALYST.
The exact facts below were extracted deterministically from the source documents and are already trusted.
Your job is ONLY to add a short interpretation or connective summary.

USER QUESTION:
{query}

EXTRACTED FACTS:
{extracted_facts}

SUPPORTING EVIDENCE:
{evidence_block}

RULES:
1. Do NOT change, reinterpret, or contradict any extracted fact.
2. Do NOT introduce new dates, clauses, costs, names, or values.
3. Keep the response to 2-4 short sentences.
4. Focus on separating tender facts from resume facts where useful.
5. If there is no meaningful interpretation to add, reply exactly: NO_ADDITIONAL_INTERPRETATION
""".strip()


def build_fallback_answer(scope_label: str, chunks: list[dict]) -> str:
    if not chunks:
        return f"No relevant uploaded {scope_label} context was found."

    snippets = []
    for chunk in chunks[:3]:
        filename = chunk.get("filename", "unknown.pdf")
        page = chunk.get("page_start") or "?"
        text = " ".join(str(chunk.get("text", "")).split())[:220]
        snippets.append(f"{filename} (page {page}): {text}")

    return f"LLM answer unavailable. Most relevant {scope_label} context: " + " | ".join(snippets)
