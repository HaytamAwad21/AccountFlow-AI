"""Manual worker-to-customer WhatsApp messages (free text and / or a picture or PDF).

`POST /api/whatsapp/manual-send` (multipart/form-data):
    client_id     int, required
    content_text  str, optional
    image_file    file, optional (.jpg / .jpeg / .png / .webp / .pdf)
    image_base64  str, optional (a data URL or raw base64 of the same file types)
    media_url     str, optional (an existing "/uploads/<name>" file, e.g. a previous upload)

At least one of the text or the attachment is required. The message is logged with
`is_automated = False` and the worker as sender, so the customer sees "הודעה מאת <worker>".
"""
from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from routers.deps import client_ip, get_client_or_404, require_user
from schemas import MessageOut, message_out
from services.activity import log_activity
from services.ticket_engine import MAX_UPLOAD_BYTES, EngineError, send_manual_message

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

MANUAL_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
MIME_TO_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
UNSUPPORTED = "סוג קובץ לא נתמך. ניתן לצרף JPG, PNG, WEBP או PDF."
DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w/+.-]+);base64,(?P<data>.+)$", re.S)


def _store(content: bytes, ext: str) -> str:
    if not content:
        raise HTTPException(422, "הקובץ המצורף ריק")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "הקובץ גדול מדי (מקסימום 15MB)")
    name = f"out_{uuid.uuid4().hex[:16]}{ext}"
    (settings.upload_dir / name).write_bytes(content)
    return f"/uploads/{name}"


def _from_upload(upload: UploadFile, content: bytes) -> tuple[str, str]:
    ext = Path(upload.filename or "").suffix.lower()
    mime = MANUAL_MEDIA_TYPES.get(ext)
    if mime is None:
        mime = (upload.content_type or "").lower()
        ext = MIME_TO_EXT.get(mime, "")
    if not ext:
        raise HTTPException(422, UNSUPPORTED)
    return _store(content, ext), mime


def _from_base64(raw: str) -> tuple[str, str]:
    m = DATA_URL_RE.match(raw.strip())
    mime, data = (m.group("mime").lower(), m.group("data")) if m else ("", raw.strip())
    try:
        content = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "קובץ base64 לא תקין") from exc
    if not mime:
        if content.startswith(b"\x89PNG"):
            mime = "image/png"
        elif content.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            mime = "image/webp"
        elif content.startswith(b"%PDF"):
            mime = "application/pdf"
    ext = MIME_TO_EXT.get(mime)
    if not ext:
        raise HTTPException(422, UNSUPPORTED)
    return _store(content, ext), mime


def _from_existing(media_url: str) -> tuple[str, str]:
    name = Path(media_url.strip()).name
    ext = Path(name).suffix.lower()
    if not media_url.strip().startswith("/uploads/") or ext not in MANUAL_MEDIA_TYPES:
        raise HTTPException(422, UNSUPPORTED)
    if not (settings.upload_dir / name).is_file():
        raise HTTPException(404, "הקובץ המצורף לא נמצא")
    return f"/uploads/{name}", MANUAL_MEDIA_TYPES[ext]


@router.post("/manual-send", response_model=MessageOut, status_code=201)
async def manual_send(
    request: Request,
    client_id: int = Form(...),
    content_text: str = Form(""),
    image_file: UploadFile | None = File(None),
    image_base64: str = Form(""),
    media_url: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    client = get_client_or_404(db, client_id)
    stored_url: str | None = None
    mime: str | None = None
    if image_file is not None and image_file.filename:
        stored_url, mime = _from_upload(image_file, await image_file.read())
    elif image_base64.strip():
        stored_url, mime = _from_base64(image_base64)
    elif media_url.strip():
        stored_url, mime = _from_existing(media_url)

    try:
        msg = send_manual_message(db, client=client, worker=user, text=content_text, media_url=stored_url, media_mime=mime)
    except EngineError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    log_activity(db, user, "MANUAL_MESSAGE_SENT", f"שליחת הודעה ידנית ללקוח {client.full_name}",
                 entity_type="client", entity_id=client.id,
                 details={"message_id": msg.id, "has_media": bool(stored_url)}, ip_address=client_ip(request))
    db.commit()
    return message_out(msg)
