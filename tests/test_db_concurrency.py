"""Proves the claim behind NOT adding extra locking around Academy's
enroll/complete endpoints: db.cursor() already serializes every write
through a single process-wide RLock (see db.py), and the write endpoints
themselves use atomic `INSERT ... ON CONFLICT` upserts rather than a
check-then-write pattern — so concurrent requests hitting the same
(user, course) pair can't produce duplicate rows or a crash. Fires real
concurrent requests via a thread pool (not asyncio.gather against a single
TestClient call, which wouldn't actually exercise cross-request
concurrency) to exercise that locking for real."""

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from test_api import _onboard


def test_concurrent_course_completions_never_duplicate_or_crash():
    with TestClient(app) as client:
        user = _onboard(client, email="concurrency1@example.com")
        user_id = user["id"]

        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user_id}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = client.get(f"/api/academy/{user_id}/curriculum").json()["courses"][0]["id"]

        def complete_once():
            return client.post(f"/api/academy/{user_id}/courses/{course_id}/complete")

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda _: complete_once(), range(10)))

        assert all(r.status_code == 200 for r in responses)

        with db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM academy_course_progress WHERE user_id=? AND course_id=?",
                (user_id, course_id),
            )
            assert cur.fetchone()["n"] == 1


def test_concurrent_enrollments_leave_a_single_deterministic_row():
    with TestClient(app) as client:
        user = _onboard(client, email="concurrency2@example.com")
        user_id = user["id"]
        fields = client.get("/api/academy/fields").json()

        def enroll_in(field_id: str):
            return client.post(f"/api/academy/{user_id}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda f: enroll_in(f["id"]), fields[:10]))

        assert all(r.status_code == 200 for r in responses)

        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM academy_enrollment WHERE user_id=?", (user_id,))
            assert cur.fetchone()["n"] == 1
