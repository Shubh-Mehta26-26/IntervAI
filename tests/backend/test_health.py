import asyncio

from app.api import health
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError


def get(path):
    async def request():
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app), base_url="http://test") as client,
        ):
            return await client.get(path)

    return asyncio.run(request())


def test_liveness_does_not_require_database():
    response = get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "intervai-api"}


def test_readiness_requires_database_and_vector(monkeypatch):
    async def connected():
        return True

    monkeypatch.setattr(health, "probe_database", connected)
    response = get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["vector"] == "available"


def test_missing_extension_is_not_ready(monkeypatch):
    async def no_vector():
        return False

    monkeypatch.setattr(health, "probe_database", no_vector)
    response = get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "connected"
    assert response.json()["vector"] == "missing"


def test_database_failure_is_redacted(monkeypatch):
    async def unavailable():
        raise SQLAlchemyError("postgres://private:secret@internal-host")

    monkeypatch.setattr(health, "probe_database", unavailable)
    response = get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert "secret" not in response.text
