"""
Voice Query Router
Speech-to-text -> RAG answer -> text-to-speech, for the voice tutor endpoint.
"""

import base64
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..services.simple_rag_service import load_language_strings
from .query import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

# A child's spoken question should be short; this is generous headroom
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB


class VoiceQueryResponse(BaseModel):
    transcript: str = Field(..., description="What the speech-to-text engine heard")
    answer_text: str = Field(..., description="The tutor's answer, as text")
    audio_base64: str = Field(..., description="The tutor's answer, spoken (WAV, base64-encoded)")


def get_voice_service():
    """Get VoiceService instance (imports faster-whisper/piper lazily)"""
    try:
        from ..services.voice_service import VoiceService

        return VoiceService()
    except ImportError as e:
        logger.error(f"Voice dependencies not installed: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                "Voice support is not installed. Run: "
                "pip install -r deployment/requirements/voice_requirements.txt"
            ),
        )


@router.post("/query", response_model=VoiceQueryResponse)
async def voice_query(
    audio: UploadFile = File(...),
    rag_service=Depends(get_rag_service),
    voice_service=Depends(get_voice_service),
):
    """
    Ask a question by voice and get a spoken answer back.

    Accepts a short audio recording, transcribes it, answers it using the
    same tutor as the text endpoint, and returns the answer as speech.
    """
    strings = load_language_strings()
    try:
        audio_bytes = await audio.read()

        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if len(audio_bytes) > MAX_AUDIO_SIZE:
            raise HTTPException(
                status_code=400, detail="Audio file too large (max 10MB)"
            )

        transcript = voice_service.transcribe(audio_bytes)
        logger.info(f"Voice transcript: {transcript[:100]}")

        if len(transcript.strip()) < 3:
            answer_text = strings["voice_retry_prompt"]
            spoken_answer = answer_text
        else:
            rag_response = await rag_service.answer_query(transcript)
            if "error" in rag_response:
                logger.warning(f"RAG error for voice query: {rag_response['error']}")
                answer_text = strings["voice_error_prompt"]
                spoken_answer = answer_text
            else:
                # answer_text keeps source citations for on-screen display;
                # spoken_answer omits them so they're never read aloud
                answer_text = rag_response["answer"]
                spoken_answer = rag_response.get("spoken_answer", answer_text)

        audio_response = voice_service.synthesize(spoken_answer)
        audio_b64 = base64.b64encode(audio_response).decode("ascii")

        return VoiceQueryResponse(
            transcript=transcript,
            answer_text=answer_text,
            audio_base64=audio_b64,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice query failed: {e}")
        raise HTTPException(status_code=500, detail="Voice query failed")
