from io import BytesIO
from uuid import uuid4

from conftest import Harness, run
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_interviews import FakeProvider, create_interview, mutate, signed_in, worker

from app.services.reporting import make_pdf
from app.worker import update_heartbeat


def test_pdf_renderer_emits_readable_pdf():
    snapshot = {
        "candidate": {"display_name": "Evidence Candidate", "headline": "Backend engineer"},
        "interview": {"type": "technical", "mode": "practice", "completed_at": "2026-10-02", "job_title": "Platform Engineer"},
        "performance": {"dimension_averages": {key: 0.7 for key in ("correctness", "relevance", "completeness", "technical_depth", "reasoning", "clarity")}, "evaluated_answers": 1},
        "strengths": ["Explains database tradeoffs"], "development_areas": ["Add a rollback example"],
        "evaluations": [{"sequence": 1, "topic": "databases", "difficulty": 3, "question": "How do transactions help?", "answer_excerpt": "They keep updates consistent.", "answer_truncated": False, "dimensions": {"correctness": 0.7}, "sources": [], "adaptive_decision": None}],
        "knowledge_gaps": [], "learning": [], "coding": [], "communication": [],
        "integrity": {"total_events": 0, "event_counts": {}, "note": "Observable visual signals only."},
        "career": None, "limitations": ["This is not a hiring score."],
    }
    pdf = make_pdf(snapshot, 1)
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) >= 1
    assert "Evidence Candidate" in text
    assert "not a hiring score" in text


def test_reports_analytics_and_roles_enforce_candidate_access(identity):
    assert identity.register().status_code == 201
    assert identity.login().status_code == 200
    assert identity.request("GET", "/reports").json() == []
    assert identity.request("GET", "/analytics/overview").json()["data_state"] == "insufficient_data"
    assert identity.request("GET", "/analytics/skills").json()["items"] == []
    assert identity.request("GET", "/analytics/learning").json()["items"] == []
    assert identity.request("GET", "/applications/jobs").json()["items"] == []
    assert identity.request("GET", "/recruiter/jobs").status_code == 403
    assert identity.request("GET", "/admin/system-status").status_code == 403


def test_report_generation_requires_csrf_and_owned_completed_interview(identity):
    identity.register()
    identity.login()
    response = identity.request("POST", f"/reports/{uuid4()}/generate", json={}, headers={"X-CSRF-Token": identity.csrf})
    assert response.status_code == 404
    response = identity.request("POST", f"/reports/{uuid4()}/generate", json={})
    assert response.status_code == 403


