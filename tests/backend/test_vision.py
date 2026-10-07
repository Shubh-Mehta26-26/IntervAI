"""Real PostgreSQL/API tests; detector fixtures are explicitly test-only."""

import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.models.interviews import Interview
from app.models.vision import VisionSession
from app.providers.vision import VisionError, validate_frame
from app.schemas.vision import Detection
from app.services import vision
from conftest import Harness, run
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_interviews import create_interview, mutate, signed_in


def image(size=(100, 100), format="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", size, "gray").save(output, format=format)
    return output.getvalue()


class FixtureDetector:
    calls = 0
    fail = False

    def detect(self, data):
        self.calls += 1
        if self.fail:
            raise VisionError("test-only failure")
        return Detection(persons=1, person_confidence=0.8, phone=False)


def prepare(identity, monkeypatch, **options):
    monkeypatch.setattr(get_settings(), "vision_enabled", True)
    signed_in(identity)
    row = create_interview(identity, **options).json()
    identity.sql(
        "UPDATE interviews SET status='waiting_for_answer' WHERE id=%s", (row["id"],)
    )
    detector = FixtureDetector()
    monkeypatch.setattr(vision, "get_vision", lambda: detector)
    monkeypatch.setattr(
        vision,
        "vision_status",
        lambda: {"available": True, "message": "Test-only detector"},
    )
    monkeypatch.setattr("app.api.vision.vision_status", lambda: {"available": True})
    return row, detector


def enable(identity, row):
    response = mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/vision/session",
        {"enabled": True, "expected_revision": 0},
    )
    assert response.status_code == 200, response.text
    return response.json()


def frame(identity, row, state, sequence=0, data=None, captured=None):
    return identity.request(
        "POST",
        f"/interviews/{row['id']}/vision/frame",
        headers={"X-CSRF-Token": identity.csrf},
        files={"image": ("ignored-user-path.jpg", data or image(), "image/jpeg")},
        data={
            "revision": state["revision"],
            "sequence": sequence,
            "captured_at": (captured or datetime.now(timezone.utc)).isoformat(),
        },
    )


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"bad", "image/jpeg"),
        (image(), "image/png"),
        (image((641, 32)), "image/jpeg"),
        (b"x" * 131073, "image/jpeg"),
        (image(), "image/svg+xml"),
    ],
    ids=["invalid", "mime-mismatch", "dimensions", "oversized", "disallowed-type"],
)
def test_frame_validation(data, mime):
    with pytest.raises(VisionError):
        validate_frame(data, mime)


def test_valid_jpeg_png_and_detector_confidence():
    validate_frame(image(), "image/jpeg")
    validate_frame(image(format="PNG"), "image/png")
    assert Detection(persons=0, phone=False).person_confidence is None
    for value in [float("nan"), 1.2, -0.2]:
        with pytest.raises(ValidationError):
            Detection(persons=1, person_confidence=value, phone=False)


def test_optional_disabled_and_ownership(identity, monkeypatch):
    row, _ = prepare(identity, monkeypatch, vision_enabled=False)
    assert (
        identity.request("GET", f"/interviews/{row['id']}/vision/status").json()[
            "enabled"
        ]
        is False
    )
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{row['id']}/vision/session",
            {"enabled": True, "expected_revision": 0},
        ).status_code
        == 409
    )
    second = Harness(identity.url)
    assert second.register("other-vision@example.com").status_code == 201
    second.login("other-vision@example.com")
    for path in ["vision/status", "integrity-events"]:
        assert (
            second.request("GET", f"/interviews/{row['id']}/{path}").status_code == 404
        )
    assert (
        Harness(identity.url)
        .request("GET", f"/interviews/{row['id']}/vision/status")
        .status_code
        == 401
    )


def test_global_disabled(identity, monkeypatch):
    row, _ = prepare(identity, monkeypatch)
    monkeypatch.setattr(get_settings(), "vision_enabled", False)
    monkeypatch.setattr("app.api.vision.vision_status", lambda: {"available": False})
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{row['id']}/vision/session",
            {"enabled": True, "expected_revision": 0},
        ).status_code
        == 409
    )


