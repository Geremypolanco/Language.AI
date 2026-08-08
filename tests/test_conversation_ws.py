"""Closes the loop this app was missing: LearningState -> AdaptationEngine
-> Conversation, exercised end-to-end over the real /ws/conversation
WebSocket rather than by calling internal functions directly. Before this,
routers/conversation.py had no WebSocket test at all."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import db
from backend import hf_client as hf_client_module
from backend.learning_engine.student_profile import set_career_goal
from backend.main import app
from conftest import dev_login


def _onboard(client, email: str) -> dict:
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Talk Test", "native_lang": "English", "target_lang": "Spanish", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


def _enroll(user_id: str, field_id: str = "software-engineering") -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at, content_lang) "
            "VALUES (?, ?, 'BACHELOR', ?, 'es')",
            (user_id, field_id, db.now_iso()),
        )


def _record_mistake(user_id: str, field_id: str, question_text: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
            "VALUES (?, ?, 'quiz', 0, ?, 0, ?)",
            (user_id, f"{field_id}:BACHELOR:0", question_text, db.now_iso()),
        )


async def _fake_stream_speech(text, target_lang, voice_description=None, persona_id=None):
    return
    yield  # pragma: no cover - makes this an empty async generator, no audio in these tests


def test_conversation_socket_prompt_includes_career_goal_and_frequent_mistakes(monkeypatch):
    captured: dict = {}

    async def fake_stream_chat(messages, max_tokens=1000, temperature=0.7):
        captured["system_prompt"] = messages[0]["content"]
        yield "Hola, ¿cómo estás?"

    monkeypatch.setattr(hf_client_module.hf_client, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(hf_client_module.hf_client, "stream_speech", _fake_stream_speech)

    with TestClient(app) as client:
        user = _onboard(client, "talk-adapt@example.com")
        user_id = user["id"]
        _enroll(user_id)
        set_career_goal(user_id, "Software Engineer")
        _record_mistake(user_id, "software-engineering", "What does 'git rebase' do?")

        with client.websocket_connect(f"/ws/conversation/{user_id}") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"

            ws.send_json({"type": "text", "data": "Hola"})

            events = []
            for _ in range(10):
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "turn_complete":
                    break

    assert any(e["type"] == "reply_done" for e in events)
    prompt = captured["system_prompt"]
    assert "LEARNER ADAPTATION NOTES" in prompt
    assert "Software Engineer" in prompt
    assert "git rebase" in prompt


def test_conversation_socket_omits_adaptation_block_for_new_learner(monkeypatch):
    captured: dict = {}

    async def fake_stream_chat(messages, max_tokens=1000, temperature=0.7):
        captured["system_prompt"] = messages[0]["content"]
        yield "Hi there!"

    monkeypatch.setattr(hf_client_module.hf_client, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(hf_client_module.hf_client, "stream_speech", _fake_stream_speech)

    with TestClient(app) as client:
        user = _onboard(client, "talk-noadapt@example.com")
        user_id = user["id"]
        # No Academy enrollment, no career goal, no recorded mistakes.

        with client.websocket_connect(f"/ws/conversation/{user_id}") as ws:
            ws.receive_json()  # ready
            ws.send_json({"type": "text", "data": "Hello"})
            for _ in range(10):
                event = ws.receive_json()
                if event["type"] == "turn_complete":
                    break

    assert "LEARNER ADAPTATION NOTES" not in captured["system_prompt"]
