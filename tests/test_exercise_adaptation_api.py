"""API-level proof that ExerciseAdaptation's priority signal never touches
the exercise list itself (content, order, count) — only Exercise.priority
changes, and only for the exercise whose vocab_key is actually due."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import db
from backend.language_library.storage import FileSystemAcademyStore, language_pair_key
from backend.learning_engine.learning_state import learning_state_provider
from backend.main import app
from conftest import dev_login


def _onboard(client, email: str) -> dict:
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Exercise Test", "native_lang": "English", "target_lang": "Spanish", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


def _seed_language_unit(store, target_lang, native_lang, unit_id, level):
    pair_key = language_pair_key(target_lang, native_lang)
    store.save_course_asset(
        pair_key, level, "v1", unit_id, "content",
        [
            {
                "id": f"{unit_id}-0", "type": "translate_to_target", "prompt": "Traduce", "target_text": "hola",
                "native_text": "hello", "options": [], "correct_answer": "hola", "image_prompt": "",
                "audio_text": "hola", "vocab_key": "greetings.hello",
            },
            {
                "id": f"{unit_id}-1", "type": "translate_to_target", "prompt": "Traduce", "target_text": "adiós",
                "native_text": "bye", "options": [], "correct_answer": "adiós", "image_prompt": "",
                "audio_text": "adiós", "vocab_key": "greetings.bye",
            },
        ],
    )
    store.set_latest_version(pair_key, level, "v1")


def _insert_due_vocab(user_id: str, vocab_key: str, unit_id: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text, unit_id) "
            "VALUES (?, ?, ?, 'hola', 'hello', ?)",
            (user_id, vocab_key, db.now_iso(), unit_id),
        )


def test_exercise_priority_reflects_due_review_without_changing_content_or_order(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    from backend.routers import lessons as lessons_router

    monkeypatch.setattr(lessons_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, "exercise-priority@example.com")
        user_id = user["id"]

        path = client.get(f"/api/lessons/{user_id}/path").json()
        unit_id = next(u["id"] for u in path if u["level"] == "A1")
        _seed_language_unit(store, user["target_lang"], user["native_lang"], unit_id, "A1")

        baseline = client.get(f"/api/lessons/{user_id}/unit/{unit_id}").json()
        assert len(baseline) == 2
        assert all(ex["priority"] == 0.0 for ex in baseline)
        baseline_content = [(ex["id"], ex["target_text"], ex["correct_answer"], ex["vocab_key"]) for ex in baseline]

        _insert_due_vocab(user_id, "greetings.bye", unit_id)
        # Same TTL-cache escape hatch as CurriculumAdaptation's API test —
        # see test_curriculum_adaptation_api.py.
        learning_state_provider.invalidate(user_id)

        after = client.get(f"/api/lessons/{user_id}/unit/{unit_id}").json()
        after_content = [(ex["id"], ex["target_text"], ex["correct_answer"], ex["vocab_key"]) for ex in after]

        # The exercises themselves — ids, content, order, count — are
        # byte-for-byte identical; only priority changed.
        assert after_content == baseline_content

        priorities = {ex["vocab_key"]: ex["priority"] for ex in after}
        assert priorities["greetings.bye"] == 1.0
        assert priorities["greetings.hello"] == 0.0
