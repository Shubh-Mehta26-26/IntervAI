"""Live Phase 3 journey through the Next.js proxy; removes its labelled QA account."""

import io
import os
import time
import zipfile
from datetime import datetime, timezone

import httpx
import psycopg
from app.core.config import get_settings
from sqlalchemy.engine import make_url


def make_docx(text: str) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{paragraphs}</w:body></w:document>",
        )
    return output.getvalue()


def expect(response, status):
    if response.status_code != status:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:300]}"
        )
    return response


base = os.environ.get("INTERVAI_BASE_URL", "http://localhost:3000").rstrip("/")
email = f"phase3-smoke-{int(datetime.now(timezone.utc).timestamp())}@example.com"
password = "Temporary-Phase3-smoke-passphrase-42"
resume_id = job_id = None
document = make_docx(
    """Development Phase 3 QA Candidate
Email: phase3.qa@example.com
Location: Pune, India
Summary
Backend engineer focused on dependable APIs.
Experience
Backend Engineer at Development Example
Built REST APIs using Python and FastAPI. Deployed PostgreSQL services with Docker.
Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes
Projects
Created an interview preparation workspace using React and Next.js.
Education
MCA, Development QA Institute
"""
)
job_text = """Required Skills:
Python
FastAPI
Kubernetes
Preferred Skills:
AWS
Responsibilities:
Build and maintain REST APIs.
Qualifications:
3+ years of backend engineering experience.
"""

with httpx.Client(
    base_url=base, headers={"Origin": base}, timeout=45, follow_redirects=False
) as client:
    try:
        expect(
            client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Development Phase 3 QA",
                },
            ),
            201,
        )
        login = expect(
            client.post("/api/v1/auth/login", json={"email": email, "password": password}), 200
        )
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        uploaded = expect(
            client.post(
                "/api/v1/resumes",
                headers=headers,
                files={"file": ("development-phase3-resume.docx", document)},
            ),
            202,
        ).json()
        resume_id = uploaded["id"]
        for _ in range(40):
            resume = expect(client.get(f"/api/v1/resumes/{resume_id}"), 200).json()
            if resume["status"] in {"parsed", "failed"}:
                break
            time.sleep(0.5)
        if resume["status"] != "parsed" or "Built REST APIs" not in resume["extracted_text"]:
            raise RuntimeError(
                f"Resume processing did not succeed: {resume['status']} {resume.get('error')}"
            )
        if {skill["name"] for skill in resume["parsed_data"]["skills"]} < {
            "Python",
            "FastAPI",
            "PostgreSQL",
            "Docker",
            "Kubernetes",
        }:
            raise RuntimeError("Expected resume skills were not extracted")
        download = expect(client.get(f"/api/v1/resumes/{resume_id}/file"), 200)
        if download.content != document:
            raise RuntimeError("Stored resume bytes differ from the uploaded document")
        job = expect(
            client.post(
                "/api/v1/jobs",
                headers=headers,
                json={
                    "title": "Backend Engineer",
                    "company": "Development Example",
                    "description": job_text,
                },
            ),
            201,
        ).json()
        job_id = job["id"]
        analysis = expect(
            client.post(f"/api/v1/jobs/{job_id}/analyze", headers=headers, json={}), 200
        ).json()
        if {item["name"] for item in analysis["analysis"]["skills"]} < {
            "Python",
            "FastAPI",
            "Kubernetes",
            "AWS",
        }:
            raise RuntimeError("Expected job skills were not extracted")
        match = expect(
            client.post(
                f"/api/v1/jobs/{job_id}/match", headers=headers, json={"resume_id": resume_id}
            ),
            200,
        ).json()
        outcomes = {item["name"]: item["status"] for item in match["result"]["skills"]}
        expected = {
            "Python": "demonstrated",
            "FastAPI": "demonstrated",
            "Kubernetes": "partial",
            "AWS": "not_demonstrated",
        }
        if any(outcomes.get(name) != status for name, status in expected.items()):
            raise RuntimeError(f"Unexpected match result: {outcomes}")
        saved = expect(client.get(f"/api/v1/jobs/{job_id}/match"), 200).json()
        if saved["id"] != match["id"] or saved["stale"]:
            raise RuntimeError("Saved match was missing or stale")

        dsn = (
            make_url(get_settings().database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(dsn) as connection:
            row = connection.execute(
                """SELECT r.status, length(r.extracted_text), jsonb_array_length(r.parsed_data->'skills'),
                          j.status, jsonb_array_length(j.analysis->'skills'), m.id IS NOT NULL
                     FROM users u JOIN candidates c ON c.user_id=u.id
                     JOIN resumes r ON r.candidate_id=c.id JOIN job_descriptions j ON j.candidate_id=c.id
                     JOIN candidate_job_matches m ON m.job_id=j.id WHERE u.email=%s""",
                (email,),
            ).fetchone()
            if row != (
                "parsed",
                len(resume["extracted_text"]),
                len(resume["parsed_data"]["skills"]),
                "analyzed",
                len(analysis["analysis"]["skills"]),
                True,
            ):
                raise RuntimeError(f"PostgreSQL persistence verification failed: {row}")
        print(
            "Phase 3 live smoke passed: upload, extraction, analysis, matching and PostgreSQL persistence."
        )
    finally:
        if job_id:
            client.delete(
                f"/api/v1/jobs/{job_id}", headers={"X-CSRF-Token": locals().get("csrf", "")}
            )
        if resume_id:
            client.delete(
                f"/api/v1/resumes/{resume_id}", headers={"X-CSRF-Token": locals().get("csrf", "")}
            )
        if "csrf" in locals():
            client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}, json={})
        dsn = (
            make_url(get_settings().database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "DELETE FROM users WHERE email=%s AND display_name=%s",
                (email, "Development Phase 3 QA"),
            )
            connection.commit()
