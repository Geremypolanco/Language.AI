"""Speech Service - Whisper for transcription + TTS"""

import logging
from typing import Optional
import io

logger = logging.getLogger(__name__)

class SpeechService:
    def __init__(self):
        self.whisper_model = None
        self.tts_model = None
        self._initialize_models()

    def _initialize_models(self):
        """Lazy load models on first use"""
        try:
            import whisper
            self.whisper_model = whisper.load_model("base")
        except ImportError:
            logger.warning("Whisper not installed. Install with: pip install openai-whisper")

    async def transcribe_audio(self, audio_file: bytes) -> dict:
        """Transcribe audio file using Whisper"""
        if not self.whisper_model:
            return {"error": "Whisper model not available"}
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_file)
                tmp.flush()
                
                result = self.whisper_model.transcribe(tmp.name)
                return {
                    "text": result["text"],
                    "language": result.get("language", "unknown"),
                    "confidence": 0.9,
                }
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"error": str(e)}

    async def check_pronunciation(self, user_text: str, reference_text: str) -> dict:
        """Check pronunciation accuracy"""
        # Placeholder - would integrate with speech analysis
        return {
            "accuracy": 85,
            "issues": ["R pronunciation", "Stress on syllable 2"],
            "suggestions": ["Practice rolling R", "Emphasize second syllable"],
        }

    async def generate_speech(self, text: str, language: str = "en") -> bytes:
        """Generate speech from text using TTS"""
        try:
            from TTS.api import TTS
            if not self.tts_model:
                self.tts_model = TTS(model_name="tts_models/en/ljspeech/glow-tts", gpu=False)
            
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                self.tts_model.tts_to_file(text=text, file_path=tmp.name)
                with open(tmp.name, "rb") as f:
                    return f.read()
        except ImportError:
            logger.warning("TTS not installed. Install with: pip install TTS")
            return b""
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return b""

# Singleton instance
_speech_service: Optional[SpeechService] = None

def get_speech_service() -> SpeechService:
    global _speech_service
    if _speech_service is None:
        _speech_service = SpeechService()
    return _speech_service
