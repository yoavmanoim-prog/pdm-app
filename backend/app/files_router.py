"""
On-site file server (used only by app.onsite, not by the cloud app).

Serves the PDF/SVG files written by ``storage_local`` over a signed, expiring
link — the on-site replacement for an S3 presigned URL. This router is mounted
WITHOUT the login dependency on purpose: the browser opens these links by plain
navigation (``<a href>`` / ``<iframe src>``), which can't attach the JWT header.
The HMAC signature in the query string is the access control instead, so an
unsigned or tampered/expired link is refused.
"""

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app import storage_local

router = APIRouter(tags=["files"])

# Map file extensions to the Content-Type the browser needs to render inline.
# Anything unknown falls back to a generic binary type (forces a download).
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@router.get("/files/{full_path:path}")
def get_file(
    full_path: str,
    exp: int = Query(..., description="Unix expiry timestamp the link was signed with"),
    sig: str = Query(..., description="HMAC signature proving the link is authorised"),
):
    # 1) The signature must match this exact path+expiry and not be expired.
    #    Reuse the same sign/verify the URL was minted with in storage_local.
    if not storage_local.verify(full_path, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired file link")

    # 2) Block path traversal: the resolved absolute path must stay inside the
    #    storage root, so a crafted "../../etc/passwd" can never escape it.
    root = os.path.realpath(storage_local.LOCAL_STORAGE_PATH)
    target = os.path.realpath(os.path.join(root, full_path))
    if not (target == root or target.startswith(root + os.sep)):
        raise HTTPException(status_code=403, detail="Invalid file path")

    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")

    # 3) Stream the file with the right Content-Type so PDFs render inline.
    media_type = _CONTENT_TYPES.get(os.path.splitext(target)[1].lower(),
                                    "application/octet-stream")
    return FileResponse(target, media_type=media_type)
