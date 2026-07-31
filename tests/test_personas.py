from fastapi.testclient import TestClient

from backend import academy, personas
from backend.curriculum import build_conversation_system_prompt
from backend.main import app
from backend.models import CEFRLevel
from test_api import _onboard


def test_core_teachers_are_five_and_distinct():
    teachers = personas.all_core_teachers()
    assert len(teachers) == 5
    assert len({p.id for p in teachers}) == 5
    assert len({p.name for p in teachers}) == 5
    for p in teachers:
        assert p.voice_description
        assert p.portrait_prompt
        assert p.system_voice
        assert p.philosophy


def test_get_core_teacher_lookup():
    elena = personas.get_core_teacher("core-elena")
    assert elena is not None
    assert elena.name == "Elena Vidal"
    assert personas.get_core_teacher("not-a-real-id") is None


def test_build_field_faculty_covers_every_field_uniquely_and_stably():
    fields = academy.all_fields()
    assigned = [personas.build_field_faculty(f) for f in fields]
    assert len({p.name for p in assigned}) == len(fields)
    assert len({p.id for p in assigned}) == len(fields)
    # Stable across repeated calls — same field always gets the same professor.
    again = personas.build_field_faculty(fields[0])
    assert again.name == assigned[0].name
    assert again.voice_description == assigned[0].voice_description


def test_get_persona_resolves_core_and_faculty_ids():
    field = academy.all_fields()[0]
    faculty = personas.get_persona(f"faculty:{field.id}")
    assert faculty is not None
    assert faculty.field_id == field.id

    assert personas.get_persona("core-marcus") is not None
    assert personas.get_persona("faculty:not-a-real-field") is None
    assert personas.get_persona("garbage-id") is None


def test_to_persona_info_has_portrait_url():
    persona = personas.get_core_teacher("core-sofia")
    info = personas.to_persona_info(persona)
    assert info.portrait_url == "/api/personas/core-sofia/portrait"
    assert info.name == persona.name


def test_conversation_prompt_carries_persona_identity_and_correction_loop():
    persona = personas.get_core_teacher("core-elena")
    prompt = build_conversation_system_prompt("Spanish", "English", CEFRLevel.B1, [], persona=persona)
    assert "Elena Vidal" in prompt
    assert "grammatical error" in prompt.lower() or "grammar" in prompt.lower()
    assert "pronunciation" in prompt.lower()
    assert "comprehension" in prompt.lower()

    generic = build_conversation_system_prompt("Spanish", "English", CEFRLevel.B1, [], persona=None)
    assert "warm" in generic.lower()


def test_list_personas_endpoint_returns_five():
    with TestClient(app) as client:
        user = _onboard(client, email="persona1@example.com")
        res = client.get("/api/personas")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 5
        assert all(item["portrait_url"].startswith("/api/personas/") for item in items)


def test_portrait_endpoint_404s_for_unknown_persona_and_503s_in_demo_mode():
    with TestClient(app) as client:
        _onboard(client, email="persona2@example.com")
        assert client.get("/api/personas/not-a-real-persona/portrait").status_code == 404
        # No HF_TOKEN in the test environment, so a real persona still 503s
        # (image generation unavailable) rather than ever fabricating a fake image.
        assert client.get("/api/personas/core-elena/portrait").status_code == 503


def test_update_user_persona_choice():
    with TestClient(app) as client:
        user = _onboard(client, email="persona3@example.com")
        res = client.patch(f"/api/users/{user['id']}", json={"tutor_persona_id": "core-theo"})
        assert res.status_code == 200
        assert res.json()["tutor_persona_id"] == "core-theo"

        bad = client.patch(f"/api/users/{user['id']}", json={"tutor_persona_id": "not-real"})
        assert bad.status_code == 404


def test_academy_field_faculty_endpoint():
    with TestClient(app) as client:
        _onboard(client, email="persona4@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        res = client.get(f"/api/academy/fields/{field_id}/faculty")
        assert res.status_code == 200
        data = res.json()
        assert data["name"]
        assert data["portrait_url"] == f"/api/personas/faculty:{field_id}/portrait"

        assert client.get("/api/academy/fields/not-a-real-field/faculty").status_code == 404


def test_course_content_includes_faculty_byline_even_in_demo_mode():
    with TestClient(app) as client:
        user = _onboard(client, email="persona5@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        courses = client.get(f"/api/academy/{user['id']}/curriculum").json()["courses"]
        course = client.get(f"/api/academy/{user['id']}/courses/{courses[0]['id']}").json()
        assert course["faculty"] is not None
        assert course["faculty"]["id"] == f"faculty:{field_id}"
