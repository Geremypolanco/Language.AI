import os
import sys
from pathlib import Path

import pytest

# Must be set before backend.config is first imported (it reads this once,
# at module load, into a frozen Settings singleton) — keeps the whole test
# suite offline and deterministic even though Pollinations itself needs no
# token and would otherwise happily make a real network call.
os.environ["LINGUA_TESTING"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db as db_module  # noqa: E402
from backend.learning_engine.learning_state import learning_state_provider  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Every test gets its own throwaway SQLite file — no shared state, no
    dependency on ARIA's Supabase/Postgres stack.

    Also resets learning_state_provider's cache: it's a module-level
    singleton that outlives any single test (see learning_state.py), so
    without this a later test reusing a common id like "u1" could read an
    earlier test's stale state instead of computing its own against this
    fresh database."""
    db_module.reset_for_tests(str(tmp_path / "test.db"))
    learning_state_provider.reset()
    yield


def dev_login(client, email: str) -> None:
    """Simulates a completed Google login for a test client (no real Google
    credentials configured in the test environment, so `dev_login_enabled`
    is true — see config.Settings.dev_login_enabled). Sets either a pending
    cookie (first time) or a session cookie (returning user) on the client's
    cookie jar, exactly like a real Google OAuth callback would."""
    res = client.get("/auth/dev-login", params={"email": email}, follow_redirects=False)
    assert res.status_code == 303