def test_admin_readiness_and_role_changes_are_scoped_and_audited(identity):
    identity.register(email="administrator@example.com")
    identity.register(email="new-recruiter@example.com")
    admin_id = identity.sql("SELECT id FROM users WHERE email = %s", ("administrator@example.com",))[0]["id"]
    identity.sql("UPDATE users SET role = 'admin' WHERE id = %s", (admin_id,))
    assert identity.login(email="administrator@example.com").status_code == 200
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def heartbeat():
        try:
            await update_heartbeat(factory)
        finally:
            await engine.dispose()
    run(heartbeat())
    status = identity.request("GET", "/admin/system-status")
    assert status.status_code == 200
    body = status.json()
    assert body["database"] == "connected"
    assert body["worker"]["status"] == "running"
    assert "api_key" not in str(body).lower()
    assert "secret" not in str(body).lower()
    target_id = identity.sql("SELECT id FROM users WHERE email = %s", ("new-recruiter@example.com",))[0]["id"]
    changed = identity.request("PATCH", f"/admin/users/{target_id}/role", headers={"X-CSRF-Token": identity.csrf}, json={"role": "recruiter"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "recruiter"
    assert identity.request("GET", "/admin/audit").json()["items"][0]["action"] == "user_role_changed"
    self_demotion = identity.request("PATCH", f"/admin/users/{admin_id}/role", headers={"X-CSRF-Token": identity.csrf}, json={"role": "candidate"})
    assert self_demotion.status_code == 409


def test_recruiter_job_ownership_and_candidate_job_board(identity):
    identity.register(email="recruiter-one@example.com")
    first_id = identity.sql("SELECT id FROM users WHERE email = %s", ("recruiter-one@example.com",))[0]["id"]
    identity.sql("UPDATE users SET role = 'recruiter' WHERE id = %s", (first_id,))
    assert identity.login(email="recruiter-one@example.com").status_code == 200
    created = identity.request("POST", "/recruiter/jobs", headers={"X-CSRF-Token": identity.csrf}, json={"title": "Platform Engineer", "company": "Example Co", "description": "Build reliable data systems with Python and PostgreSQL across a growing platform team."})
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert identity.request("GET", "/recruiter/jobs").json()[0]["id"] == job_id
    assert identity.request("GET", "/applications/jobs").json()["items"][0]["id"] == job_id
    identity.register(email="recruiter-two@example.com")
    second_id = identity.sql("SELECT id FROM users WHERE email = %s", ("recruiter-two@example.com",))[0]["id"]
    identity.sql("UPDATE users SET role = 'recruiter' WHERE id = %s", (second_id,))
    assert identity.login(email="recruiter-two@example.com").status_code == 200
    assert identity.request("GET", "/recruiter/jobs").json() == []
    assert identity.request("PATCH", f"/recruiter/jobs/{job_id}", headers={"X-CSRF-Token": identity.csrf}, json={"expected_version": 1, "status": "closed"}).status_code == 404


def test_completed_interview_report_and_consent_scoped_recruiter_pdf(identity):
    signed_in(identity)
    description = "Build reliable services with Python and PostgreSQL, design clear APIs, and improve production observability with the platform engineering team."
    target = mutate(identity, "POST", "/jobs", {"title": "Platform Engineer", "company": "Example Co", "description": description}).json()
    analyzed = identity.request("POST", f"/jobs/{target['id']}/analyze", headers={"X-CSRF-Token": identity.csrf}, json={})
    assert analyzed.status_code == 200 and analyzed.json()["status"] == "analyzed"
    interview = create_interview(identity, mode="simulation", question_limit=1, job_id=target["id"]).json()
    assert mutate(identity, "POST", f"/interviews/{interview['id']}/start", {"expected_revision": 0}).status_code == 202
    provider = FakeProvider()
    assert worker(identity, provider)
    current = identity.request("GET", f"/interviews/{interview['id']}").json()
    answer = {"question_id": current["current"]["id"], "text": "I build typed APIs, manage PostgreSQL transactions, use bounded timeouts, and add observability to detect service regressions.", "duration_seconds": 35, "expected_revision": current["revision"], "idempotency_key": str(uuid4())}
    assert mutate(identity, "POST", f"/interviews/{interview['id']}/answers", answer).status_code == 202
    assert worker(identity, provider)
    assert identity.request("GET", f"/interviews/{interview['id']}").json()["status"] == "completed"
    report_response = identity.request("POST", f"/reports/{interview['id']}/generate", headers={"X-CSRF-Token": identity.csrf}, json={})
    assert report_response.status_code == 200
    report_id = report_response.json()["id"]
    pdf = identity.request("GET", f"/reports/{report_id}/pdf")
    assert pdf.status_code == 200 and PdfReader(BytesIO(pdf.content)).pages

    recruiter = Harness(identity.url)
    assert recruiter.register("phase12-recruiter@example.com").status_code == 201
    recruiter_id = recruiter.sql("SELECT id FROM users WHERE email = %s", ("phase12-recruiter@example.com",))[0]["id"]
    recruiter.sql("UPDATE users SET role = 'recruiter' WHERE id = %s", (recruiter_id,))
    assert recruiter.login("phase12-recruiter@example.com", "Development-test-passphrase-42").status_code == 200
    posting = recruiter.request("POST", "/recruiter/jobs", headers={"X-CSRF-Token": recruiter.csrf}, json={"title": "Platform Engineer", "company": "Example Co", "description": description})
    assert posting.status_code == 201
    application = identity.request("POST", "/applications", headers={"X-CSRF-Token": identity.csrf}, json={"recruiter_job_id": posting.json()["id"], "candidate_job_id": target["id"], "share_consent": True})
    assert application.status_code == 201
    list_response = recruiter.request("GET", f"/recruiter/jobs/{posting.json()['id']}/applications")
    assert len(list_response.json()["items"]) == 1
    detail = recruiter.request("GET", f"/recruiter/applications/{application.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["candidate"]["email"] == "candidate@example.com"
    assert detail.json()["reports"][0]["id"] == report_id
    recruiter_pdf = recruiter.request("GET", f"/recruiter/applications/{application.json()['id']}/reports/{report_id}/pdf")
    assert recruiter_pdf.status_code == 200 and PdfReader(BytesIO(recruiter_pdf.content)).pages
    withdrawn = identity.request("PATCH", f"/applications/{application.json()['id']}", headers={"X-CSRF-Token": identity.csrf}, json={"status": "withdrawn"})
    assert withdrawn.status_code == 200
    assert recruiter.request("GET", f"/recruiter/jobs/{posting.json()['id']}/applications").json()["items"] == []
