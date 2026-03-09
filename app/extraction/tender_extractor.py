import re


def extract_tender_requirements(text: str):

    skills = [
        "python",
        "machine learning",
        "nlp",
        "fastapi",
        "docker",
        "aws",
        "data engineering",
        "rest api",
    ]

    found_skills = []

    text_lower = text.lower()

    for skill in skills:
        if skill in text_lower:
            found_skills.append(skill)

    experience_match = re.search(r"(\d+)\+?\s*years", text_lower)

    experience = None
    if experience_match:
        experience = experience_match.group(1)

    return {
        "skills_required": found_skills,
        "experience_required": experience
    }