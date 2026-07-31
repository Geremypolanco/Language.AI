"""Sentence-chunked TTS streaming — turns a live text token stream into a
stream of synthesized audio chunks, one per completed sentence, instead of
waiting for the entire response to finish generating before synthesizing
anything.

Scope note, read before wiring this into a new call site: this is
deliberately a generic utility over any *plain natural-language* text
stream (e.g. book/course narration), and it is NOT wired into Talk Live's
websocket handler (backend/routers/conversation.py). That handler's model
output is a single structured JSON object per turn (see
curriculum.build_conversation_system_prompt's OUTPUT FORMAT section) —
spoken_response and critique_metrics arrive as one inseparable blob, and
nothing guarantees the model streams spoken_response's characters before
critique_metrics's. Chunking raw streamed JSON tokens on sentence
punctuation would just as easily slice across a JSON string boundary or
feed a stray `",` fragment to text-to-speech as it would a clean sentence —
there is no safe way to stream-synthesize speech from the middle of a JSON
object that's still being generated. Making Talk Live's replies stream this
way for real requires first splitting the model's output contract into two
phases (plain spoken text, then a trailing metrics block) — a deliberate
follow-up, not something to paper over here.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable

# Matches a run of text up to and including a sentence-ending mark. The
# request that motivated this module named periods/exclamation marks/
# semicolons; "?" is added too — a conversational tutor asks questions
# constantly, and without it a buffer full of questions would never flush
# until the whole stream ended, defeating the point of chunked streaming.
_SENTENCE_BOUNDARY = re.compile(r"[^.!?;]*[.!?;]+")

SynthesizeFn = Callable[[str], Awaitable[bytes | None]]


async def stream_audio_payloads(text_stream: AsyncIterator[str], synthesize: SynthesizeFn) -> AsyncIterator[bytes]:
    """Buffers `text_stream`'s chunks and, each time the buffer contains at
    least one complete sentence (ending in '.', '!', '?', or ';'),
    synthesizes and yields audio for that sentence immediately — instead of
    waiting for the whole response before the first byte of audio exists.
    Any leftover text with no closing punctuation is flushed once the
    stream ends.

    `synthesize` is any async callable text -> audio bytes (or None on
    failure, which is skipped rather than raised, matching every TTS
    tier's own resilience contract elsewhere in this app) — typically a
    partial binding of HFClient.text_to_speech with target_lang/
    voice_description/persona_id already fixed for the current turn.

    This is intentionally a "light regex token buffer" (plain punctuation
    matching, no abbreviation/decimal-number awareness) — an abbreviation
    like "Dr." will still split a sentence early. Fine for TTS, where an
    early split just means two short audio clips instead of one."""
    buffer = ""
    async for token in text_stream:
        buffer += token
        while True:
            match = _SENTENCE_BOUNDARY.match(buffer)
            if not match:
                break
            sentence = match.group().strip()
            buffer = buffer[match.end() :]
            if not sentence:
                continue
            audio = await synthesize(sentence)
            if audio:
                yield audio

    trailing = buffer.strip()
    if trailing:
        audio = await synthesize(trailing)
        if audio:
            yield audio
