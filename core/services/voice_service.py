"""
Voice Service
Speech-to-text (faster-whisper) and text-to-speech (Piper), both fully local/offline.
Models are loaded once per process (lazy singletons) since loading them is slow.
"""

import io
import logging
import os
import re
import unicodedata
import wave
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Split on sentence-ending punctuation followed by whitespace. Not perfect
# (e.g. "Dr." mid-sentence), but good enough for TTS chunking - an
# occasional over-split just means one shorter audio chunk, not a
# correctness problem the way it would be for text display.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# The LLM writes chat-style text; Piper/espeak reads symbols aloud ("asterisk",
# "slash") or makes odd sounds on them. These turn it into speakable text.
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")                  # **Recipe** -> Recipe
_ACTION_RE = re.compile(r"\*[^*\n]+\*")                     # *beep boop* -> (dropped)
_BRACKET_RE = re.compile(r"\s*[(\[]([^()\[\]]*)[)\]]")      # "glue (PVA)" -> "glue, PVA,"
_FRACTION_RE = re.compile(r"(?<![\w/])(\d+)/(\d+)(?![\w/])")  # 5/8, but not dates like 1/2/2026
_SYMBOL_RE = re.compile(r"[*#_`~|>]")

_whisper_model = None
_piper_voice = None


def clean_for_speech(text: str, strings: Optional[Dict] = None) -> str:
    """Turn chat-formatted LLM text into something TTS reads naturally.

    Language-specific words (fraction names) come from the language file's
    speech_fractions / speech_fraction_template, so nothing spoken is
    hardcoded here.
    """
    if strings is None:
        from .simple_rag_service import load_language_strings
        strings = load_language_strings()

    text = _BOLD_RE.sub(r"\2", text)
    text = _ACTION_RE.sub("", text)
    text = _BRACKET_RE.sub(r", \1,", text)

    fractions = strings.get("speech_fractions") or {}
    template = strings.get("speech_fraction_template", "{numerator} / {denominator}")
    text = _FRACTION_RE.sub(
        lambda m: f" {fractions.get(m.group(0)) or template.format(numerator=m.group(1), denominator=m.group(2))} ",
        text,
    )

    # Emoji: espeak reads their names ("smiling face with...")
    text = "".join(c for c in text if unicodedata.category(c) != "So" and c not in "\u200d\ufe0f")
    text = _SYMBOL_RE.sub("", text)
    text = re.sub(r"(?<=[A-Za-z])/(?=[A-Za-z])", " ", text)  # and/or -> and or

    # Tidy the punctuation the bracket swap leaves behind: "slime,." / "fun!,"
    text = re.sub(r"\s*,\s*(?=[.!?,;:])", "", text)
    text = re.sub(r"([!?])[.,]", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +([.!?,;:])", r"\1", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    """Split text into sentence-sized chunks for streaming TTS.

    Exposed as a plain function (not a VoiceService method) so a caller can
    compute the chunk count - needed for the hardware protocol's
    frame_count metadata field - before synthesis actually starts.
    """
    text = clean_for_speech(text)
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


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
            voice.synthesize_wav(clean_for_speech(text), wav_file)
        return buffer.getvalue()

    def synthesize_sentences(self, sentences: List[str]) -> Iterator[bytes]:
        """Synthesize a pre-split list of sentences, yielding one WAV per sentence.

        Lets a caller start sending/playing audio for the first sentence
        while later sentences are still being synthesized, instead of
        waiting for the whole answer. Each yielded chunk is a complete,
        independently-playable WAV file (own header), using Piper's
        streaming synthesize() API (returns raw PCM AudioChunks) rather
        than the batch synthesize_wav() helper `synthesize()` above uses.

        Takes a pre-split sentence list (see split_sentences) rather than
        splitting internally, so a caller can know the chunk count upfront.
        """
        voice = _get_piper_voice()

        for sentence in sentences:
            audio_chunks = list(voice.synthesize(sentence))
            if not audio_chunks:
                continue

            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(audio_chunks[0].sample_channels)
                wav_file.setsampwidth(audio_chunks[0].sample_width)
                wav_file.setframerate(audio_chunks[0].sample_rate)
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
            yield buffer.getvalue()
