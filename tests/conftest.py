import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db as db_module  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.oer import vectorstore as oer_vectorstore  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_from_real_hf_token():
    """The test suite's "fully offline, no real HF calls" guarantee must
    hold no matter what's in the environment it runs in — found the hard
    way: a real HF_TOKEN sitting in a local .env (e.g. for manual testing
    against real HF endpoints) leaks into settings.hf_token here too, since
    config.py reads it once at import time. Without this fixture, tests
    that expect the demo-mode fallback instead attempt real HTTP requests,
    which then fail in whatever way the current network happens to allow —
    not the deterministic, offline behavior this suite is supposed to
    guarantee. settings is a frozen dataclass (see backend/config.py), so
    object.__setattr__ is the same escape hatch db.reset_for_tests uses."""
    original = settings.hf_token
    object.__setattr__(settings, "hf_token", "")
    yield
    object.__setattr__(settings, "hf_token", original)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Every test gets its own throwaway SQLite file — no shared state, no
    dependency on ARIA's Supabase/Postgres stack."""
    db_module.reset_for_tests(str(tmp_path / "test.db"))
    yield


@pytest.fixture(autouse=True)
def isolated_oer_store(tmp_path):
    """Every test gets its own throwaway Chroma directory — the OER vector
    store never touches the real persisted data/oer_chroma/."""
    oer_vectorstore.reset_for_tests(str(tmp_path / "oer_chroma"))
    yield


def dev_login(client, email: str) -> None:
    """Simulates a completed Google login for a test client (no real Google
    credentials configured in the test environment, so `dev_login_enabled`
    is true — see config.Settings.dev_login_enabled). Sets either a pending
    cookie (first time) or a session cookie (returning user) on the client's
    cookie jar, exactly like a real Google OAuth callback would."""
    res = client.get("/auth/dev-login", params={"email": email}, follow_redirects=False)
    assert res.status_code == 303
