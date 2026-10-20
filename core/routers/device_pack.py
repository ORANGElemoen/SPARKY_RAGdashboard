"""
Device-facing endpoints for the Wi-Fi "personality pack" (Sparky Studio content).

A Sparky authenticates with its X-Device-Key (core/routers/device_auth.py),
fetches the pack manifest (ETag/304 when unchanged), downloads voice-line
files it doesn't have, and reports which pack version it now holds.
Wire format documented in docs/PROTOCOL.md ("Personality pack").
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from ..repositories.device_repository import Device
from ..services import device_commands
from ..services import studio_service as studio
from .device_auth import get_device_from_key

router = APIRouter(prefix="/api/v1/device", tags=["device"])


async def require_device(device: Optional[Device] = Depends(get_device_from_key)) -> Device:
    """Like get_device_from_key, but these endpoints are for devices only."""
    if device is None:
        raise HTTPException(status_code=401, detail="Sparky devices only: send your X-Device-Key")
    return device


class PackAck(BaseModel):
    pack_version: str = Field(..., min_length=1, max_length=64)
    free_bytes: int = Field(0, ge=0)
    error: Optional[str] = Field(None, max_length=200)


@router.get("/pack")
async def get_pack(request: Request, device: Device = Depends(require_device)):
    pack = studio.build_pack()
    etag = f'"{pack["pack_version"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(pack, headers={"ETag": etag})


@router.get("/pack/voice/{line_id}.wav")
async def get_pack_voice(line_id: str, device: Device = Depends(require_device)):
    try:
        path = studio.voice_path(line_id)
    except studio.StudioError:
        raise HTTPException(status_code=404, detail="Unknown voice line")
    return FileResponse(path, media_type="audio/wav")


@router.post("/pack/ack")
async def ack_pack(body: PackAck, device: Device = Depends(require_device)):
    studio.record_device_sync(device.id, body.pack_version, body.free_bytes, body.error)
    return {"ok": True}


@router.get("/commands")
async def get_commands(wait: float = 25, device: Device = Depends(require_device)):
    """Long-poll: held open up to `wait` seconds; 204 = nothing to do."""
    command = await device_commands.board.wait(device.id, timeout=max(0.0, min(wait, 30.0)))
    if command is None:
        return Response(status_code=204)
    return command
