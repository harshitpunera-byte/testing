from app.extraction import tender_extractor
from app.llm.schemas import TenderRequirements


def test_tender_extractor_falls_back_to_llm_for_missing_preferred_skills_and_experience(monkeypatch):
    def fake_llm_extract(_text: str) -> TenderRequirements:
        return TenderRequirements(
            role="Data Platform Lead",
            domain="AI/ML",
            skills_required=[{"raw": "Python", "generic": "python"}],
            preferred_skills=[{"raw": "Docker", "generic": "docker"}, {"raw": "Kubernetes", "generic": "kubernetes"}],
            experience_required=7,
            qualifications=[{"raw": "B.Tech", "generic": "btech"}],
            responsibilities=["Lead delivery"],
        )

    monkeypatch.setattr(tender_extractor, "extract_tender_requirements_llm", fake_llm_extract)

    result = tender_extractor.extract_tender_requirements(
        "Tender scope covers modernization of enterprise data systems."
    )

    # assertions update for structured list format
    assert [s["raw"] for s in result["preferred_skills"]] == ["Docker", "Kubernetes"]
    assert result["experience_required"] == 7
