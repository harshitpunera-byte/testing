from typing import Dict, List
import json
from app.llm.provider import llm_text_answer

def _get_ai_reasoning(match: Dict, tender_reqs: Dict) -> str:
    """Uses LLM to generate a premium reasoning summary for a match."""
    prompt = f"""
    You are an AI Recruitment Specialist. Analyze the match between a candidate and a tender.
    
    Tender Requirements: {json.dumps(tender_reqs)}
    
    Candidate (Match Details): {json.dumps(match)}
    
    Task: Write a concise, professional 2-3 sentence summary explaining WHY this candidate fits OR why they are a partial match. 
    Be specific about skills and education (especially if there's a semantic match like 'BTech' vs 'Bachelor of Engineering').
    
    Return ONLY the summary text.
    """
    return llm_text_answer(prompt)

def reasoning_agent(state: Dict) -> Dict:
    matches = state.get("matches", [])
    tender_reqs = state.get("tender_requirements", {})
    query = state.get("query", "")

    enriched_matches = []
    shortlist = []
    rejected = []

    for match in matches:
        # Use LLM for premium reasoning if available, otherwise fallback to procedural
        explanation = _get_ai_reasoning(match, tender_reqs)
        
        enriched_match = {
            **match,
            "reasoning": explanation
        }
        enriched_matches.append(enriched_match)

        # Simple logic for shortlist/rejected for the summary
        score = match.get("score") or 0
        if score >= 75:
            shortlist.append(match.get("filename", match.get("candidate_name", "unknown")))
        elif score < 40:
            rejected.append(match.get("filename", match.get("candidate_name", "unknown")))

    # Generate a final overall summary
    summary_prompt = f"""
    You are an AI Recruitment Lead. Review these candidates for: "{query}"
    
    ### CANDIDATE DATA:
    {json.dumps([{ 'name': m.get('candidate_name','unknown'), 'phone': m.get('phone','N/A'), 'email': m.get('email', 'N/A')} for m in enriched_matches])}
    
    ### MANDATORY TASK:
    1. If the user query implies a list, list ALL candidates in a professional Markdown Table.
    2. COLUMNS: | Name | Phone | Email |
    3. DATA RULE: Use the 'phone' and 'email' from the CANDIDATE DATA. 
    4. If the phone/email is provided in the data, you MUST include it. Do NOT say N/A if data is present.
    5. Keep it clean and professional.
    
    Return ONLY the final markdown text.
    """
    overall_summary = llm_text_answer(summary_prompt)

    return {
        **state,
        "matches": enriched_matches,
        "reasoning_summary": overall_summary
    }
