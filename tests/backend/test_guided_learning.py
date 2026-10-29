from uuid import uuid4

from app.services.learning_catalog import TRACKS, catalog_values, matching_tracks
from conftest import Harness
from test_interviews import FakeProvider, mutate, signed_in, worker


def create(identity, topics=None, **extra):
    return mutate(identity, "POST", "/learning/plans", {
        "topics": topics if topics is not None else ["python"],
        "idempotency_key": str(uuid4()), **extra,
    })


def test_catalog_has_valid_lessons_and_does_not_mix_java_and_javascript():
    assert len(catalog_values()) == 12
    assert "java" not in matching_tracks("JavaScript")
    assert "javascript" in matching_tracks("JavaScript")
    for track in TRACKS.values():
        assert len(track["lessons"]) == 2
        for lesson in track["lessons"]:
            assert len(lesson["explanation"]) > 200
            quiz = lesson["quiz"]
            assert 0 <= quiz["answer"] < len(quiz["options"])
            assert quiz["feedback"] and lesson["examples"] and lesson["practice_question"]


def test_new_candidate_can_create_and_finish_plan_without_gap_or_ai(identity):
    signed_in(identity)
    assert identity.request("GET", "/candidates/me/progress").json()["recommendations"] == []
    catalog = identity.request("GET", "/learning/catalog")
    assert catalog.status_code == 200 and catalog.json()["suggested"]
    saved = create(identity, ["python", "sql"])
    assert saved.status_code == 201, saved.text
    plan = saved.json()
    assert plan["context"]["mode"] == "guided"
    assert plan["progress"] == {"completed": 0, "total": 4}
    assert plan["targets"] == []
    item = plan["items"][0]
    assert item["content"]["grounding_status"] == "authored"
    assert "answer" not in item["content"]["quiz"]
    assert "feedback" not in item["content"]["quiz"]
    started = mutate(identity, "POST", f"/learning/plans/{plan['id']}/start", {"expected_revision": 0})
    assert started.status_code == 200
    current = started.json()
    again = mutate(identity, "POST", f"/learning/plans/{plan['id']}/start", {"expected_revision": 0})
    assert again.json()["revision"] == current["revision"]
    assert len(again.json()["actions"]) == 1

    wrong = mutate(identity, "POST", f"/learning/items/{item['id']}/check", {
        "expected_revision": current["revision"], "selected_index": 1,
    })
    assert wrong.status_code == 200, wrong.text
    current = wrong.json()
    result = current["items"][0]["check_result"]
    assert result["correct"] is False and result["feedback"]
    stale = mutate(identity, "POST", f"/learning/items/{item['id']}/check", {
        "expected_revision": 0, "selected_index": 0,
    })
    assert stale.status_code == 409
    correct = mutate(identity, "POST", f"/learning/items/{item['id']}/check", {
        "expected_revision": current["revision"], "selected_index": 0,
    })
    assert correct.status_code == 200
    current = correct.json()
    assert current["items"][0]["check_result"]["correct"] is True
    assert current["items"][0]["check_result"]["attempts"] == 2
    for lesson in current["items"]:
        response = mutate(identity, "POST", f"/learning/items/{lesson['id']}/complete", {
            "expected_revision": current["revision"],
        })
        assert response.status_code == 200
        current = response.json()
    assert current["status"] == "completed" and current["progress"]["completed"] == 4
    reloaded = identity.request("GET", f"/learning/plans/{plan['id']}").json()
    assert reloaded["items"][0]["check_result"]["correct"] is True
    assert reloaded["items"][0]["completed_at"]
    for table in ("knowledge_gaps", "candidate_memory", "memory_evidence", "learning_targets"):
        assert identity.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0


def test_topic_plans_are_idempotent_and_can_be_explicitly_recreated(identity):
    signed_in(identity)
    key = str(uuid4())
    first = create(identity, idempotency_key=key).json()
    assert create(identity, idempotency_key=key).json()["id"] == first["id"]
    assert create(identity).json()["id"] == first["id"]
    assert create(identity, ["sql"], idempotency_key=key).status_code == 409
    assert create(identity, regenerate=True).json()["id"] != first["id"]
    assert create(identity, ["not-a-real-topic"]).status_code == 422
    assert create(identity, []).status_code == 422
    assert create(identity, ["python", "sql", "react", "git", "docker"]).status_code == 422


def test_target_job_suggestions_and_private_ownership(identity):
    signed_in(identity)
    job = mutate(identity, "POST", "/jobs", {
        "title": "Frontend Developer", "description": "Build accessible HTML and CSS interfaces using React and TypeScript.",
    }).json()
    catalog = identity.request("GET", f"/learning/catalog?job_id={job['id']}").json()
    assert {x["id"] for x in catalog["suggested"]} >= {"react", "typescript", "html-css"}
    plan = create(identity, [], job_id=job["id"]).json()
    assert plan["job_id"] == job["id"] and plan["items"]
    other = Harness(identity.url)
    assert other.register("other@example.com").status_code == 201
    assert other.login("other@example.com").status_code == 200
    assert other.request("GET", f"/learning/catalog?job_id={job['id']}").status_code == 404
    assert create(other, [], job_id=job["id"]).status_code == 404
    item_id = plan["items"][0]["id"]
    assert mutate(other, "POST", f"/learning/items/{item_id}/check", {
        "expected_revision": 0, "selected_index": 0,
    }).status_code == 404
    assert identity.request("POST", f"/learning/items/{item_id}/check", json={
        "expected_revision": 0, "selected_index": 0,
    }).status_code == 403
    assert Harness(identity.url).request("GET", "/learning/catalog").status_code == 401


def test_guided_practice_uses_interview_evaluator_without_fabricating_gaps(identity):
    signed_in(identity)
    saved = create(identity).json()
    item_id = saved["items"][0]["id"]
    attempt = mutate(identity, "POST", f"/learning/items/{item_id}/practice", {
        "idempotency_key": str(uuid4()),
    })
    assert attempt.status_code == 201, attempt.text
    attempt = attempt.json()
    assert attempt["targets"] == []
    interview = identity.request("GET", f"/interviews/{attempt['interview_id']}").json()
    submitted = mutate(identity, "POST", f"/learning/items/{item_id}/practice/{attempt['id']}/submit", {
        "question_id": interview["current"]["id"], "expected_revision": interview["revision"],
        "text": "A mutable default is created once when the function is defined. Use None and create a fresh list inside each call.",
        "idempotency_key": str(uuid4()),
    })
    assert submitted.status_code == 202, submitted.text
    assert worker(identity, FakeProvider())
    evaluated = identity.request("GET", f"/interviews/{attempt['interview_id']}").json()
    assert evaluated["status"] == "completed" and evaluated["practice_feedback"]["feedback"]
    assert identity.sql("SELECT count(*) AS n FROM memory_evidence")[0]["n"] == 0
    assert identity.request("GET", f"/learning/plans/{saved['id']}").json()["attempts"][0]["id"] == attempt["id"]
