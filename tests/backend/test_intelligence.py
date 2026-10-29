import io
import zipfile

import pytest
from app.core.config import get_settings
from app.providers.documents import DocumentError, extract_local
from app.worker import process_one
from conftest import PASSWORD, Harness, run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def docx(text: str) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    content = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo("[Content_Types].xml"), content)
        archive.writestr(zipfile.ZipInfo("word/document.xml"), document)
    return output.getvalue()


def pdf(lines: list[str], open_action: bytes | None = None) -> bytes:
    commands = ["BT /F1 11 Tf 72 740 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(("" if index == 0 else "0 -18 Td ") + f"({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    catalog = b"<< /Type /Catalog /Pages 2 0 R"
    if open_action is not None:
        catalog += b" /OpenAction " + open_action
    catalog += b" >>"
    objects = [
        catalog,
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


RESUME_TEXT = """Development Test Candidate
Email: candidate@example.com
Phone: +91 98765 43210
Location: Pune, India
Summary
Backend engineer building dependable web services.
Experience
Backend Engineer at Example Labs
Built REST APIs using Python and FastAPI. Deployed PostgreSQL services with Docker.
Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes
Education
MCA, Development Test Institute
Projects
Created an interview preparation portal using React and Next.js.
Certifications
Cloud fundamentals certificate
Achievements
Reduced deployment time through CI/CD automation.
"""

JOB_TEXT = """Required Skills:
Python
FastAPI
Kubernetes
Preferred Skills:
AWS
Responsibilities:
Build and maintain REST APIs for customer-facing systems.
Qualifications:
3+ years of backend engineering experience.
Bachelor degree in computer science or equivalent experience.
"""


def signed_in(identity):
    assert identity.register().status_code == 201
    assert identity.login().status_code == 200
    return identity


def upload(identity, name="resume.docx", data=None):
    return identity.request(
        "POST",
        "/resumes",
        headers={"X-CSRF-Token": identity.csrf},
        files={"file": (name, data if data is not None else docx(RESUME_TEXT))},
    )


def mutate(identity, method, path, payload=None):
    return identity.request(
        method,
        path,
        headers={"X-CSRF-Token": identity.csrf},
        json=payload,
    )


def run_worker(identity):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def work():
        try:
            return await process_one(factory)
        finally:
            await engine.dispose()

    return run(work())


def test_resume_upload_extracts_real_docx_and_persists_evidence(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    response = upload(identity)
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "uploaded"
    stored = identity.sql("SELECT storage_key, sha256, extracted_text FROM resumes")[0]
    assert (tmp_path / stored["storage_key"]).read_bytes() == docx(RESUME_TEXT)
    assert len(stored["sha256"]) == 64 and stored["extracted_text"] is None

    assert run_worker(identity)
    parsed = identity.request("GET", f"/resumes/{created['id']}")
    assert parsed.status_code == 200
    body = parsed.json()
    assert body["status"] == "parsed"
    assert "Built REST APIs using Python" in body["extracted_text"]
    assert body["parsed_data"]["email"] == "candidate@example.com"
    skills = {item["name"]: item for item in body["parsed_data"]["skills"]}
    assert skills["Python"]["evidence"][0]["quote"]
    assert {"Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"} <= set(skills)
    assert len(identity.sql("SELECT * FROM resume_skills")) >= 5


def test_pdf_resume_extraction(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    document = pdf(
        [
            "Development PDF Candidate",
            "Email: pdf@example.com",
            "Experience",
            "Built Python services using FastAPI and PostgreSQL.",
            "Skills",
            "Python FastAPI PostgreSQL",
        ]
    )
    created = upload(identity, "resume.pdf", document)
    assert created.status_code == 202
    assert run_worker(identity)
    parsed = identity.request("GET", f"/resumes/{created.json()['id']}").json()
    assert parsed["status"] == "parsed"
    assert "Built Python services" in parsed["extracted_text"]
    assert {skill["name"] for skill in parsed["parsed_data"]["skills"]} >= {
        "Python",
        "FastAPI",
        "PostgreSQL",
    }


def test_pdf_internal_open_action_is_safe_but_scripts_are_rejected(tmp_path):
    lines = ["Experience", "Built Python services using FastAPI and PostgreSQL."]
    path = tmp_path / "resume.pdf"
    path.write_bytes(pdf(lines, b"<< /S /GoTo /D [3 0 R /Fit] >>"))
    assert "Built Python services" in extract_local(path)

    path.write_bytes(pdf(lines, b"<< /S /JavaScript /JS (app.alert) >>"))
    with pytest.raises(DocumentError, match="Active or form PDF"):
        extract_local(path)

    path.write_bytes(pdf(lines, b"<< /S /GoTo /D [3 0 R /Fit] /Next << /S /JavaScript /JS (app.alert) >> >>"))
    with pytest.raises(DocumentError, match="Active or form PDF"):
        extract_local(path)


def test_resume_rejects_unsupported_oversized_and_invalid_documents(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    assert upload(identity, "resume.txt", b"plain text").status_code == 415
    assert upload(identity, "resume.pdf", b"not a PDF").status_code == 422
    oversized = upload(identity, "resume.pdf", b"%PDF-" + b"x" * (10 * 1024 * 1024))
    assert oversized.status_code == 413
    assert not identity.sql("SELECT * FROM resumes")
    assert not list(tmp_path.glob("*"))


def test_resume_failure_retry_replacement_and_deletion(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    failed = upload(identity, data=docx("tiny text"))
    assert failed.status_code == 202
    assert run_worker(identity)
    detail = identity.request("GET", f"/resumes/{failed.json()['id']}").json()
    assert detail["status"] == "failed"
    assert "No readable text" in detail["error"]
    retry = mutate(identity, "POST", f"/resumes/{detail['id']}/retry", {})
    assert retry.status_code == 202 and retry.json()["status"] == "uploaded"

    replacement = identity.request(
        "POST",
        f"/resumes/{detail['id']}/replace",
        headers={"X-CSRF-Token": identity.csrf},
        files={"file": ("new-version.docx", docx(RESUME_TEXT))},
    )
    assert replacement.status_code == 202
    assert replacement.json()["version"] == 2
    assert len(identity.sql("SELECT * FROM resumes")) == 2
    key = identity.sql("SELECT storage_key FROM resumes WHERE id=%s", (detail["id"],))[0][
        "storage_key"
    ]
    removed = mutate(identity, "DELETE", f"/resumes/{detail['id']}")
    assert removed.status_code == 204
    assert not (tmp_path / key).exists()
    assert len(identity.sql("SELECT * FROM resumes")) == 1


def test_job_analysis_skill_normalization_and_match_persistence(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    resume = upload(identity).json()
    assert run_worker(identity)
    created = mutate(
        identity,
        "POST",
        "/jobs",
        {
            "title": "Backend Engineer",
            "company": "Example Company",
            "description": JOB_TEXT,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    analyzed = mutate(identity, "POST", f"/jobs/{job_id}/analyze", {})
    assert analyzed.status_code == 200
    requirements = {item["name"]: item for item in analyzed.json()["analysis"]["skills"]}
    assert requirements["Python"]["requirement"] == "required"
    assert requirements["AWS"]["requirement"] == "preferred"
    assert requirements["Python"]["evidence"][0]["quote"] == "Python"

    matched = mutate(identity, "POST", f"/jobs/{job_id}/match", {"resume_id": resume["id"]})
    assert matched.status_code == 200
    result = {item["name"]: item for item in matched.json()["result"]["skills"]}
    assert result["Python"]["status"] == "demonstrated"
    assert result["Kubernetes"]["status"] == "partial"
    assert result["AWS"]["status"] == "not_demonstrated"
    assert "score" not in matched.json()["result"]
    saved = identity.request("GET", f"/jobs/{job_id}/match")
    assert saved.status_code == 200 and saved.json()["id"] == matched.json()["id"]
    assert len(identity.sql("SELECT * FROM candidate_job_matches")) == 1

    updated = mutate(
        identity,
        "PATCH",
        f"/jobs/{job_id}",
        {
            "expected_version": 1,
            "title": "Senior Backend Engineer",
            "company": "Example Company",
            "description": JOB_TEXT + "\nDocker required.",
        },
    )
    assert updated.status_code == 200 and updated.json()["status"] == "draft"
    assert (
        mutate(identity, "POST", f"/jobs/{job_id}/match", {"resume_id": resume["id"]}).status_code
        == 409
    )
    stale = identity.request("GET", f"/jobs/{job_id}/match")
    assert stale.status_code == 200 and stale.json()["stale"] is True


def test_resume_job_and_match_ownership_and_authentication(identity, tmp_path):
    signed_in(identity)
    get_settings().storage_root = tmp_path
    resume = upload(identity).json()
    job = mutate(
        identity,
        "POST",
        "/jobs",
        {
            "title": "Backend Engineer",
            "description": JOB_TEXT,
        },
    ).json()
    assert mutate(identity, "POST", f"/jobs/{job['id']}/analyze", {}).status_code == 200

    other = Harness(identity.url)
    assert other.register("other@example.com").status_code == 201
    assert other.login("other@example.com", PASSWORD).status_code == 200
    for path in [f"/resumes/{resume['id']}", f"/jobs/{job['id']}", f"/jobs/{job['id']}/match"]:
        assert other.request("GET", path).status_code == 404
    assert mutate(other, "DELETE", f"/resumes/{resume['id']}").status_code == 404
    assert mutate(other, "POST", f"/jobs/{job['id']}/analyze", {}).status_code == 404

    anonymous = Harness(identity.url)
    assert anonymous.request("GET", "/resumes").status_code == 401
    assert anonymous.request("GET", "/jobs").status_code == 401


def test_job_validation_conflict_and_delete(identity):
    signed_in(identity)
    assert (
        mutate(identity, "POST", "/jobs", {"title": "x", "description": "short"}).status_code == 422
    )
    created = mutate(
        identity, "POST", "/jobs", {"title": "Backend Engineer", "description": JOB_TEXT}
    ).json()
    conflict = mutate(
        identity,
        "PATCH",
        f"/jobs/{created['id']}",
        {
            "expected_version": 2,
            "title": "Changed",
            "company": None,
            "description": JOB_TEXT,
        },
    )
    assert conflict.status_code == 409
    assert mutate(identity, "DELETE", f"/jobs/{created['id']}").status_code == 204
    assert identity.request("GET", f"/jobs/{created['id']}").status_code == 404
