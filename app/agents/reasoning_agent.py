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
    You are an AI Recruitment Lead. Summarize the search results for the user query: "{query}"
    
    Found {len(enriched_matches)} candidates.
    Top Candidates: {", ".join(shortlist[:3])}
    
    Provide a professional 2-sentence overview of the pool's suitability for a client demo.
    """
    overall_summary = llm_text_answer(summary_prompt)

    return {
        **state,
        "matches": enriched_matches,
        "reasoning_summary": overall_summary
    }
