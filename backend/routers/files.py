"""Uploaded documents (client photos and PDFs, files sent by the office).

GET /uploads/{name}  the file, for a logged-in user only (token header or session cookie)

Client tax documents must never be readable by someone who only has the link.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from config import settings
from models import User
from routers.deps import require_header_or_cookie

router = APIRouter(tags=["files"])


@router.get("/uploads/{name}")
def uploaded_file(name: str, _user: User = Depends(require_header_or_cookie)):
    # Only a bare file name inside the upload folder: no folders, no "..".
    if not name or Path(name).name != name or name.startswith("."):
        raise HTTPException(404, "הקובץ לא נמצא")
    path = settings.upload_dir / name
    if not path.is_file():
        raise HTTPException(404, "הקובץ לא נמצא")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
