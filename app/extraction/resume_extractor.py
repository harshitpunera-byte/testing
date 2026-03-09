import re


def extract_resume_data(text: str):

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

    text_lower = text.lower()

    found_skills = []

    for skill in skills:
        if skill in text_lower:
            found_skills.append(skill)

    experience_match = re.search(r"(\d+)\+?\s*years", text_lower)

    experience = None
    if experience_match:
        experience = experience_match.group(1)

    return {
        "skills": found_skills,
        "experience": experience
    }