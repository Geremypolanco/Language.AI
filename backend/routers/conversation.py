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


def _get_user_memory(user_id: str) -> str:
    with db.cursor() as cur:
        cur.execute("SELECT content FROM user_memories WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row["content"] if row else ""

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
    memory = _get_user_memory(user_id)
    system_prompt = build_conversation_system_prompt(user.target_lang, user.native_lang, user.level, user.interests, memory)
    
    if mission:
        system_prompt += f"\n\n### ACTIVE MISSION:\n{mission}\nYou must act as the persona required by this mission and evaluate if the learner achieves the goal."
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
            reply_text = ""
            
            # Start streaming the reply text to the UI
            await websocket.send_json({"type": "reply_start"})
            
            with telemetry.timed(chat_timing):
                # Elite: Emotional Intelligence - Detect frustration or difficulty
                sentiment_prompt = f"Analyze the following user input and determine if the user is frustrated, confused, or struggling (True/False). Input: '{transcript}'"
                is_struggling = "true" in (await hf_client.chat([{"role": "user", "content": sentiment_prompt}], max_tokens=10)).lower()
                
                adjusted_system_prompt = system_prompt
                if is_struggling:
                    adjusted_system_prompt += "\n\n### ADAPTIVE MODE: The user seems to be struggling. Be extra patient, use simpler words, and offer more encouragement."
                
                messages = [{"role": "system", "content": adjusted_system_prompt}, *history]
                async for chunk in hf_client.stream_chat(messages):
                    reply_text += chunk
                    await websocket.send_json({"type": "reply_chunk", "text": chunk})
            
            await websocket.send_json({"type": "reply_done", "text": reply_text})
            
            _log_turn(user_id, "assistant", reply_text)
            history.append({"role": "assistant", "content": reply_text})
            history = history[-_MAX_HISTORY_TURNS:]

            # Stream audio in parallel (or after text starts)
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
