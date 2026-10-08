"""Security tests for the /auth/dev-login bypass (critical production hole).

Policy under test (see backend/config.py):
- Dev-login is OFF by default — only an explicit LINGUA_ALLOW_DEV_LOGIN=1
  turns it on.
- If the flag is on in a production-looking environment, the server must
  REFUSE TO START (Settings.assert_security_policy, called from the
  FastAPI lifespan in backend/main.py).
- With dev-login off and no Google OAuth configured, /auth/dev-login must
  answer 403 and must NOT create a session.

The rest of the suite (tests/conftest.py) enables LINGUA_ALLOW_DEV_LOGIN=1
explicitly for tests — these tests verify the production path stays locked.
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import app
from backend.routers import auth as auth_router


def _fresh_settings(monkeypatch) -> Settings:
    """Build a Settings from the current (monkeypatched) environment, as if
    the process had just booted."""
    return Settings()


def test_dev_login_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LINGUA_ALLOW_DEV_LOGIN", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    s = _fresh_settings(monkeypatch)
    assert s.google_configured is False
    assert s.dev_login_enabled is False, (
        "dev-login must be OFF by default — 'no Google credentials' must "
        "never auto-enable the auth bypass"
    )


def test_dev_login_enabled_only_via_explicit_flag(monkeypatch):
    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "1")
    assert _fresh_settings(monkeypatch).dev_login_enabled is True

    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "0")
    assert _fresh_settings(monkeypatch).dev_login_enabled is False

    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "yes")
    assert _fresh_settings(monkeypatch).dev_login_enabled is False


def test_production_startup_refuses_dev_login_flag(monkeypatch):
    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "1")
    monkeypatch.setenv("LINGUA_ENV", "production")
    s = _fresh_settings(monkeypatch)
    assert s.is_production is True
    with pytest.raises(RuntimeError, match="Refusing to start"):
        s.assert_security_policy()


def test_fly_machine_counts_as_production(monkeypatch):
    # Fly injects FLY_APP_NAME on every machine — a stray
    # `fly secrets set LINGUA_ALLOW_DEV_LOGIN=1` must crash at boot, not
    # silently open the bypass in production.
    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "1")
    monkeypatch.setenv("FLY_APP_NAME", "language-ai-x90j9w")
    s = _fresh_settings(monkeypatch)
    assert s.is_production is True
    with pytest.raises(RuntimeError, match="Refusing to start"):
        s.assert_security_policy()


def test_dev_login_allowed_in_non_production_with_flag(monkeypatch):
    # Local dev / CI: flag on, no production signals → starts fine.
    monkeypatch.setenv("LINGUA_ALLOW_DEV_LOGIN", "1")
    for var in ("LINGUA_ENV", "ENV", "APP_ENV", "FLY_APP_NAME"):
        monkeypatch.delenv(var, raising=False)
    s = _fresh_settings(monkeypatch)
    assert s.is_production is False
    s.assert_security_policy()  # must not raise


def test_dev_login_endpoint_returns_403_and_no_session_without_oauth(monkeypatch):
    """The production path: no Google creds, flag off → 403, no cookies,
    session status stays unauthenticated."""
    monkeypatch.delenv("LINGUA_ALLOW_DEV_LOGIN", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    locked = _fresh_settings(monkeypatch)
    assert locked.dev_login_enabled is False

    # Swap the settings object the auth router consults (lifespan already
    # ran on the real singleton; this only affects the endpoint under test).
    monkeypatch.setattr(auth_router, "settings", locked)

    with TestClient(app) as client:
        res = client.get(
            "/auth/dev-login",
            params={"email": "attacker@example.com", "name": "Attacker"},
            follow_redirects=False,
        )
        assert res.status_code == 403
        # No session or pending cookie may be issued
        assert "lingua_session" not in client.cookies
        assert "lingua_pending" not in client.cookies

        status = client.get("/api/session").json()
        assert status["authenticated"] is False
        assert status["pending"] is False
        assert status["dev_login_enabled"] is False


def test_google_login_unavailable_without_credentials():
    # No GOOGLE_CLIENT_ID/SECRET in the test env → the OAuth entry point
    # must fail closed instead of redirecting to a broken Google flow.
    with TestClient(app) as client:
        res = client.get("/auth/google/login", follow_redirects=False)
        assert res.status_code == 503


def test_dev_login_still_works_when_explicitly_enabled():
    # Positive control: the suite's own LINGUA_ALLOW_DEV_LOGIN=1 keeps the
    # helper path working for every other test file.
    with TestClient(app) as client:
        res = client.get(
            "/auth/dev-login",
            params={"email": "sec-positive-control@example.com"},
            follow_redirects=False,
        )
        assert res.status_code == 303
