"""Author a small original taxonomy; no scrape, external credential, or labour-market claim."""

import json
from pathlib import Path

aliases = {
    "Python": ["python"],
    "SQL": ["sql", "dbms", "databases"],
    "APIs": ["rest api", "rest apis", "api design", "apis"],
    "Data Structures": ["data structures", "arrays", "hash tables", "binary search"],
    "Machine Learning": ["machine learning", "ml"],
    "Model Evaluation": ["model evaluation"],
    "JavaScript": ["javascript", "js"],
    "HTML/CSS": ["html", "css"],
}
definitions = [
    (
        "software-engineer",
        "Software Engineer",
        ["Python", "Data Structures", "Software Testing"],
        ["System Design", "Git"],
        "Design, implement, test, and maintain software.",
    ),
    (
        "backend-engineer",
        "Backend Engineer",
        ["Python", "SQL", "APIs"],
        ["Docker", "System Design"],
        "Build services, database interactions, and reliable APIs.",
    ),
    (
        "frontend-engineer",
        "Frontend Engineer",
        ["JavaScript", "HTML/CSS", "React"],
        ["TypeScript", "Accessibility"],
        "Build accessible browser experiences and maintain client applications.",
    ),
    (
        "full-stack-engineer",
        "Full Stack Engineer",
        ["JavaScript", "Python", "SQL", "APIs"],
        ["React", "Docker"],
        "Connect browser experiences to application services and data.",
    ),
    (
        "ai-ml-engineer",
        "AI/ML Engineer",
        ["Python", "Machine Learning", "Model Evaluation"],
        ["Deep Learning", "MLOps", "Cloud"],
        "Develop, evaluate, and integrate machine-learning systems.",
    ),
    (
        "data-scientist",
        "Data Scientist",
        ["Python", "Statistics", "Machine Learning"],
        ["SQL", "Data Visualization"],
        "Analyze data, test hypotheses, and evaluate predictive models.",
    ),
    (
        "data-engineer",
        "Data Engineer",
        ["Python", "SQL", "Data Pipelines"],
        ["Cloud", "Distributed Systems"],
        "Build reliable data ingestion, transformation, and delivery pipelines.",
    ),
    (
        "devops-engineer",
        "DevOps Engineer",
        ["Linux", "CI/CD", "Docker"],
        ["Cloud", "Monitoring"],
        "Automate delivery and operate reliable software environments.",
    ),
    (
        "cloud-engineer",
        "Cloud Engineer",
        ["Cloud", "Networking", "Linux"],
        ["Infrastructure as Code", "Security"],
        "Design and operate cloud infrastructure and connectivity.",
    ),
    (
        "nlp-engineer",
        "NLP Engineer",
        ["Python", "NLP", "Model Evaluation"],
        ["Deep Learning", "RAG"],
        "Build and evaluate systems processing language.",
    ),
    (
        "computer-vision-engineer",
        "Computer Vision Engineer",
        ["Python", "Computer Vision", "Model Evaluation"],
        ["Deep Learning", "Deployment"],
        "Develop and evaluate image-processing systems.",
    ),
    (
        "technical-product",
        "Technical Product",
        ["Product Discovery", "Communication", "Data Analysis"],
        ["APIs", "Software Testing"],
        "Clarify product problems and coordinate evidence-informed technical delivery.",
    ),
]
roles = []
for slug, name, required, preferred, description in definitions:
    roles.append(
        {
            "slug": slug,
            "name": name,
            "description": description,
            "requirements": [
                {
                    "skill": skill,
                    "aliases": aliases.get(skill, [skill]),
                    "requirement": kind,
                    "certainty": "illustrative",
                    "related_concepts": [
                        "normalization",
                        "transactions",
                        "indexing",
                        "deadlocks",
                    ]
                    if skill == "SQL"
                    else [],
                }
                for kind, skills in [("required", required), ("preferred", preferred)]
                for skill in skills
            ],
            "responsibilities": [description],
            "version": 1,
            "provenance": {
                "kind": "project_authored",
                "source": "IntervAI career-roles-v1",
                "scope": "Illustrative exploration taxonomy; not universal hiring requirements or verified labour-market data.",
            },
        }
    )
destination = Path(__file__).resolve().parents[1] / "backend/data/career_roles_v1.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(roles, indent=2) + "\n", encoding="utf-8")
print("Wrote 12 original, versioned role definitions.")
