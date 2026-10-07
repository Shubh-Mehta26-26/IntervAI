"""Versioned vocabulary, never candidate data. Only literal source matches become evidence."""

import re

# Canonical name, category, explicit equivalent spellings. No related-skill inference.
VOCABULARY = [
    ("Python", "languages", []),
    ("JavaScript", "languages", ["Javascript"]),
    ("TypeScript", "languages", []),
    ("Java", "languages", []),
    ("C++", "languages", []),
    ("C#", "languages", []),
    ("SQL", "languages", []),
    ("HTML", "languages", []),
    ("CSS", "languages", []),
    ("FastAPI", "frameworks", ["Fast API"]),
    ("Django", "frameworks", []),
    ("Flask", "frameworks", []),
    ("React", "frameworks", ["React.js", "ReactJS"]),
    ("Next.js", "frameworks", ["NextJS"]),
    ("Node.js", "frameworks", ["NodeJS"]),
    ("PostgreSQL", "databases", ["Postgres"]),
    ("MySQL", "databases", []),
    ("SQLite", "databases", []),
    ("MongoDB", "databases", []),
    ("Redis", "databases", []),
    ("Docker", "cloud_devops", []),
    ("Kubernetes", "cloud_devops", ["K8s"]),
    ("AWS", "cloud_devops", ["Amazon Web Services"]),
    ("Azure", "cloud_devops", ["Microsoft Azure"]),
    ("Google Cloud", "cloud_devops", ["GCP", "Google Cloud Platform"]),
    ("Terraform", "cloud_devops", []),
    ("CI/CD", "cloud_devops", ["continuous integration"]),
    ("Git", "tools", []),
    ("Linux", "tools", []),
    ("REST APIs", "technical", ["REST API", "RESTful APIs"]),
    ("Machine Learning", "ai_ml", []),
    ("Deep Learning", "ai_ml", []),
    ("TensorFlow", "ai_ml", []),
    ("PyTorch", "ai_ml", []),
    ("scikit-learn", "ai_ml", ["sklearn"]),
    ("pandas", "ai_ml", []),
    ("NumPy", "ai_ml", []),
    ("LangChain", "ai_ml", []),
    ("LangGraph", "ai_ml", []),
    ("RAG", "ai_ml", ["retrieval augmented generation", "retrieval-augmented generation"]),
    ("Communication", "soft_skills", ["communication skills"]),
    ("Teamwork", "soft_skills", ["team collaboration"]),
    ("Problem solving", "soft_skills", ["problem-solving"]),
    ("Leadership", "soft_skills", []),
    ("Agile", "technical", []),
    ("Testing", "technical", ["unit testing"]),
]


def slug(name: str) -> str:
    return re.sub(
        r"[^a-z0-9]+", "-", name.lower().replace("++", " plus plus").replace("#", " sharp")
    ).strip("-")


def canonical_skills(text: str):
    found = []
    for name, category, aliases in VOCABULARY:
        if any(
            re.search(r"(?<![\w+#])" + re.escape(alias) + r"(?![\w+#])", text, re.I)
            for alias in [name, *aliases]
        ):
            found.append((slug(name), name, category))
    return found
