from backend import academy, personas


class _EmptyStore:
    def load_field_biography(self, field_id):
        return None


class _BioStore:
    def __init__(self, bio):
        self._bio = bio

    def load_field_biography(self, field_id):
        return self._bio


def test_build_field_faculty_falls_back_to_category_archetype_without_a_biography():
    field = academy.get_field("business-administration")
    persona = personas.build_field_faculty(field, store=_EmptyStore())

    category_info = personas._CATEGORY_ARCHETYPES["Negocios"]
    assert persona.correction_focus == category_info["correction_focus"]
    assert persona.motivational_style == category_info["motivation"]
    assert field.name in persona.system_voice
    assert persona.field_id == "business-administration"


def test_build_field_faculty_uses_a_persisted_biography_when_present():
    field = academy.get_field("business-administration")
    bio = {
        "career_highlights": ["18 años como CEO de una empresa de logística global", "Fundó dos startups"],
        "philosophy": "La precisión ejecutiva importa más que el volumen de palabras.",
        "correction_focus": "afirmaciones de negocio sin sustento",
        "system_voice": "You are a pragmatic, battle-tested former CEO who corrects vague business reasoning immediately.",
        "motivational_style": "Enmarca cada corrección como algo que fortalece tu credibilidad ante una junta directiva real.",
    }
    persona = personas.build_field_faculty(field, store=_BioStore(bio))

    assert persona.philosophy == bio["philosophy"]
    assert persona.correction_focus == bio["correction_focus"]
    assert persona.motivational_style == bio["motivational_style"]
    assert bio["system_voice"] in persona.system_voice
    assert "18 años como CEO" in persona.system_voice
    # Identity (name/portrait/voice tone) stays from the deterministic pools
    # regardless of whether a biography exists — only the written persona changes.
    fallback_persona = personas.build_field_faculty(field, store=_EmptyStore())
    assert persona.name == fallback_persona.name
    assert persona.portrait_prompt == fallback_persona.portrait_prompt
    assert persona.voice_description == fallback_persona.voice_description


def test_build_field_faculty_ignores_a_biography_missing_system_voice():
    field = academy.get_field("computer-science")
    bio = {"career_highlights": ["x"], "philosophy": "y"}  # incomplete — treated as absent
    persona = personas.build_field_faculty(field, store=_BioStore(bio))
    fallback_persona = personas.build_field_faculty(field, store=_EmptyStore())
    assert persona.system_voice == fallback_persona.system_voice
    assert persona.philosophy == fallback_persona.philosophy
