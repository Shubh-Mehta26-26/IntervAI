"""Exercise the running API with a clearly labelled temporary development account.

Only the account UUID created by this run is removed in the finally block.
No real candidate records are read or modified.
"""

import secrets
from uuid import uuid4

import httpx
import psycopg
from app.core.config import get_settings
from sqlalchemy.engine import make_url


def main():
    email = f"phase2-qa-{uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)
    user_id = None
    dsn = (
        make_url(get_settings().database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    try:
        with httpx.Client(
            base_url="http://localhost:3000/api/v1",
            headers={"Origin": "http://localhost:3000"},
            timeout=20,
        ) as client:
            assert client.get("/candidates/me").status_code == 401
            response = client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Development QA Candidate",
                },
            )
            assert response.status_code == 201, response.text
            user_id = response.json()["id"]
            login = client.post("/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200, login.text
            csrf = login.json()["csrf_token"]
            assert "HttpOnly" in login.headers["set-cookie"]
            token = client.cookies.get("intervai_session")
            profile = client.get("/candidates/me").json()
            result = client.patch(
                "/candidates/me",
                headers={"X-CSRF-Token": csrf},
                json={
                    "expected_revision": profile["revision"],
                    "headline": "Development persistence verification",
                    "goals": [{"role_title": "Backend engineer"}],
                    "career_interests": ["API design"],
                },
            )
            assert result.status_code == 200, result.text
            assert (
                client.get("/candidates/me").json()["headline"]
                == "Development persistence verification"
            )
            with psycopg.connect(dsn) as db:
                row = db.execute(
                    "SELECT u.role, u.password_hash LIKE '$argon2id$%%', c.headline FROM users u JOIN candidates c ON c.user_id=u.id WHERE u.id=%s",
                    (user_id,),
                ).fetchone()
                assert row == ("candidate", True, "Development persistence verification")
            assert (
                client.post("/auth/logout", headers={"X-CSRF-Token": csrf}, json={}).status_code
                == 204
            )
            assert client.get("/auth/session").status_code == 401
            replay = httpx.get(
                "http://localhost:8000/api/v1/candidates/me",
                cookies={"intervai_session": token},
                timeout=10,
            )
            assert replay.status_code == 401
            assert (
                client.post("/auth/login", json={"email": email, "password": password}).status_code
                == 200
            )
            assert (
                client.get("/candidates/me").json()["headline"]
                == "Development persistence verification"
            )
            print(
                "PASS: real HTTP registration/login/profile persistence/logout/replay rejection, with PostgreSQL record verification."
            )
    finally:
        if user_id:
            with psycopg.connect(dsn) as db:
                db.execute("DELETE FROM users WHERE id=%s AND email=%s", (user_id, email))
            print("Temporary development QA account removed; no seeded profile remains.")


if __name__ == "__main__":
    main()
