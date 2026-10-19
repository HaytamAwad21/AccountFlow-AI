"""Engine C endpoints: inbound WhatsApp webhook (simulator JSON, Meta Cloud API, multipart
uploads), simulator demo receipts, read receipts and the real-time SSE stream."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import ChasingTicket, Client, DeliveryStatus, MessageDirection, User, WhatsAppMessageLog
from routers.deps import get_client_or_404, require_user
from schemas import DemoReceiptRequest, InboundMessage, InboundResult, ticket_out
from services.demo_invoices import generate_invoice_image, parse_amount
from services.events import broker, queue_event
from services.system_settings import get_system_settings
from services.ticket_engine import (
    EngineError,
    find_awaiting_ticket,
    handle_button,
    handle_media,
    handle_text,
    save_upload,
)
from services.whatsapp import download_cloud_media, normalize_phone, parse_button_payload

log = logging.getLogger("accountflow.webhook")
router = APIRouter(prefix="/api", tags=["webhook"])


def _resolve_client(db: Session, client_id: int | None, from_phone: str | None) -> Client:
    if client_id:
        return get_client_or_404(db, client_id)
    if from_phone:
        client = db.scalar(select(Client).where(Client.whatsapp_phone == normalize_phone(from_phone)))
        if client:
            return client
    raise HTTPException(404, "שולח לא מזוהה: יש לציין client_id או מספר וואטסאפ רשום")


def _result(out: dict, started: float, action: str | None = None) -> InboundResult:
    ticket = out.get("ticket")
    return InboundResult(
        ticket=ticket_out(ticket) if ticket else None,
        action=out.get("action", action),
        reply=out.get("reply"),
        ocr=out.get("ocr"),
        validation=out.get("validation"),
        unsolicited=bool(out.get("unsolicited")),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _process_simple(payload: InboundMessage) -> InboundResult:
    started = time.perf_counter()
    with SessionLocal() as db:
        client = _resolve_client(db, payload.client_id, payload.from_phone)
        if payload.type == "button":
            ticket_id, button_id = payload.ticket_id, payload.button_id
            if payload.payload:
                parsed_ticket, button_id = parse_button_payload(payload.payload)
                ticket_id = ticket_id or parsed_ticket
            if not button_id:
                raise HTTPException(422, "חסר מזהה כפתור (button_id)")
            out = handle_button(db, client, button_id, ticket_id)
        else:
            if not (payload.text or "").strip():
                raise HTTPException(422, "חסר טקסט הודעה")
            out = handle_text(db, client, payload.text.strip(), payload.ticket_id)
        db.commit()
        return _result(out, started)


def _process_upload(client_id: int | None, from_phone: str | None, ticket_id: int | None,
                    content: bytes, filename: str, mime: str, caption: str) -> InboundResult:
    started = time.perf_counter()
    with SessionLocal() as db:
        client = _resolve_client(db, client_id, from_phone)
        path, url, mime = save_upload(content, filename, mime)
        out = handle_media(db, client, path, url, mime, ticket_id, caption)
        db.commit()
        return _result(out, started)


def _process_meta(body: dict) -> dict:
    """Handle the official WhatsApp Cloud API webhook envelope."""
    processed = 0
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                _apply_status(status)
            for m in value.get("messages", []):
                try:
                    _process_meta_message(m)
                    processed += 1
                except HTTPException as exc:
                    log.warning("Ignoring inbound message from %s: %s", m.get("from"), exc.detail)
    return {"ok": True, "processed": processed}


def _apply_status(status: dict) -> None:
    mapping = {"sent": DeliveryStatus.SENT, "delivered": DeliveryStatus.DELIVERED, "read": DeliveryStatus.READ,
               "failed": DeliveryStatus.FAILED}
    new = mapping.get(status.get("status"))
    if not new:
        return
    with SessionLocal() as db:
        msg = db.scalar(select(WhatsAppMessageLog).where(WhatsAppMessageLog.external_id == status.get("id")))
        if msg:
            msg.delivery_status = new
            queue_event(db, {"type": "message", "client_id": msg.client_id, "ticket_id": msg.ticket_id})
            db.commit()


def _process_meta_message(m: dict) -> None:
    phone = "+" + m.get("from", "").lstrip("+")
    kind = m.get("type")
    if kind == "text":
        _process_simple(InboundMessage(from_phone=phone, type="text", text=m["text"]["body"]))
    elif kind == "button":
        _process_simple(InboundMessage(from_phone=phone, type="button", payload=m["button"].get("payload") or m["button"].get("text")))
    elif kind == "interactive":
        reply = m["interactive"].get("button_reply") or m["interactive"].get("list_reply") or {}
        _process_simple(InboundMessage(from_phone=phone, type="button", payload=reply.get("id")))
    elif kind in ("image", "document"):
        media = m[kind]
        content, mime = download_cloud_media(media["id"])
        _process_upload(None, phone, None, content, media.get("filename") or f"{media['id']}", mime, media.get("caption", ""))


@router.get("/webhook/whatsapp-inbound", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_token == settings.whatsapp_verify_token:
        return hub_challenge
    raise HTTPException(403, "אסימון האימות שגוי")


@router.post("/webhook/whatsapp-inbound")
async def whatsapp_inbound(request: Request):
    """Accepts three shapes:
    * multipart/form-data  – file upload (fields: file, client_id | from_phone, ticket_id?, caption?)
    * JSON {object: "whatsapp_business_account", entry: [...]}  – Meta Cloud API webhook
    * JSON InboundMessage  – the in-app simulator (button taps & text)
    """
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise HTTPException(422, "חסר קובץ (file) בהעלאה")
            content = await upload.read()
            client_id = int(form["client_id"]) if form.get("client_id") else None
            ticket_id = int(form["ticket_id"]) if form.get("ticket_id") else None
            result = await run_in_threadpool(
                _process_upload, client_id, form.get("from_phone"), ticket_id, content,
                upload.filename or "upload", upload.content_type or "", str(form.get("caption") or ""),
            )
            return result.model_dump(mode="json")

        body = await request.json()
        if isinstance(body, dict) and body.get("object") == "whatsapp_business_account":
            return await run_in_threadpool(_process_meta, body)
        payload = InboundMessage.model_validate(body)
        result = await run_in_threadpool(_process_simple, payload)
        return result.model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json())) from exc
    except EngineError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


# ── simulator helpers ────────────────────────────────────────────────────────

def _demo_receipt(body: DemoReceiptRequest) -> InboundResult:
    started = time.perf_counter()
    with SessionLocal() as db:
        client = get_client_or_404(db, body.client_id)
        ticket = find_awaiting_ticket(db, client, body.ticket_id, for_media=True)
        ctx = (ticket.context_variables_json if ticket else {}) or {}
        amount = parse_amount(ctx.get("amount") or ctx.get("charge_amount") or ctx.get("expected_amount"))
        office = get_system_settings(db)
        path, _meta = generate_invoice_image(
            scenario=body.scenario,
            supplier_name=ctx.get("supplier_name") or "Office Supplies Ltd.",
            invoice_number=ctx.get("invoice_number"),
            client_company=client.company_name or client.full_name,
            amount_total=amount,
            invoice_date=ctx.get("invoice_date") or ctx.get("charge_date"),
            vat_rate=office.vat_rate / 100.0,
            allocation_threshold=office.allocation_number_threshold_nis,
        )
        url = f"/uploads/{path.name}"
        out = handle_media(db, client, path, url, "image/png", ticket.id if ticket else None, "")
        db.commit()
        return _result(out, started)


@router.post("/simulator/demo-receipt", response_model=InboundResult)
async def simulator_demo_receipt(body: DemoReceiptRequest, _user: User = Depends(require_user)):
    try:
        return await run_in_threadpool(_demo_receipt, body)
    except EngineError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/simulator/{client_id}/read")
def simulator_mark_read(client_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    """The simulated phone opened the chat: mark outbound messages as READ (blue ticks)."""
    get_client_or_404(db, client_id)
    result = db.execute(
        update(WhatsAppMessageLog)
        .where(
            WhatsAppMessageLog.client_id == client_id,
            WhatsAppMessageLog.direction == MessageDirection.OUTBOUND,
            WhatsAppMessageLog.delivery_status.in_([DeliveryStatus.SENT, DeliveryStatus.DELIVERED]),
        )
        .values(delivery_status=DeliveryStatus.READ)
    )
    if result.rowcount:
        queue_event(db, {"type": "message", "client_id": client_id, "ticket_id": None})
    db.commit()
    return {"ok": True, "updated": result.rowcount}


@router.get("/simulator/{client_id}/active-ticket")
def simulator_active_ticket(client_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    client = get_client_or_404(db, client_id)
    ticket: ChasingTicket | None = find_awaiting_ticket(db, client, for_media=True)
    return {"ticket": ticket_out(ticket).model_dump(mode="json") if ticket else None}


# ── real-time stream ─────────────────────────────────────────────────────────

@router.get("/events/stream")
async def event_stream(request: Request):
    queue = broker.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
