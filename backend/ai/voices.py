"""Structured teacher voice profiles — turns each TeacherPersona's free-form
`voice_description` (backend/personas.py) into explicit fields the Speech
Router and any future UI can reason about directly, instead of leaving
"voz, entonación, personalidad, ritmo, pronunciación, estilo" implicit
inside one prose string.

The prose string is still what actually steers synthesis (Parler-TTS reads
it as a natural-language description prompt, ElevenLabs ignores it in favor
of a named voice_id — see hf_client.text_to_speech) — VoiceProfile is a
parsed, queryable *view* over that same source of truth, not a second,
competing one. Every field here is derived directly from the persona's own
already-authored voice_description/sampling_temperature; nothing is
invented per-voice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..personas import TeacherPersona

_RATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "slow": ("slow", "deliberate", "unhurried", "measured", "formal pace"),
    "fast": ("fast", "quick", "brisk", "rapid"),
}
_PITCH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "low": ("low", "deep", "resonant", "rich"),
    "high": ("bright", "high-pitched"),
}
_STYLE_WORDS: tuple[str, ...] = (
    "warm", "energetic", "calm", "authoritative", "friendly", "crisp", "bright",
    "relaxed", "formal", "dry", "expressive", "measured", "animated", "casual",
)


@dataclass(frozen=True)
class VoiceProfile:
    """One teacher's complete voice identity — the concrete answer to "voz,
    entonación, personalidad, ritmo, pronunciación, estilo" per professor."""

    persona_id: str
    name: str
    description: str                 # full natural-language prompt sent to TTS (pronunciation + intonation cues live here)
    rate: str                        # "slow" | "moderate" | "fast" — derived, informational
    pitch: str                       # "low" | "moderate" | "high" — derived, informational
    style_tags: tuple[str, ...]      # e.g. ("warm", "energetic")
    sampling_temperature: float      # this persona's chat sampling temperature — the textual-personality lever (see personas.TeacherPersona)
    provider_priority: tuple[str, ...] = ("elevenlabs", "parler-tts", "piper", "mms-tts")


def _match(text: str, keywords: dict[str, tuple[str, ...]], default: str) -> str:
    lowered = text.lower()
    for label, words in keywords.items():
        if any(word in lowered for word in words):
            return label
    return default


def _style_tags(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(word for word in _STYLE_WORDS if word in lowered)


def voice_profile_for_persona(persona: "TeacherPersona") -> VoiceProfile:
    description = persona.voice_description
    return VoiceProfile(
        persona_id=persona.id,
        name=persona.name,
        description=description,
        rate=_match(description, _RATE_KEYWORDS, default="moderate"),
        pitch=_match(description, _PITCH_KEYWORDS, default="moderate"),
        style_tags=_style_tags(description),
        sampling_temperature=persona.sampling_temperature,
    )
