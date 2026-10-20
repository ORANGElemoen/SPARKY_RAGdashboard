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

from ..repositories.factory import RepositoryFactory
from ..services import device_commands
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


class PreviewBody(BaseModel):
    rows: List[str]
    seconds: int = 10


def _run(fn, *args):
    """Call a studio function, turning bad input into a 400 instead of a 500."""
    try:
        return fn(*args)
    except studio.StudioError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _devices():
    return RepositoryFactory.create_production_repository().devices


async def _nudge_all():
    """Tell idle Sparkys a new pack exists (they still fetch it themselves)."""
    try:
        for d in await _devices().list_devices():
            if d.revoked_at is None:
                device_commands.board.post(d.id, {"type": "sync"})
    except Exception as e:  # a nudge is a nicety - never fail the save over it
        logger.warning(f"Could not nudge devices: {e}")


@router.get("/view", response_class=HTMLResponse)
async def studio_page(request: Request):
    return templates.TemplateResponse("studio.html", {"request": request})


@router.get("")
async def get_studio():
    return _run(studio.summary)


@router.put("/faces/{name}")
async def put_face(name: str, body: FaceBody):
    out = _run(lambda: studio.summary(studio.put_face(name, body.rows)))
    await _nudge_all()
    return out


@router.delete("/faces/{name}")
async def delete_face(name: str):
    out = _run(lambda: studio.summary(studio.delete_face(name)))
    await _nudge_all()
    return out


@router.put("/moods")
async def put_moods(moods: Dict[str, str] = Body(...)):
    out = _run(lambda: studio.summary(studio.set_moods(moods)))
    await _nudge_all()
    return out


@router.post("/faces/import")
async def import_faces(payload: Dict = Body(...)):
    result = _run(studio.import_faces, payload)
    await _nudge_all()
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
    await _nudge_all()
    return {"line": line, **studio.summary()}


@router.get("/voice-lines/{line_id}.wav")
async def get_voice_line(line_id: str):
    return FileResponse(_run(studio.voice_path, line_id), media_type="audio/wav")


@router.delete("/voice-lines/{line_id}")
async def delete_voice_line(line_id: str):
    out = _run(lambda: studio.summary(studio.delete_voice_line(line_id)))
    await _nudge_all()
    return out


@router.get("/export/voice_lines.zip")
async def export_voice_lines():
    return Response(_run(studio.export_voice_zip), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="sparky_voice_lines.zip"'})


# ---------------------------------------------------------------- Sparkys on the network
@router.get("/devices")
async def list_studio_devices():
    current = studio.build_pack()["pack_version"]
    sync = studio.device_sync()
    out = []
    for d in await _devices().list_devices():
        s = sync.get(str(d.id), {})
        out.append({"id": d.id, "name": d.name, "last_seen_at": d.last_seen_at, "revoked": d.revoked_at is not None,
                    "pack_version": s.get("pack_version"), "up_to_date": s.get("pack_version") == current,
                    "free_bytes": s.get("free_bytes"), "error": s.get("error"), "synced_at": s.get("at")})
    return {"pack_version": current, "devices": out}


@router.post("/devices/{device_id}/preview")
async def preview_on_device(device_id: int, body: PreviewBody):
    rows = _run(studio.check_rows, body.rows)
    device = await _devices().get_by_id(device_id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(status_code=404, detail="No active Sparky with that id")
    device_commands.board.post(device_id, {"type": "show_face", "rows": rows, "seconds": max(1, min(body.seconds, 60))})
    return {"ok": True}