def test_frame_replay_stale_throttle_stop_and_no_client_claims(identity, monkeypatch):
    row, detector = prepare(identity, monkeypatch)
    state = enable(identity, row)
    first = frame(identity, row, state)
    assert first.status_code == 200, first.text
    assert frame(identity, row, state).status_code == 200 and detector.calls == 1
    assert frame(identity, row, state, 1).status_code == 429
    assert (
        frame(
            identity,
            row,
            state,
            2,
            captured=datetime.now(timezone.utc) - timedelta(seconds=20),
        ).status_code
        == 409
    )
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{row['id']}/vision/events",
            {"event_type": "PHONE_DETECTED", "confidence": 1},
        ).status_code
        == 404
    )
    stopped = mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/vision/session",
        {"enabled": False, "expected_revision": state["revision"]},
    )
    assert stopped.status_code == 200 and not stopped.json()["enabled"]
    assert frame(identity, row, state, 3).status_code == 409
    assert identity.sql("SELECT count(*) AS n FROM answer_evaluations")[0]["n"] == 0
    assert identity.sql("SELECT count(*) AS n FROM memory_evidence")[0]["n"] == 0
    assert identity.sql("SELECT count(*) AS n FROM knowledge_gaps")[0]["n"] == 0
    assert identity.sql("SELECT count(*) AS n FROM learning_plans")[0]["n"] == 0


def test_failure_and_expired_processing_claim(identity, monkeypatch):
    row, detector = prepare(identity, monkeypatch)
    state = enable(identity, row)
    detector.fail = True
    response = frame(identity, row, state)
    assert response.status_code == 200
    assert (
        response.json()["error_code"] == "vision_unavailable"
        and response.json()["events"] == []
    )
    identity.sql(
        "UPDATE vision_sessions SET processing_sequence=1,processing_until=now()+interval '10 seconds', last_received_at=now()-interval '2 seconds' WHERE interview_id=%s",
        (row["id"],),
    )
    assert frame(identity, row, state, 1).status_code == 429
    identity.sql(
        "UPDATE vision_sessions SET processing_until=now()-interval '1 seconds' WHERE interview_id=%s",
        (row["id"],),
    )
    detector.fail = False
    assert frame(identity, row, state, 2).status_code == 200


@pytest.mark.parametrize(
    "kind,persons,phone,threshold,phone_enabled",
    [
        ("CANDIDATE_PRESENT", 1, False, 2, True),
        ("CANDIDATE_ABSENT", 0, False, 3, True),
        ("MULTIPLE_PERSONS_DETECTED", 2, False, 2, True),
        ("PHONE_DETECTED", 1, True, 2, True),
        ("CANDIDATE_PRESENT", 1, True, 2, False),
    ],
)
def test_debounce_duration_order_recovery(
    identity, monkeypatch, kind, persons, phone, threshold, phone_enabled
):
    row, _ = prepare(identity, monkeypatch, vision_phone_enabled=phone_enabled)
    enable(identity, row)
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with factory() as db:
            interview = await db.get(Interview, UUID(row["id"]))
            session = await db.scalar(
                select(VisionSession).where(VisionSession.interview_id == interview.id)
            )
            detection = Detection(
                persons=persons,
                person_confidence=0.81 if persons else None,
                phone=phone,
                phone_confidence=0.9 if phone else None,
            )
            started = datetime.now(timezone.utc)
            for seconds in [0, 0.3, 1]:
                await vision.aggregate(
                    db,
                    interview,
                    session,
                    detection,
                    started + timedelta(seconds=seconds),
                )
            await db.commit()
            assert not await vision.timeline(db, interview.id)
            for seconds in range(2, 11):
                await vision.aggregate(
                    db,
                    interview,
                    session,
                    detection,
                    started + timedelta(seconds=seconds),
                )
            await db.commit()
            events = await vision.timeline(db, interview.id)
            if not phone_enabled:
                assert all(event["event_type"] != "PHONE_DETECTED" for event in events)
            target = [event for event in events if event["event_type"] == kind]
            assert len(target) == 1
            assert target[0]["duration_ms"] == 10000
            assert target[0]["confidence"] == (
                None
                if kind in {"CANDIDATE_ABSENT", "MULTIPLE_PERSONS_DETECTED"}
                else 0.9
                if phone and kind == "PHONE_DETECTED"
                else 0.81
            )
            await vision.aggregate(
                db,
                interview,
                session,
                Detection(persons=1 if not persons else 0, phone=False),
                started + timedelta(seconds=11),
            )
            await db.commit()
            event = next(
                event
                for event in await vision.timeline(db, interview.id)
                if event["event_type"] == kind
            )
            assert event["ended_at"] is not None and event["duration_ms"] == 10000
            await vision.close_all(db, session)
            await db.commit()
        await engine.dispose()

    run(scenario())
    for table in [
        "answer_evaluations",
        "memory_evidence",
        "knowledge_gaps",
        "learning_plans",
        "adaptive_decisions",
    ]:
        assert identity.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0


