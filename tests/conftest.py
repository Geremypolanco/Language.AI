import os
import sys
import tempfile
from pathlib import Path

import pytest

# Must be set before backend.config is first imported (it reads this once,
# at module load, into a frozen Settings singleton) — keeps the whole test
# suite offline and deterministic even though Pollinations itself needs no
# token and would otherwise happily make a real network call.
os.environ["LINGUA_TESTING"] = "1"

# Dev-login bypass is OFF by default (see backend/config.py) and must stay
# off in production. The test suite needs it to simulate logins, so it is
# explicitly enabled HERE for tests only — exactly how local dev enables it.
os.environ["LINGUA_ALLOW_DEV_LOGIN"] = "1"

# Dead-letter triage writes go to a throwaway dir during tests — the
# llm_contracts singleton reads this env var once at import, which happens
# after this file runs, so no test ever touches the real data/dead_letters/.
os.environ["LINGUA_DEAD_LETTER_DIR"] = tempfile.mkdtemp(prefix="lingua-test-dead-letters-")

# Sandbox/proxy artifact: some runtimes export a malformed NO_PROXY (bracketed
# IPv6 entries such as [fd8b:...::1]) that makes httpx raise InvalidURL at
# import time (backend/hf_client.py builds an httpx.AsyncClient at module
# load). The suite is fully offline by design (LINGUA_TESTING=1), so proxy
# variables are irrelevant here — drop them before anything imports httpx.
for _proxy_var in (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
):
    os.environ.pop(_proxy_var, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db as db_module  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Every test gets its own throwaway SQLite file — no shared state, no
    dependency on ARIA's Supabase/Postgres stack."""
    db_module.reset_for_tests(str(tmp_path / "test.db"))
    yield


def dev_login(client, email: str) -> None:
    """Simulates a completed Google login for a test client. The dev-login
    bypass is explicitly enabled for the test suite via
    LINGUA_ALLOW_DEV_LOGIN=1 in this conftest (production default is OFF).
    Sets either a pending cookie (first time) or a session cookie (returning
    user) on the client's cookie jar, exactly like a real Google OAuth
    callback would."""
    res = client.get("/auth/dev-login", params={"email": email}, follow_redirects=False)
    assert res.status_code == 303
