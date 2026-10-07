from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import get_settings
from app.core.security import COOKIE_NAME, digest, verify_password
from conftest import PASSWORD, Harness


def signed_in(identity):
    assert identity.register().status_code == 201
    assert identity.login().status_code == 200
    return identity


def test_registration_persists_user_profile_and_hash(identity):
    response = identity.register()
    assert response.status_code == 201
    assert response.json()["role"] == "candidate"
    assert "password" not in response.text
    user = identity.sql("SELECT * FROM users")[0]
    assert user["password_hash"].startswith("$argon2id$")
    assert verify_password(PASSWORD, user["password_hash"])
    assert len(identity.sql("SELECT * FROM candidates")) == 1
    assert len(identity.sql("SELECT * FROM candidate_preferences")) == 1


def test_duplicate_email_case_insensitive(identity):
    assert identity.register("Candidate@example.com").status_code == 201
    assert identity.register("CANDIDATE@EXAMPLE.COM").status_code == 409
    assert len(identity.sql("SELECT * FROM users")) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"display_name": "  "},
        {"role": "admin"},
        {"password": "x" * 129},
        {"password": " " * 12},
    ],
)
def test_registration_validation_and_no_role_escalation(identity, values):
    response = identity.register(**values)
    assert response.status_code == 422
    assert not identity.sql("SELECT * FROM users")
    assert '"input"' not in response.text
    assert PASSWORD not in response.text


def test_successful_login_cookie_session_and_current_user(identity):
    identity.register()
    response = identity.login()
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    token = identity.cookies.get(COOKIE_NAME)
    session = identity.sql("SELECT * FROM sessions")[0]
    assert bytes(session["token_hash"]) == digest(token)
    assert token not in response.text
    current = identity.request("GET", "/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["email"] == "candidate@example.com"
    assert current.json()["csrf_token"] == identity.csrf
    assert current.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "email,password",
    [("candidate@example.com", "wrong-password"), ("missing@example.com", PASSWORD)],
)
def test_invalid_credentials(identity, email, password):
    identity.register()
    response = identity.login(email, password)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email or password is incorrect."
    assert not identity.sql("SELECT * FROM sessions")


def test_protected_endpoints_without_authentication(identity):
    assert identity.request("GET", "/auth/session").status_code == 401
    assert identity.request("GET", "/candidates/me").status_code == 401
    assert identity.patch({"expected_revision": 0, "headline": "Attack"}).status_code == 401


