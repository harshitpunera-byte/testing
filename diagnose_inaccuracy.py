from app.llm.intent_detector import detect_query_intent
from app.llm.query_to_sql import generate_sql_for_query
from app.services.search_service import search_resumes
import json

def debug_query(query: str):
    print(f"\n--- DEBUGGING QUERY: '{query}' ---")
    
    # 1. Intent Check
    intent_data = detect_query_intent(query)
    print(f"INTENT: {intent_data.intent}")
    print(f"SEMANTIC EXPANSION: {intent_data.semantic_expansion_terms}")
    
    # 2. SQL Check
    sql = generate_sql_for_query(query)
    print(f"GENERATED SQL:\n{sql}")
    
    # 3. Overall Results
    results = search_resumes(query)
    print(f"TOTAL FOUND: {results['total']}")
    
    # 4. Reason Check
    if results['results']:
        first = results['results'][0]
        print(f"FIRST CANDIDATE: {first['candidate_name']}")
        print(f"FIRST CANDIDATE SCORE: {first['score']}%")
        print(f"FIRST CANDIDATE REASONING: {first['reasoning']}")

print("DIAGNOSING INACCURACY...")
debug_query("list all the candidates who have done btech")
debug_query("list all the candidates who have done masters")
