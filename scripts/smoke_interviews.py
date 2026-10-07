"""Live Phase 4 journey through the UI proxy with the configured real LLM provider."""

import io
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import psycopg
from app.core.config import get_settings
from sqlalchemy.engine import make_url


def docx(text: str) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
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
email = f"phase4-smoke-{int(datetime.now(timezone.utc).timestamp())}@example.com"
password = "Temporary-Phase4-smoke-passphrase-42"
interview_id = None
csrf = ""
with httpx.Client(base_url=base, headers={"Origin": base}, timeout=60) as client:
    try:
        expect(
            client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Development Phase 4 QA",
                },
            ),
            201,
        )
        csrf = expect(
            client.post("/api/v1/auth/login", json={"email": email, "password": password}), 200
        ).json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        provider = expect(client.get("/api/v1/interviews/provider"), 200).json()
        if not provider["configured"]:
            print(provider["message"], file=sys.stderr)
            raise SystemExit(2)
        resume = expect(
            client.post(
                "/api/v1/resumes",
                headers=headers,
                files={
                    "file": (
                        "phase4-qa.docx",
                        docx("""Phase 4 QA Candidate
Backend engineer building dependable APIs.
Experience
Built an interview application with Python, FastAPI and PostgreSQL.
Projects
Designed authenticated REST APIs and deployed services with Docker.
Skills
Python, FastAPI, PostgreSQL, Docker
"""),
                    )
                },
            ),
            202,
        ).json()
        for _ in range(60):
            resume = expect(client.get(f"/api/v1/resumes/{resume['id']}"), 200).json()
            if resume["status"] in {"parsed", "failed"}:
                break
            time.sleep(0.5)
        if resume["status"] != "parsed":
            raise RuntimeError("Resume did not parse")
        job = expect(
            client.post(
                "/api/v1/jobs",
                headers=headers,
                json={
                    "title": "Backend Engineer",
                    "company": "Phase 4 QA",
                    "description": "Required Skills:\nPython\nFastAPI\nPostgreSQL\nDocker\nResponsibilities:\nBuild reliable authenticated APIs.",
                },
            ),
            201,
        ).json()
        expect(client.post(f"/api/v1/jobs/{job['id']}/analyze", headers=headers, json={}), 200)
        expect(
            client.post(
                f"/api/v1/jobs/{job['id']}/match", headers=headers, json={"resume_id": resume["id"]}
            ),
            200,
        )
        interview = expect(
            client.post(
                "/api/v1/interviews",
                headers=headers,
                json={
                    "interview_type": "technical",
                    "mode": "practice",
                    "job_id": job["id"],
                    "resume_id": resume["id"],
                    "question_limit": 2,
                    "duration_minutes": 15,
                    "selected_topics": ["FastAPI", "PostgreSQL"],
                    "difficulty": 2,
                    "candidate_focus": "API reliability",
                    "instructions": "Ask for concrete trade-offs",
                    "show_hints": True,
                },
            ),
            201,
        ).json()
        interview_id = interview["id"]
        expect(
            client.post(
                f"/api/v1/interviews/{interview_id}/start",
                headers=headers,
                json={"expected_revision": interview["revision"]},
            ),
            202,
        )
        for _ in range(90):
            interview = expect(client.get(f"/api/v1/interviews/{interview_id}"), 200).json()
            if interview["status"] in {"waiting_for_answer", "failed"}:
                break
            time.sleep(1)
        if interview["status"] != "waiting_for_answer":
            raise RuntimeError(f"Planning failed: {interview.get('error')}")
        expect(
            client.post(
                f"/api/v1/interviews/{interview_id}/answers",
                headers=headers,
                json={
                    "question_id": interview["current"]["id"],
                    "text": "I used request validation, explicit transactions, bounded connection pools, timeouts and metrics so failures remained visible and writes stayed consistent.",
                    "duration_seconds": 40,
                    "expected_revision": interview["revision"],
                    "idempotency_key": str(uuid4()),
                },
            ),
            202,
        )
        for _ in range(90):
            interview = expect(client.get(f"/api/v1/interviews/{interview_id}"), 200).json()
            if interview["status"] in {"waiting_for_answer", "completed", "failed"}:
                break
            time.sleep(1)
        if interview["status"] == "failed":
            raise RuntimeError(f"Evaluation failed: {interview.get('error')}")
        answers = expect(client.get(f"/api/v1/interviews/{interview_id}/answers"), 200).json()
        if not answers or not answers[0]["evaluation"] or not answers[0]["decision"]:
            raise RuntimeError("Evaluation or adaptive decision was not persisted")
        if interview["status"] != "completed":
            interview = expect(
                client.post(
                    f"/api/v1/interviews/{interview_id}/complete",
                    headers=headers,
                    json={"expected_revision": interview["revision"]},
                ),
                200,
            ).json()
        dsn = (
            make_url(get_settings().database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(dsn) as connection:
            persisted = connection.execute(
                "SELECT (SELECT count(*) FROM interview_plans WHERE interview_id=%s), (SELECT count(*) FROM interview_questions WHERE interview_id=%s), (SELECT count(*) FROM interview_answers WHERE interview_id=%s), (SELECT count(*) FROM answer_evaluations WHERE interview_id=%s), (SELECT count(*) FROM adaptive_decisions WHERE interview_id=%s)",
                (interview_id,) * 5,
            ).fetchone()
            if not all(value >= 1 for value in persisted):
                raise RuntimeError(f"Persistence check failed: {persisted}")
        print(
            "Phase 4 live LLM smoke passed: plan, question, answer, evaluation, adaptive decision, next state, and completion."
        )
    finally:
        if csrf:
            client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}, json={})
        dsn = (
            make_url(get_settings().database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "DELETE FROM users WHERE email=%s AND display_name=%s",
                (email, "Development Phase 4 QA"),
            )
            connection.commit()
