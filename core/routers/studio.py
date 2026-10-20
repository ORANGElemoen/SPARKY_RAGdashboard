"""
Sparky Studio admin endpoints - design faces, map them to moods, make voice
lines in Sparky's own voice, and export both for the ESP32 firmware.
Logic lives in core/services/studio_service.py; this file only adapts HTTP.

Every POST/PUT/DELETE here is under /admin, so the CSRF middleware in
core/main.py applies - the page sends X-CSRF-Token like the other admin pages.
"""

import asyncio
import logging
from typing import Dict, List

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..services import studio_service as studio

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="core/templates")
router = APIRouter(prefix="/admin/studio", tags=["studio"])


class FaceBody(BaseModel):
    rows: List[str]


class VoiceLineBody(BaseModel):
    text: str
    trigger: str = "custom"
    mood: str = "talking"


def _run(fn, *args):
    """Call a studio function, turning bad input into a 400 instead of a 500."""
    try:
        return fn(*args)
    except studio.StudioError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/view", response_class=HTMLResponse)
async def studio_page(request: Request):
    return templates.TemplateResponse("studio.html", {"request": request})


@router.get("")
async def get_studio():
    return _run(studio.summary)


@router.put("/faces/{name}")
async def put_face(name: str, body: FaceBody):
    return _run(lambda: studio.summary(studio.put_face(name, body.rows)))


@router.delete("/faces/{name}")
async def delete_face(name: str):
    return _run(lambda: studio.summary(studio.delete_face(name)))


@router.put("/moods")
async def put_moods(moods: Dict[str, str] = Body(...)):
    return _run(lambda: studio.summary(studio.set_moods(moods)))


@router.post("/faces/import")
async def import_faces(payload: Dict = Body(...)):
    result = _run(studio.import_faces, payload)
    return {**result, **studio.summary()}


@router.get("/faces/export")
async def export_faces():
    return JSONResponse(studio.export_faces_file(),
                        headers={"Content-Disposition": 'attachment; filename="sparky_faces.json"'})


@router.get("/export/sparky_faces.h")
async def export_header():
    return Response(_run(studio.export_header), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="sparky_faces.h"'})


@router.post("/voice-lines")
async def add_voice_line(body: VoiceLineBody):
    try:
        from ..services.voice_service import VoiceService  # lazy: voice deps are optional
    except ImportError:
        raise HTTPException(status_code=503, detail=(
            "Voice support is not installed. Run: "
            "pip install -r deployment/requirements/voice_requirements.txt"))
    text = " ".join(body.text.split())
    if not text or len(text) > studio.MAX_TEXT:
        raise HTTPException(status_code=400, detail=f"A voice line must be 1-{studio.MAX_TEXT} characters.")
    try:
        wav = await asyncio.to_thread(VoiceService().synthesize, text)
    except Exception as e:
        logger.error(f"Studio voice line synthesis failed: {e}")
        raise HTTPException(status_code=503, detail="Sparky's voice could not be loaded. Check the Piper voice model.")
    line = _run(studio.add_voice_line, text, body.trigger, body.mood, wav)
    return {"line": line, **studio.summary()}


@router.get("/voice-lines/{line_id}.wav")
async def get_voice_line(line_id: str):
    return FileResponse(_run(studio.voice_path, line_id), media_type="audio/wav")


@router.delete("/voice-lines/{line_id}")
async def delete_voice_line(line_id: str):
    return _run(lambda: studio.summary(studio.delete_voice_line(line_id)))


@router.get("/export/voice_lines.zip")
async def export_voice_lines():
    return Response(_run(studio.export_voice_zip), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="sparky_voice_lines.zip"'})
