"""
Voice Query Router
Speech-to-text -> RAG answer -> text-to-speech, for the voice tutor endpoint.

Two response formats are served from the same endpoint, chosen by the
Accept header:
  - Default (no special Accept header): JSON + base64-encoded WAV, used by
    the browser UI. Unchanged from before - see VoiceQueryResponse.
  - `Accept: application/x-tutor-voice`: a compact length-prefixed binary
    framing intended for hardware clients (ESP32), with the answer's audio
    streamed sentence-by-sentence so playback can start before the whole
    answer finishes synthesizing. See PROTOCOL.md at the repo root for the
    full wire format and core/services/audio_framing.py for the framing
    helper.
"""

import asyncio
import base64
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..repositories.device_repository import Device
from ..services.audio_framing import pack_frame, pack_metadata
from ..services.simple_rag_service import load_language_strings
from ..services.voice_service import split_sentences
from .device_auth import get_device_from_key
from .query import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

# A child's spoken question should be short; this is generous headroom
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

HARDWARE_MEDIA_TYPE = "application/x-tutor-voice"
PROTOCOL_VERSION = 1

# Caps how many transcribe->generate->synthesize pipelines can run at once.
# Each one now overlaps properly on the event loop (see the asyncio.to_thread
# calls below), so without a cap a burst of simultaneous hardware requests
# could pile up unbounded CPU-bound work on the thread pool. Checked with a
# non-blocking Semaphore.locked() test (see below) rather than letting
# requests queue silently for a real-time voice interaction.
MAX_CONCURRENT_VOICE_REQUESTS = int(os.getenv("MAX_CONCURRENT_VOICE_REQUESTS", "4"))
_voice_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VOICE_REQUESTS)

_SENTINEL = object()


def _next_or_sentinel(gen):
    """next(gen), or _SENTINEL when exhausted - see frame_generator below
    for why this can't just be a bare next() call wrapped in try/except."""
    try:
        return next(gen)
    except StopIteration:
        return _SENTINEL


class VoiceQueryResponse(BaseModel):
    transcript: str = Field(..., description="What the speech-to-text engine heard")
    answer_text: str = Field(..., description="The tutor's answer, as text")
    audio_base64: str = Field(..., description="The tutor's answer, spoken (WAV, base64-encoded)")
    sources: list = Field(default=[], description="Retrieved chunks used to ground the answer (document name, chunk text, similarity)")
    used_general_knowledge: bool = Field(
        default=False,
        description="True if no relevant document chunk was found and the tutor fell back to general knowledge",
    )


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


@router.post("/query")
async def voice_query(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(
        default=None,
        description="Identifies one learner's conversation (e.g. one browser tab "
        "or one device), so follow-up questions can pull in that session's own "
        "recent turns.",
    ),
    accept: Optional[str] = Header(default=None),
    rag_service=Depends(get_rag_service),
    voice_service=Depends(get_voice_service),
    device: Optional[Device] = Depends(get_device_from_key),
):
    """
    Ask a question by voice and get a spoken answer back.

    Accepts a short audio recording, transcribes it, answers it using the
    same tutor as the text endpoint, and returns the answer as speech - as
    JSON+base64 by default, or as the framed binary hardware format if the
    request sends `Accept: application/x-tutor-voice` (see PROTOCOL.md).
    """
    hardware_format = accept == HARDWARE_MEDIA_TYPE
    strings = load_language_strings()

    if _voice_semaphore.locked():
        raise HTTPException(
            status_code=503,
            detail="The tutor is busy answering someone else right now - please try again in a moment.",
        )

    async with _voice_semaphore:
        try:
            audio_bytes = await audio.read()

            if not audio_bytes:
                raise HTTPException(status_code=400, detail="Empty audio file")
            if len(audio_bytes) > MAX_AUDIO_SIZE:
                raise HTTPException(
                    status_code=400, detail="Audio file too large (max 10MB)"
                )

            transcript = await asyncio.to_thread(voice_service.transcribe, audio_bytes)
            logger.info(f"Voice transcript: {transcript[:100]}")

            sources = []
            used_general_knowledge = False
            confidence = 0.0

            if len(transcript.strip()) < 3:
                answer_text = strings["voice_retry_prompt"]
                spoken_answer = answer_text
            else:
                rag_response = await rag_service.answer_query(
                    transcript,
                    query_type="voice",
                    session_id=session_id,
                    device_id=device.id if device else None,
                )
                if "error" in rag_response:
                    logger.warning(f"RAG error for voice query: {rag_response['error']}")
                    answer_text = strings["voice_error_prompt"]
                    spoken_answer = answer_text
                else:
                    # answer_text keeps source citations for on-screen display;
                    # spoken_answer omits them so they're never read aloud
                    answer_text = rag_response["answer"]
                    spoken_answer = rag_response.get("spoken_answer", answer_text)
                    sources = rag_response.get("sources", [])
                    used_general_knowledge = rag_response.get(
                        "used_general_knowledge", False
                    )
                    confidence = rag_response.get("confidence", 0.0)

            if hardware_format:
                return await _stream_hardware_response(
                    voice_service=voice_service,
                    transcript=transcript,
                    answer_text=answer_text,
                    spoken_answer=spoken_answer,
                    sources=sources,
                    used_general_knowledge=used_general_knowledge,
                    confidence=confidence,
                )

            audio_response = await asyncio.to_thread(
                voice_service.synthesize, spoken_answer
            )
            audio_b64 = base64.b64encode(audio_response).decode("ascii")

            return VoiceQueryResponse(
                transcript=transcript,
                answer_text=answer_text,
                audio_base64=audio_b64,
                sources=sources,
                used_general_knowledge=used_general_knowledge,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Voice query failed: {e}")
            raise HTTPException(status_code=500, detail="Voice query failed")


async def _stream_hardware_response(
    voice_service,
    transcript: str,
    answer_text: str,
    spoken_answer: str,
    sources: list,
    used_general_knowledge: bool,
    confidence: float,
) -> StreamingResponse:
    """Build the framed binary response for a hardware client.

    Sentences are synthesized one at a time and each frame is written to
    the response as soon as it's ready (see PROTOCOL.md), so a device can
    start playing the first sentence before later ones finish generating.
    """
    sentences = split_sentences(spoken_answer)
    metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "transcript": transcript,
        "answer_text": answer_text,
        "confidence": confidence,
        "used_general_knowledge": used_general_knowledge,
        "sources": sources,
        "frame_count": len(sentences),
    }

    async def frame_generator():
        yield pack_frame(pack_metadata(metadata))

        sentence_generator = voice_service.synthesize_sentences(sentences)
        while True:
            # Each call runs Piper synthesis for one sentence, which is
            # CPU-bound - offload it so the event loop can keep serving
            # other requests while this frame is produced. StopIteration
            # is caught *inside* _next_or_sentinel, in the worker thread,
            # rather than allowed to propagate out of asyncio.to_thread:
            # a StopIteration crossing that boundary is reinterpreted by
            # asyncio as the coroutine itself returning (PEP 479) and
            # surfaces as an unrelated "cannot be raised into a Future"
            # RuntimeError instead of being catchable here.
            wav_bytes = await asyncio.to_thread(_next_or_sentinel, sentence_generator)
            if wav_bytes is _SENTINEL:
                break
            yield pack_frame(wav_bytes)

    return StreamingResponse(frame_generator(), media_type=HARDWARE_MEDIA_TYPE)
