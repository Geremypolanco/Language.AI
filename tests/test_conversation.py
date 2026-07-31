import base64

from fastapi.testclient import TestClient

from backend.main import app
from test_api import _onboard


def test_audio_message_in_demo_mode_gives_an_accurate_no_retry_error():
    """Regression test: this used to send the same generic "no se pudo
    transcribir, intenta de nuevo" message whether HF_TOKEN was missing
    (where retrying can never help) or a real transcription attempt failed
    (where it might) — see backend/routers/conversation.py."""
    with TestClient(app) as client:
        user = _onboard(client, email="talklive1@example.com")
        with client.websocket_connect(f"/ws/conversation/{user['id']}") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"

            fake_audio = base64.b64encode(b"not real audio").decode()
            ws.send_json({"type": "audio", "data": fake_audio, "content_type": "audio/webm"})
            reply = ws.receive_json()
            assert reply["type"] == "error"
            assert "modo demo" in reply["message"].lower()
            assert "hf_token" in reply["message"].lower()


def test_text_message_still_works_in_demo_mode():
    with TestClient(app) as client:
        user = _onboard(client, email="talklive2@example.com")
        with client.websocket_connect(f"/ws/conversation/{user['id']}") as ws:
            ws.receive_json()  # ready

            ws.send_json({"type": "text", "data": "Hola, quiero practicar"})
            transcript = ws.receive_json()
            assert transcript == {"type": "transcript", "text": "Hola, quiero practicar"}

            reply = ws.receive_json()
            assert reply["type"] == "reply"
            assert reply["text"]
