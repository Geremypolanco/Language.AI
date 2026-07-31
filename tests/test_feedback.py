"""Tests for POST /api/feedback — thumbs up/down + report on AI content."""

from fastapi.testclient import TestClient

from backend.main import app

from tests.test_api import _onboard


def test_feedback_requires_signin():
    with TestClient(app) as client:
        res = client.post(
            "/api/feedback",
            json={"content_type": "course_module", "content_id": "abc", "rating": "up"},
        )
        assert res.status_code == 401


def test_feedback_accepts_thumbs_up_and_down():
    with TestClient(app) as client:
        _onboard(client, email="feedback1@example.com")
        for rating in ("up", "down"):
            res = client.post(
                "/api/feedback",
                json={"content_type": "book", "content_id": "some-book-id", "rating": rating},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "recorded"


def test_feedback_report_with_note():
    with TestClient(app) as client:
        _onboard(client, email="feedback2@example.com")
        res = client.post(
            "/api/feedback",
            json={
                "content_type": "tutor_reply",
                "content_id": "conv-42",
                "rating": "report",
                "note": "Esto no tiene sentido en este contexto.",
            },
        )
        assert res.status_code == 200


def test_feedback_rejects_invalid_rating():
    with TestClient(app) as client:
        _onboard(client, email="feedback3@example.com")
        res = client.post(
            "/api/feedback",
            json={"content_type": "book", "content_id": "x", "rating": "sideways"},
        )
        assert res.status_code == 422
