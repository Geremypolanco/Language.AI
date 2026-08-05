"""Live conversation practice — the "video call" style speaking mode.

A WebSocket carries either recorded audio (base64) or typed text from the
learner; the server transcribes (if audio), generates a level-appropriate
tutor reply via the chat model, then synthesizes and streams its speech
back sentence-by-sentence (hf_client.stream_speech) so the frontend can
start playing the first clause while the rest is still being synthesized,
instead of waiting on one TTS call sized to the whole reply — the practical,
buildable version of "talk normally like in a video call" without needing
either full video synthesis or a live token-streaming chat model."""

from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import auth, db, personas, srs, telemetry
from ..curriculum import build_conversation_system_prompt
from ..hf_client import hf_client
from ..mentor_engine import adaptive_mentor, conversation_memory_adapter
from .users import get_user_by_id_or_404

_DEFAULT_PERSONA_ID = "core-marcus"  # warm, conversational — the closest match to the old generic tutor voice

logger = logging.getLogger("lingua.conversation")

router = APIRouter(tags=["conversation"])

_MAX_HISTORY_TURNS = 12


def _log_turn(user_id: str, role: str, content: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO conversation_log (user_id, role, content, created_at) VALUES (?,?,?,?)",
            (user_id, role, content, db.now_iso()),
        )


def _update_user_memory(user_id: str, new_memory: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO user_memories (user_id, content, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
            (user_id, new_memory, db.now_iso())
        )

def _recent_history(user_id: str) -> list[dict[str, str]]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT role, content FROM conversation_log WHERE user_id=? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, _MAX_HISTORY_TURNS),
        )
        rows = cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