def test_profile_creation_update_and_retrieval(identity):
    signed_in(identity)
    original = identity.request("GET", "/candidates/me").json()
    assert original["headline"] is None and original["revision"] == 0
    payload = {
        "expected_revision": 0,
        "display_name": "Updated Development Candidate",
        "phone": "+91 9000000000",
        "location": "Pune",
        "headline": "Backend developer",
        "biography": "Development test profile",
        "timezone": "Asia/Kolkata",
        "experience_months": 18,
        "career_interests": ["Distributed systems", "AI"],
        "goals": [{"role_title": "Backend engineer", "priority": 0, "active": True}],
        "education": [
            {
                "institution": "Test Institute",
                "qualification": "MCA",
                "start_date": "2024-01-01",
                "end_date": "2026-01-01",
            }
        ],
        "experience": [
            {
                "organization": "Test Organization",
                "title": "Intern",
                "description": "API development",
            }
        ],
        "preferences": {
            "interview_mode": "voice",
            "interview_duration_minutes": 30,
            "locale": "en-IN",
        },
    }
    updated = identity.patch(payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 1
    assert identity.request("GET", "/candidates/me").json() == updated.json()
    assert identity.sql("SELECT headline FROM candidates")[0]["headline"] == "Backend developer"
    assert (
        identity.sql("SELECT qualification FROM candidate_education")[0]["qualification"] == "MCA"
    )
    # Fresh login sees the committed profile, not client-local data.
    fresh = Harness(identity.url)
    assert fresh.login().status_code == 200
    assert fresh.request("GET", "/candidates/me").json()["headline"] == "Backend developer"


def test_partial_update_clear_and_revision_conflict(identity):
    signed_in(identity)
    assert (
        identity.patch(
            {
                "expected_revision": 0,
                "headline": "Before",
                "goals": [{"role_title": "Engineer"}],
            }
        ).status_code
        == 200
    )
    assert identity.patch({"expected_revision": 0, "headline": "Stale"}).status_code == 409
    updated = identity.patch({"expected_revision": 1, "headline": None, "goals": []})
    assert updated.status_code == 200
    assert updated.json()["headline"] is None and updated.json()["goals"] == []
    assert updated.json()["display_name"] == "Development Test Candidate"


def test_another_candidate_cannot_be_read_or_changed(identity):
    signed_in(identity)
    first = identity.request("GET", "/candidates/me").json()
    other = Harness(identity.url)
    other.register("other@example.com")
    other.login("other@example.com")
    assert other.request("GET", f"/candidates/{first['id']}").status_code == 404
    assert (
        other.request(
            "PATCH", f"/candidates/{first['id']}", json={"headline": "stolen"}
        ).status_code
        == 404
    )
    assert (
        other.patch(
            {"expected_revision": 0, "user_id": first["user_id"], "headline": "stolen"}
        ).status_code
        == 422
    )
    assert other.patch({"expected_revision": 0, "headline": "Own profile"}).status_code == 200
    assert identity.request("GET", "/candidates/me").json()["headline"] is None


def test_csrf_and_origin_checks(identity):
    signed_in(identity)
    assert (
        identity.request("PATCH", "/candidates/me", json={"expected_revision": 0}).status_code
        == 403
    )
    assert identity.patch({"expected_revision": 0}, **{"X-CSRF-Token": "wrong"}).status_code == 403
    assert (
        identity.patch({"expected_revision": 0}, Origin="https://evil.example").status_code == 403
    )
    assert (
        identity.request(
            "POST",
            "/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"email": "candidate@example.com", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_logout_revokes_cookie_and_prevents_replay(identity):
    signed_in(identity)
    token = identity.cookies.get(COOKIE_NAME)
    response = identity.request(
        "POST", "/auth/logout", headers={"X-CSRF-Token": identity.csrf}, json={}
    )
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert identity.request("GET", "/auth/session").status_code == 401
    identity.cookies.set(COOKIE_NAME, token)
    assert identity.request("GET", "/candidates/me").status_code == 401


def test_login_rotates_previous_session(identity):
    signed_in(identity)
    old = identity.cookies.get(COOKIE_NAME)
    assert identity.login().status_code == 200
    assert identity.cookies.get(COOKIE_NAME) != old
    attacker = Harness(identity.url)
    attacker.cookies.set(COOKIE_NAME, old)
    assert attacker.request("GET", "/auth/session").status_code == 401


def test_expired_session_rejected(identity):
    signed_in(identity)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    identity.sql(
        "UPDATE sessions SET created_at=%s, expires_at=%s",
        (past, past + timedelta(hours=1)),
    )
    assert identity.request("GET", "/auth/session").status_code == 401


def test_disabled_account_and_role_checks(identity):
    signed_in(identity)
    identity.sql("UPDATE users SET role='recruiter'")
    assert identity.request("GET", "/candidates/me").status_code == 403
    assert identity.patch({"expected_revision": 0}).status_code == 403
    identity.sql("UPDATE users SET disabled_at=now()")
    assert identity.request("GET", "/auth/session").status_code == 401
    assert identity.login().status_code == 401


def test_database_backed_rate_limit(identity, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_rate_limit_attempts", 2)
    assert identity.login("absent@example.com").status_code == 401
    assert identity.login("absent@example.com").status_code == 401
    assert identity.login("absent@example.com").status_code == 429


@pytest.mark.parametrize(
    "payload",
    [
        {"timezone": "Bad/Zone"},
        {"experience_months": -1},
        {"display_name": None},
        {"goals": [{"role_title": "Engineer"}, {"role_title": "engineer"}]},
        {
            "education": [
                {
                    "institution": "School",
                    "qualification": "MCA",
                    "start_date": "2026-01-01",
                    "end_date": "2024-01-01",
                }
            ]
        },
    ],
)
def test_profile_validation(identity, payload):
    signed_in(identity)
    assert identity.patch({"expected_revision": 0, **payload}).status_code == 422
    assert identity.request("GET", "/candidates/me").json()["revision"] == 0


def test_csrf_token_cannot_cross_sessions(identity):
    signed_in(identity)
    other = Harness(identity.url)
    other.register("other@example.com")
    other.login("other@example.com")
    assert (
        identity.patch({"expected_revision": 0}, **{"X-CSRF-Token": other.csrf}).status_code == 403
    )


def test_auth_requires_origin_and_limits_request_size(identity):
    assert (
        identity.request(
            "POST",
            "/auth/login",
            headers={"Origin": ""},
            json={"email": "candidate@example.com", "password": PASSWORD},
        ).status_code
        == 403
    )
    assert (
        identity.request(
            "POST",
            "/auth/register",
            content=b"x" * 65537,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_secure_cookie_setting(identity, monkeypatch):
    identity.register()
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    response = identity.login()
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
