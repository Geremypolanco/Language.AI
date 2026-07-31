"""Tests for the security headers and rate-limiting middleware added to
main.py — see backend/security_headers.py and backend/rate_limit.py."""

from fastapi.testclient import TestClient

from backend.main import app
from backend.rate_limit import _counter
from conftest import dev_login

from tests.test_api import _onboard


def test_security_headers_present_on_every_response():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in res.headers["Content-Security-Policy"]
        assert "Permissions-Policy" in res.headers


def test_rate_limit_does_not_affect_non_ai_routes():
    with TestClient(app) as client:
        for _ in range(15):
            res = client.get("/api/health")
            assert res.status_code == 200


def test_rate_limit_blocks_ai_route_after_limit_then_recovers():
    _counter._hits.clear()  # isolate from any counts other tests left behind
    with TestClient(app) as client:
        user = _onboard(client, email="ratelimit1@example.com")

        # The configured default is 10/minute; the 11th call in the same
        # window for the same signed-in user must be rejected.
        statuses = []
        for _ in range(11):
            res = client.post(
                "/api/content/recommendations",
                json={"target_lang": "Spanish", "level": "A2", "interests": []},
            )
            statuses.append(res.status_code)

        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429
        blocked_res = client.post(
            "/api/content/recommendations",
            json={"target_lang": "Spanish", "level": "A2", "interests": []},
        )
        assert blocked_res.status_code == 429
        assert "Retry-After" in blocked_res.headers
        assert blocked_res.json()["retry_after_seconds"] > 0


def test_rate_limit_is_scoped_per_user_not_global():
    _counter._hits.clear()
    with TestClient(app) as client:
        user_a = _onboard(client, email="ratelimit2a@example.com")
        for _ in range(10):
            res = client.post(
                "/api/content/recommendations",
                json={"target_lang": "Spanish", "level": "A2", "interests": []},
            )
            assert res.status_code == 200
        # user A is now at the limit
        assert client.post(
            "/api/content/recommendations",
            json={"target_lang": "Spanish", "level": "A2", "interests": []},
        ).status_code == 429

        # a different signed-in user is unaffected
        client.post("/auth/logout")
        dev_login(client, "ratelimit2b@example.com")
        user_b_res = client.post(
            "/api/users",
            json={"display_name": "B", "native_lang": "English", "target_lang": "Spanish", "level": "A1"},
        )
        assert user_b_res.status_code == 200
        res = client.post(
            "/api/content/recommendations",
            json={"target_lang": "Spanish", "level": "A2", "interests": []},
        )
        assert res.status_code == 200
