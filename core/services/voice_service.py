"""
Voice Service
Speech-to-text (faster-whisper) and text-to-speech (Piper), both fully local/offline.
Models are loaded once per process (lazy singletons) since loading them is slow.
"""

import io
import logging
import os
import wave
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_whisper_model = None
_piper_voice = None


def _get_active_language() -> str:
    """Reuse the language selected in the admin Settings page as a hint for STT"""
    try:
        lang_config_path = Path("config/language_config.yaml")
        if lang_config_path.exists():
            with open(lang_config_path, "r", encoding="utf-8") as f:
                lang_config = yaml.safe_load(f) or {}
            return lang_config.get("current_language", "en")
    except Exception as e:
        logger.warning(f"Failed to read language config, defaulting to English: {e}")
    return "en"


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        logger.info(f"Loading Whisper model: {model_size}")
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_model


def _get_piper_voice():
    global _piper_voice
    if _piper_voice is None:
        from piper import PiperVoice

        voice_name = os.getenv("PIPER_VOICE", "en_US-hfc_female-medium")
        voice_dir = Path(os.getenv("PIPER_VOICE_DIR", "data/piper_voices"))
        model_path = voice_dir / f"{voice_name}.onnx"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Piper voice model not found at {model_path}. Download it with:\n"
                f"  python -m piper.download_voices {voice_name} "
                f"--download-dir {voice_dir}"
            )

        logger.info(f"Loading Piper voice: {voice_name}")
        _piper_voice = PiperVoice.load(str(model_path))
    return _piper_voice


class VoiceService:
    """Speech-to-text and text-to-speech for the voice tutor endpoint"""

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe spoken audio (any ffmpeg/PyAV-readable format) to text"""
        model = _get_whisper_model()
        segments, _info = model.transcribe(
            io.BytesIO(audio_bytes), language=_get_active_language()
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to speech, returning WAV audio bytes"""
        voice = _get_piper_voice()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return buffer.getvalue()