def test_global_busy_drops_without_calling_detector(identity, monkeypatch):
    row, detector = prepare(identity, monkeypatch)
    state = enable(identity, row)
    assert vision.INFERENCE_SLOT.acquire(blocking=False)
    try:
        response = frame(identity, row, state)
        assert response.status_code == 200
        assert response.json()["error_code"] == "vision_busy"
        assert detector.calls == 0 and not response.json()["events"]
    finally:
        vision.INFERENCE_SLOT.release()


def test_abandoned_session_without_first_frame_closes(identity, monkeypatch):
    row, _ = prepare(identity, monkeypatch)
    enable(identity, row)
    identity.sql(
        "UPDATE vision_sessions SET updated_at=now()-interval '20 seconds' WHERE interview_id=%s",
        (row["id"],),
    )
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def sweep():
        await vision.sweep_sessions(factory)
        await engine.dispose()

    run(sweep())
    state = identity.request("GET", f"/interviews/{row['id']}/vision/status").json()
    assert not state["enabled"] and state["events"][0]["duration_ms"] == 0


def test_gap_breaks_confirmation_and_worker_closes_session(identity, monkeypatch):
    row, _ = prepare(identity, monkeypatch)
    state = enable(identity, row)
    assert frame(identity, row, state).status_code == 200
    identity.sql(
        "UPDATE vision_sessions SET last_received_at=now()-interval '20 seconds' WHERE interview_id=%s",
        (row["id"],),
    )
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def sweep():
        await vision.sweep_sessions(factory)
        await engine.dispose()

    run(sweep())
    response = identity.request("GET", f"/interviews/{row['id']}/vision/status").json()
    assert not response["enabled"] and response["error_code"] == "sampling_stopped"
    assert response["events"][0]["confidence"] is None
    assert (
        response["events"][0]["metadata"]["provenance"]
        == "server_observed_sampling_gap"
    )


def test_camera_notice_neutral_unverified_debounced(identity, monkeypatch):
    row, _ = prepare(identity, monkeypatch)
    state = enable(identity, row)
    path = f"/interviews/{row['id']}/vision/notice"
    for _ in range(5):
        assert (
            mutate(
                identity,
                "POST",
                path,
                {"revision": state["revision"], "notice": "orientation_changed"},
            ).status_code
            == 200
        )
    events = identity.request(
        "GET", f"/interviews/{row['id']}/integrity-events"
    ).json()["events"]
    assert len(events) == 1 and events[0]["confidence"] is None
    assert events[0]["metadata"]["provenance"] == "client_reported_unverified"
    assert (
        mutate(
            identity,
            "POST",
            path,
            {"revision": state["revision"], "notice": "CHEATING_DETECTED"},
        ).status_code
        == 422
    )


def test_pause_resume_completion_returns_state_and_stops_monitoring(
    identity, monkeypatch
):
    row, _ = prepare(identity, monkeypatch)
    state = enable(identity, row)
    assert frame(identity, row, state).status_code == 200
    paused = mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/pause",
        {"expected_revision": row["revision"]},
    )
    assert paused.status_code == 200, paused.text
    assert frame(identity, row, state, 1).status_code == 409
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def sweep():
        await vision.sweep_sessions(factory)
        await engine.dispose()

    run(sweep())
    assert not identity.request("GET", f"/interviews/{row['id']}/vision/status").json()[
        "enabled"
    ]
    resumed = mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/resume",
        {"expected_revision": paused.json()["revision"]},
    )
    assert resumed.status_code == 200, resumed.text
    completed = mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/complete",
        {"expected_revision": resumed.json()["revision"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