@router.websocket("/ws/conversation/{user_id}")
async def conversation_socket(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()

    session = auth.verify_session(websocket.cookies.get(auth.SESSION_COOKIE))
    if not session or session["user_id"] != user_id:
        await websocket.send_json({"type": "error", "message": "Inicia sesión con Google primero"})
        await websocket.close(code=4401)
        return

    try:
        user = get_user_by_id_or_404(user_id)
    except Exception:
        await websocket.send_json({"type": "error", "message": "Usuario desconocido"})
        await websocket.close()
        return

    mission = websocket.query_params.get("mission")
    requested_persona_id = websocket.query_params.get("persona") or user.tutor_persona_id or _DEFAULT_PERSONA_ID
    teacher = personas.get_core_teacher(requested_persona_id) or personas.get_core_teacher(_DEFAULT_PERSONA_ID)
    debate = websocket.query_params.get("debate") == "true"
    memory = conversation_memory_adapter.get_memory(user_id)
    system_prompt = build_conversation_system_prompt(user.target_lang, user.native_lang, user.level, user.interests, memory)

    # Dual-core persona voice: the Instructor Core (system_voice) sets this
    # teacher's specific correction philosophy; the Motivator Core
    # (motivational_style) sets how a correction gets framed so it lands as
    # progress rather than pure criticism — both run in the same reply, one
    # coherent voice, not two separate turns (see backend/personas.py).
    system_prompt = f"{teacher.system_voice}\n\n{teacher.motivational_style}\n\n{system_prompt}"

    if debate:
        system_prompt += "\n\n### DEBATE MODE ACTIVE: You are two distinct personas: 'Optimist' and 'Skeptic'. When replying, you must provide a short dialogue between them, and then ask the user for their opinion as the moderator."
    
    if mission:
        system_prompt += f"\n\n### ACTIVE MISSION:\n{mission}\nYou must act as the persona required by this mission and evaluate if the learner achieves the goal."

    # Previously a separate chat() call analyzed each message for frustration
    # before generating the real reply. That call competed with the reply
    # itself for the same small, easily-exhausted free chat quota (see
    # backend/config.py's Pollinations note) — on a multi-turn conversation
    # it would routinely be the one to get rate-limited, and since it ran
    # inside the same try/except as the reply, its failure aborted a reply
    # that would otherwise have succeeded, surfacing as "Lo siento, no puedo
    # responder" even though the tutor was available. Folding this into a
    # standing instruction costs zero extra calls — the model judges tone
    # itself, in the one call it was already making.
    system_prompt += (
        "\n\n### ADAPTIVE TONE: If the learner's latest message reads as frustrated, confused, or "
        "like they're struggling, respond with extra patience, simpler words, and more encouragement."
    )

    # ADAPTIVE MENTOR: unlike the per-message ADAPTIVE TONE rule above,
    # this reacts to the student's broader trend across sessions (recent
    # lesson scores) rather than the current message alone — see
    # mentor_engine/adaptive_mentor.py. Empty string (nothing appended)
    # when there's no real "apoyo"/"reto" signal either way.
    mentor_mode = adaptive_mentor.get_mentor_mode(user_id)
    mode_instruction = adaptive_mentor.mode_instruction_text(mentor_mode)
    if mode_instruction:
        system_prompt += f"\n\n{mode_instruction}"

    # PREDICTIVE SRS: surface real due-for-review vocab (or, failing that, past
    # mistakes) from vocab_progress instead of a hardcoded placeholder list.
    # vocab_key is stored as "{unit_id}.{word}" (or "item-{i}" with no dot),
    # so rsplit on "." and fall back to the whole key when there's no prefix.
    srs_keys = srs.due_review_keys(user_id, limit=5) or srs.recent_mistakes(user_id, limit=5)
    if srs_keys:
        srs_words = [key.rsplit(".", 1)[-1] for key in srs_keys]
        system_prompt += f"\n\n### PREDICTIVE SRS: Try to naturally use or elicit the following words from the user: {', '.join(srs_words)}."
    history = _recent_history(user_id)

    await websocket.send_json(
        {
            # target_lang/native_lang are stored as ISO codes ("en", "es"), not
            # display names — the level + language-code badge avoids awkwardly
            # interpolating a raw code into a Spanish sentence (e.g. the "en"
            # code colliding with the Spanish word "en").
            "type": "ready",
            "message": f"Conversación lista — nivel {user.level.value} ({user.target_lang.upper()}).",
            "persona": personas.to_persona_info(teacher).model_dump(),
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Mensaje inválido"})
                continue

            msg_type = msg.get("type")
            if msg_type == "audio":
                audio_bytes = base64.b64decode(msg.get("data", ""))
                content_type = msg.get("content_type", "audio/webm")
                transcript = await hf_client.speech_to_text(audio_bytes, content_type)
                if not transcript:
                    await websocket.send_json(
                        {"type": "error", "message": "No se pudo transcribir el audio — intenta de nuevo o escribe en su lugar."}
                    )
                    # Hands-free mode (see Talk.tsx) waits for this to know
                    # it's safe to start listening again — without it, a
                    # failed transcription would silently break the
                    # continuous listen/reply loop until the learner
                    # manually restarted it.
                    await websocket.send_json({"type": "turn_complete"})
                    continue
            elif msg_type == "text":
                transcript = str(msg.get("data", "")).strip()
                if not transcript:
                    continue
            else:
                await websocket.send_json({"type": "error", "message": f"Tipo de mensaje desconocido: {msg_type}"})
                continue

            await websocket.send_json({"type": "transcript", "text": transcript})
            _log_turn(user_id, "user", transcript)
            history.append({"role": "user", "content": transcript})
            history = history[-_MAX_HISTORY_TURNS:]

            chat_timing: dict = {}
            reply_text = ""

            # Start streaming the reply text to the UI
            await websocket.send_json({"type": "reply_start"})

            try:
                with telemetry.timed(chat_timing):
                    messages = [{"role": "system", "content": system_prompt}, *history]
                    async for chunk in hf_client.stream_chat(messages, temperature=teacher.sampling_temperature):
                        reply_text += chunk
                        await websocket.send_json({"type": "reply_chunk", "text": chunk})
            except Exception:
                # Every AI chat provider failed — the client already got
                # reply_start, so it must still get reply_done or the reply
                # bubble is stuck empty forever.
                logger.exception("Chat reply generation failed for user %s", user_id)
                reply_text = "Lo siento, no puedo responder en este momento — inténtalo de nuevo en unos segundos."
                await websocket.send_json({"type": "error", "message": "El tutor no está disponible en este momento."})
                await websocket.send_json({"type": "reply_done", "text": reply_text})
                await websocket.send_json({"type": "turn_complete"})
                continue

            await websocket.send_json({"type": "reply_done", "text": reply_text})

            _log_turn(user_id, "assistant", reply_text)
            history.append({"role": "assistant", "content": reply_text})
            history = history[-_MAX_HISTORY_TURNS:]

            # Stream audio in parallel (or after text starts)
            tts_timing: dict = {}
            sentence_count = 0
            try:
                with telemetry.timed(tts_timing):
                    async for sentence, audio, media_type in hf_client.stream_speech(
                        reply_text, user.target_lang, teacher.voice_description, teacher.id
                    ):
                        sentence_count += 1
                        await websocket.send_json(
                            {
                                "type": "reply_audio_chunk",
                                "text": sentence,
                                "audio_base64": base64.b64encode(audio).decode(),
                                "audio_mime": media_type,
                            }
                        )
            except Exception:
                # Text reply already landed — a TTS failure shouldn't cost
                # the user the (already-delivered) text turn.
                logger.exception("Speech synthesis failed for user %s", user_id)
                tts_timing.setdefault("elapsed_ms", 0)

            telemetry.log_tutor_turn(
                user_id=user_id,
                chat_ms=chat_timing["elapsed_ms"],
                tts_ms=tts_timing["elapsed_ms"],
                chars_in=len(transcript),
                chars_out=len(reply_text),
                sentence_count=sentence_count,
            )
            # Tells the client (see Talk.tsx's hands-free mode) that no more
            # audio chunks are coming for this turn — whether TTS succeeded
            # or failed above — so it's safe to start listening again for
            # the next thing the learner says, the way a real voice
            # assistant resumes listening after it finishes speaking.
            await websocket.send_json({"type": "turn_complete"})
            # Background task to update memory every few turns
            if len(history) % 4 == 0:
                import asyncio
                asyncio.create_task(_refresh_memory(user_id, history, memory))
    except WebSocketDisconnect:
        logger.info("Conversation socket closed for user %s", user_id)

async def _refresh_memory(user_id: str, history: list[dict], old_memory: str):
    try:
        history_str = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        prompt = f"""Based on the following conversation history and old memory, create a concise, 
updated long-term memory of this learner (their progress, mistakes, interests, and personality). 
Old Memory: {old_memory}
History: {history_str}
New Memory (max 200 words):"""
        new_memory = await hf_client.chat([{"role": "user", "content": prompt}], max_tokens=300)
        _update_user_memory(user_id, new_memory)
    except Exception:
        pass
