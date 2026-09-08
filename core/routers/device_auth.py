"""
Device authentication dependency.

Lets a registered hardware device (see DeviceRepository) call the API
endpoints directly via an X-Device-Key header, without the browser's
cookie/CSRF dance - see the CSRF middleware in core/main.py, which exempts
a request carrying a *valid* device key from the CSRF check entirely.

Purely additive: a request with no X-Device-Key header behaves exactly as
before (browser flow, untouched).
"""

import logging
from typing import Optional

from fastapi import Header, HTTPException

from ..repositories.device_repository import Device
from ..repositories.factory import RepositoryFactory

logger = logging.getLogger(__name__)


async def get_device_from_key(
    x_device_key: Optional[str] = Header(default=None),
) -> Optional[Device]:
    """FastAPI dependency: resolve the calling device from X-Device-Key.

    Returns None if the header is absent (browser request). Raises 401 if
    the header is present but doesn't match an active device - a request
    with a garbage/revoked key is almost certainly a misconfigured or
    revoked hardware client, not a browser, so it gets a specific error
    rather than falling through to the generic CSRF failure.
    """
    if not x_device_key:
        return None

    device_repo = RepositoryFactory.create_production_repository().devices
    device = await device_repo.get_by_api_key(x_device_key)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or revoked device key")

    await device_repo.touch_last_seen(device.id)
    return device
