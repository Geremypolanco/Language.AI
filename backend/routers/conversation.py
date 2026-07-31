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

from .. import auth, db, telemetry
from ..curriculum import build_conversation_system_prompt
from ..hf_client import hf_client
from .users import get_user_by_id_or_404

logger = logging.getLogger("lingua.conversation")

router = APIRouter(tags=["conversation"])

_MAX_HISTORY_TURNS = 12


def _log_turn(user_id: str, role: str, content: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO conversation_log (user_id, role, content, created_at) VALUES (?,?,?,?)",
            (user_id, role, content, db.now_iso()),
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

    system_prompt = build_conversation_system_prompt(user.target_lang, user.native_lang, user.level, user.interests)
    history = _recent_history(user_id)

    await websocket.send_json(
        {
            # target_lang/native_lang are stored as ISO codes ("en", "es"), not
            # display names — the level + language-code badge avoids awkwardly
            # interpolating a raw code into a Spanish sentence (e.g. the "en"
            # code colliding with the Spanish word "en").
            "type": "ready",
            "message": f"Conversación lista — nivel {user.level.value} ({user.target_lang.upper()}).",
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
            with telemetry.timed(chat_timing):
                reply_text = await hf_client.conversation_reply(system_prompt, history)
            _log_turn(user_id, "assistant", reply_text)
            history.append({"role": "assistant", "content": reply_text})
            history = history[-_MAX_HISTORY_TURNS:]

            # Text goes out immediately — the transcript doesn't need to wait
            # on audio. Audio is then streamed sentence-by-sentence as each
            # one finishes synthesizing (see hf_client.stream_speech), so the
            # learner starts hearing the reply instead of waiting for the
            # whole thing to render as one clip.
            await websocket.send_json({"type": "reply", "text": reply_text})

            tts_timing: dict = {}
            sentence_count = 0
            with telemetry.timed(tts_timing):
                async for sentence, audio, media_type in hf_client.stream_speech(reply_text, user.target_lang):
                    sentence_count += 1
                    await websocket.send_json(
                        {
                            "type": "reply_audio_chunk",
                            "text": sentence,
                            "audio_base64": base64.b64encode(audio).decode(),
                            "audio_mime": media_type,
                        }
                    )

            telemetry.log_tutor_turn(
                user_id=user_id,
                chat_ms=chat_timing["elapsed_ms"],
                tts_ms=tts_timing["elapsed_ms"],
                chars_in=len(transcript),
                chars_out=len(reply_text),
                sentence_count=sentence_count,
            )
    except WebSocketDisconnect:
        logger.info("Conversation socket closed for user %s", user_id)
