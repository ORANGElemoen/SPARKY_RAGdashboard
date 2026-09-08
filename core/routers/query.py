"""
Simple Query Router
Single AI-only endpoint for RAG queries
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..repositories.device_repository import Device
from .device_auth import get_device_from_key

logger = logging.getLogger(__name__)


# Simple request/response models for single endpoint
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="User question")
    session_id: Optional[str] = Field(
        default=None,
        description="Identifies one learner's conversation (e.g. one browser tab), "
        "so follow-up questions can pull in that session's own recent turns. "
        "Omit for a one-off query with no conversation memory.",
    )


class QueryResponse(BaseModel):
    answer: str = Field(..., description="AI-generated answer")
    sources: list = Field(default=[], description="Retrieved chunks used to ground the answer (document name, chunk text, similarity)")
    confidence: float = Field(..., description="Confidence score")
    timestamp: str = Field(..., description="Response timestamp")
    query: str = Field(..., description="Original query")
    used_general_knowledge: bool = Field(
        default=False,
        description="True if no relevant document chunk was found and the tutor fell back to general knowledge",
    )


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    target_language: str = Field(
        ..., description="Language code matching a file in config/languages/, e.g. 'fr'"
    )


class TranslateResponse(BaseModel):
    translated_text: str
    target_language: str


class StatusResponse(BaseModel):
    service: str
    mode: str
    config: Dict[str, Any]
    healthy: bool


router = APIRouter(prefix="/api/v1", tags=["query"])


# Dependency to get SimpleRAGService
def get_rag_service():
    """Get SimpleRAGService instance"""
    try:
        from ..ollama_client import OllamaClient
        from ..repositories.factory import RepositoryFactory
        from ..services.simple_rag_service import SimpleRAGService

        # Get repositories
        rag_repo = RepositoryFactory.create_production_repository()
        vector_repo = rag_repo.vector_search
        interaction_log_repo = rag_repo.interaction_log

        # Get LLM client with faster timeout for better user experience
        llm_client = OllamaClient(timeout=60)  # 1 minute instead of 3 minutes

        # Create simple RAG service
        return SimpleRAGService(vector_repo, llm_client, interaction_log_repo)

    except Exception as e:
        logger.error(f"Failed to create RAG service: {e}")
        raise HTTPException(status_code=500, detail="Service unavailable")


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    rag_service=Depends(get_rag_service),
    device: Optional[Device] = Depends(get_device_from_key),
):
    """
    Ask a question and get an AI answer with sources

    Single endpoint for all RAG queries - AI answers only
    - **query**: Your question (3-500 characters)
    - Returns AI answer with source citations
    """
    try:
        logger.info(f"Processing query: {request.query[:50]}...")

        # Process query using SimpleRAGService
        response = await rag_service.answer_query(
            request.query,
            query_type="text",
            session_id=request.session_id,
            device_id=device.id if device else None,
        )

        # Check for errors
        if "error" in response:
            raise HTTPException(status_code=400, detail=response["error"])

        return QueryResponse(**response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail="Query processing failed")


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest):
    """Translate a tutor answer or logged question into another configured
    language, so answer quality can be checked outside English/German too.

    Uses the same local Ollama model as everything else - no cloud
    translation API, consistent with the project's offline-first design.
    """
    lang_file = Path(f"config/languages/{request.target_language}.yaml")
    if not lang_file.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown language '{request.target_language}' "
            f"(no config/languages/{request.target_language}.yaml)",
        )

    try:
        with open(lang_file, "r", encoding="utf-8") as f:
            lang_name = (yaml.safe_load(f) or {}).get("name", request.target_language)

        prompt = (
            f"Translate the following text into {lang_name}. Output only the "
            f"translation, with no extra commentary, notes, or quotation marks "
            f"around it.\n\n{request.text}"
        )

        from ..ollama_client import OllamaClient

        llm_client = OllamaClient(timeout=60)
        translated = await asyncio.to_thread(
            llm_client.generate_answer,
            query=prompt,
            context="",
            max_tokens=800,
            temperature=0.2,
            max_retries=1,
            is_complete_prompt=True,
        )

        if not translated:
            raise HTTPException(
                status_code=502,
                detail="Translation failed - the AI model didn't return a result",
            )

        return TranslateResponse(
            translated_text=translated.strip(), target_language=request.target_language
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail="Translation failed")


@router.get("/status", response_model=StatusResponse)
async def get_status(rag_service=Depends(get_rag_service)):
    """Get RAG service status and configuration"""
    try:
        status = rag_service.get_status()
        return StatusResponse(**status)

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")


@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "service": "Simple RAG Query API"}
