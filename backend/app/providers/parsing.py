import re
from typing import Protocol

from app.providers.taxonomy import canonical_skills
from app.schemas.intelligence import Evidence, ExtractedSkill, JobAnalysis, Requirement, ResumeFacts

PARSER_VERSION = "deterministic-1"
HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "objective", "about me"],
    "education": ["education", "academic qualifications", "academic background"],
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
    ],
    "projects": ["projects", "personal projects", "academic projects", "selected projects"],
    "skills": ["skills", "technical skills", "technologies", "tools", "skills and technologies"],
    "certifications": ["certifications", "certificates", "licenses"],
    "achievements": ["achievements", "awards", "honors"],
    "required": [
        "required skills",
        "requirements",
        "essential skills",
        "must have",
        "minimum requirements",
    ],
    "preferred": ["preferred skills", "nice to have", "preferred qualifications", "desirable"],
    "responsibilities": ["responsibilities", "key responsibilities", "what you will do", "duties"],
    "qualifications": ["qualifications", "minimum qualifications", "education requirements"],
}
NEGATIVE = re.compile(
    r"\b(no experience|not experienced|without experience|not required|do not have|don't have|never used|no knowledge|lack of)\b",
    re.I,
)
APPLIED = re.compile(
    r"\b(built|developed|implemented|deployed|designed|created|maintained|used|automated|trained|integrated|optimized|managed|led|delivered)\b",
    re.I,
)


def lines(text: str, source: str):
    section = "general"
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        clean = raw.strip().strip("•- ")
        heading, sep, tail = clean.partition(":")
        key = heading.strip().lower()
        match = next((name for name, aliases in HEADINGS.items() if key in aliases), None)
        if match:
            section = match
            if not sep or not tail.strip():
                continue
        yield Evidence(
            source=source,
            quote=raw,
            line=number,
            section=section,
            kind="applied"
            if section in {"experience", "projects"}
            and APPLIED.search(raw)
            and not NEGATIVE.search(raw)
            else "mentioned",
        )


def extract_skills(evidence: list[Evidence]) -> list[ExtractedSkill]:
    found = {}
    for item in evidence:
        if NEGATIVE.search(item.quote):
            continue
        for key, name, category in canonical_skills(item.quote):
            if key not in found:
                found[key] = ExtractedSkill(slug=key, name=name, category=category, evidence=[])
            if len(found[key].evidence) < 8:
                found[key].evidence.append(item)
    return list(found.values())


class ResumeParser(Protocol):
    def parse(self, text: str, source: str) -> ResumeFacts: ...


class StructuredLLMParser(Protocol):
    """Optional semantic adapter boundary. No LLM is enabled or silently simulated."""

    def parse_resume(self, text: str) -> ResumeFacts: ...
    def parse_job(self, text: str) -> JobAnalysis: ...


class DeterministicResumeParser:
    def parse(self, text: str, source: str) -> ResumeFacts:
        evidence = list(lines(text, source))
        facts = ResumeFacts(
            skills=extract_skills(evidence),
            warnings=[
                "Deterministic extraction: section text is preserved as evidence. Review against the original; unknown fields stay empty.",
                "Skill mentions are self-reported evidence, not assessed proficiency. Vocabulary coverage is limited.",
            ],
        )
        first = text.splitlines()[0].strip()
        explicit = re.search(r"(?im)^name\s*:\s*(.{2,120})$", text)
        if explicit:
            facts.name = explicit.group(1).strip()
        elif (
            re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+){1,3}", first)
            and not canonical_skills(first)
            and first.lower() not in {"curriculum vitae", "software engineer", "development resume"}
        ):
            facts.name = first
        email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        facts.email = email.group() if email else None
        phone = re.search(r"(?im)^(?:phone|mobile|tel)\s*:\s*([+\d() .-]{7,40})$", text)
        facts.phone = phone.group(1).strip() if phone else None
        location = re.search(r"(?im)^location\s*:\s*(.{1,160})$", text)
        facts.location = location.group(1).strip() if location else None
        facts.links = list(dict.fromkeys(re.findall(r"https?://[^\s<>]+", text)))[:30]
        summary = [item.quote for item in evidence if item.section == "summary"]
        facts.summary = "\n".join(summary) or None
        for field in ["education", "experience", "projects", "certifications", "achievements"]:
            setattr(facts, field, [item for item in evidence if item.section == field][:100])
        return ResumeFacts.model_validate(facts.model_dump())


def analyze_job(text: str) -> JobAnalysis:
    evidence = list(lines(text, "job"))
    requirements = []
    for skill in extract_skills(evidence):
        levels = []
        for item in skill.evidence:
            if re.search(
                r"\b(preferred|optional|nice.to.have|a plus|desirable)\b", item.quote, re.I
            ):
                levels.append("preferred")
            elif re.search(r"\b(required|must|essential)\b", item.quote, re.I):
                levels.append("required")
            elif item.section in {"preferred", "required"}:
                levels.append(item.section)
            elif item.section == "qualifications":
                levels.append("required")
            else:
                levels.append("unspecified")
        level = (
            "required"
            if "required" in levels
            else "preferred"
            if "preferred" in levels
            else "unspecified"
        )
        requirements.append(Requirement(**skill.model_dump(), requirement=level))
    experience = [
        item
        for item in evidence
        if re.search(r"\b\d+\s*(?:[-–]\s*\d+\s*)?\+?\s*years?\b", item.quote, re.I)
    ]
    qualifications = [
        item
        for item in evidence
        if item.section in {"education", "qualifications"}
        or re.search(r"\b(degree|bachelor|master|phd|diploma)\b", item.quote, re.I)
    ]
    other = [
        item
        for item in evidence
        if item.section in {"required", "preferred"} and not canonical_skills(item.quote)
    ]
    domain = re.search(r"(?im)^domain\s*:\s*(.{1,160})$", text)
    return JobAnalysis(
        parser_version=PARSER_VERSION,
        skills=requirements,
        responsibilities=[item for item in evidence if item.section == "responsibilities"],
        qualifications=qualifications,
        experience_requirements=experience,
        other_requirements=other,
        domain=domain.group(1).strip() if domain else None,
        warnings=[
            "Only explicit skill names and equivalent aliases are recognized. Requirements without a clear required/preferred label remain unspecified.",
            "Experience, qualifications and responsibilities require review; skill evidence alone does not establish them.",
        ],
    )
