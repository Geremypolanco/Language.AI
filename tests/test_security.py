"""Tests for the security headers middleware added to main.py — see
backend/security_headers.py."""

from fastapi.testclient import TestClient

from backend.main import app


def test_security_headers_present_on_every_response():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in res.headers["Content-Security-Policy"]
        assert "Permissions-Policy" in res.headers
