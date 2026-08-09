"""API-level proof that CurriculumAdaptation's weight() layer never touches
the CEFR-ordered skill path itself — only routers/lessons.py's new
priority_weight field changes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import db
from backend.learning_engine.learning_state import learning_state_provider
from backend.main import app
from conftest import dev_login


def _onboard(client, email: str) -> dict:
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Path Test", "native_lang": "English", "target_lang": "Spanish", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


def _insert_due_vocab(user_id: str, vocab_key: str, unit_id: str, target_text: str = "hola") -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text, unit_id) "
            "VALUES (?, ?, ?, ?, 'hello', ?)",
            (user_id, vocab_key, db.now_iso(), target_text, unit_id),
        )


def test_path_priority_weight_reflects_due_review_without_reordering_path():
    with TestClient(app) as client:
        user = _onboard(client, "path-weight@example.com")
        user_id = user["id"]

        baseline = client.get(f"/api/lessons/{user_id}/path").json()
        assert all(u["priority_weight"] == 0.0 for u in baseline)
        baseline_order = [(u["id"], u["order"], u["level"], u["state"]) for u in baseline]

        target_unit = baseline[3]["id"]  # some unit past the first, so it's not a trivial index-0 case
        _insert_due_vocab(user_id, f"{target_unit}.palabra", target_unit)
        # LearningStateProvider's TTL cache (see learning_state.py) would
        # otherwise still serve the pre-mutation snapshot for up to 5
        # minutes — invalidate() is the deliberate escape hatch for a
        # caller that just changed something LearningState reflects and
        # wants the next read to see it now, same as a real endpoint that
        # writes to vocab_progress should call after mutating it.
        learning_state_provider.invalidate(user_id)

        after = client.get(f"/api/lessons/{user_id}/path").json()
        after_order = [(u["id"], u["order"], u["level"], u["state"]) for u in after]

        # The path itself — ids, CEFR order, availability — is byte-for-byte
        # identical; only priority_weight changed.
        assert after_order == baseline_order

        weights = {u["id"]: u["priority_weight"] for u in after}
        assert weights[target_unit] == 1.0
        assert all(w == 0.0 for uid, w in weights.items() if uid != target_unit)
