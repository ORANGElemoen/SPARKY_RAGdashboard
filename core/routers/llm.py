"""
LLM management router
Handles LLM-related management endpoints
"""

import logging

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def llm_status():
    """Get real LLM (Ollama) service status.

    This previously returned a hardcoded stub claiming the model was always
    available regardless of whether Ollama was actually running - the exact
    field this endpoint's only real caller, the main tutor page's "AI Model"
    indicator (static/index.html), reads to decide what to show a learner.
    """
    try:
        from datetime import datetime

        from ..ollama_client import OllamaClient

        health = OllamaClient().health_check()
        return {
            "status": "connected" if health.get("available") else "disconnected",
            "host": health.get("base_url"),
            "current_model": health.get("model"),
            "available": health.get("available", False),
            "last_check": datetime.utcnow().isoformat(),
            "error": health.get("error"),
        }
    except Exception as e:
        logger.error(f"Error getting LLM status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
