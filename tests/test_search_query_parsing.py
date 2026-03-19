from app.services.search_service import parse_search_query


def test_parse_search_query_structured_constraints():
    parsed = parse_search_query("Find Python developers with 5+ years experience in Pune under 30 days notice")

    assert parsed["mode"] in {"structured_filter", "structured_rank"}
    assert "python" in parsed["skills"]
    assert parsed["min_experience_years"] == 5
    assert parsed["location"] == "pune"


def test_parse_search_query_semantic_mode():
    parsed = parse_search_query("Find candidates who worked on claims processing and fraud analytics")

    assert parsed["mode"] in {"semantic", "hybrid"}
