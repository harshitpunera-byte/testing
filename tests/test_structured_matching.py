import json
from app.services.matching_utils import extract_structured_requirements, generate_matching_sql
from app.services.search_service import get_structured_match_plan

def test_structured_matching():
    print("🚀 Starting Structured Matching Test...\n")
    
    # 1. Mock Raw Tender Data (as if extracted by LLM)
    mock_tender_data = {
        "role": "Project Manager",
        "domain": "Highway and Expressway",
        "skills_required": ["Python", "PostgreSQL", "React"],
        "preferred_skills": ["Docker", "Kubernetes"],
        "experience_required": 10,
        "qualifications": ["B.Tech", "BE", "M.Tech"]
    }
    
    print("--- 📝 Input Tender Requirements ---")
    print(json.dumps(mock_tender_data, indent=2))
    print("\n")
    
    # 2. Extract and Normalize (Using our new Utility)
    structured_reqs = extract_structured_requirements(mock_tender_data)
    
    print("--- 🏗️ Normalized Requirements (JSON) ---")
    print(json.dumps(structured_reqs, indent=2))
    
    # VERIFICATION: Checking Synonyms
    expected_qual = "engineering_bachelor"
    if expected_qual in structured_reqs["qualifications"]:
        print(f"✅ Success: B.Tech/BE mapped to '{expected_qual}'")
    
    expected_domain = "road_transport_infrastructure"
    if structured_reqs["domain"] == expected_domain:
        print(f"✅ Success: Highway/Expressway mapped to '{expected_domain}'\n")

    # 3. Generate SQL Query
    sql_query = generate_matching_sql(structured_reqs)
    
    print("--- 💻 Generated SQL Query ---")
    print(sql_query)
    print("\n")
    
    # 4. Test the Full Match Plan (Integration Test)
    match_plan = get_structured_match_plan(mock_tender_data)
    
    print("--- 📊 Short Explanation ---")
    print(match_plan["short_explanation"])
    
    if "EXISTS" in match_plan["sql_query"] and ">= 10" in match_plan["sql_query"]:
        print("\n✅ FINAL TEST PASSED: System correctly converted Tender -> Structured JSON -> SQL.")
    else:
        print("\n❌ TEST FAILED: Check SQL generation logic.")

if __name__ == "__main__":
    test_structured_matching()
