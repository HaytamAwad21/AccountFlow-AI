"""Engine A endpoint (quick-send) and the chasing board's ticket operations."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import ChasingTicket, Client, MessageTemplate, TicketPriority, TicketStatus, User
from routers.deps import client_ip, get_client_or_404, get_ticket_or_404, require_user
from schemas import (
    OcrUpdate,
    QuickSendRequest,
    QuickSendResponse,
    TicketDetail,
    TicketNote,
    TicketOut,
    message_out,
    ticket_detail,
    ticket_out,
)
from services.activity import log_activity
from services.system_settings import get_system_settings
from services.templating import text_direction
from services.ticket_engine import (
    approve_ticket,
    create_and_send_ticket,
    reopen_ticket,
    resolve_ticket,
    template_by_slug,
    touch,
)
from services.vision_ocr import revalidate_with_overrides

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

STATUS_ORDER = case(
    (ChasingTicket.status == TicketStatus.ESCALATED, 0),
    (ChasingTicket.status == TicketStatus.NEEDS_CLERK_REVIEW, 1),
    (ChasingTicket.status == TicketStatus.NEEDS_CORRECTION, 2),
    (ChasingTicket.status == TicketStatus.WAITING_FOR_CLIENT, 3),
    (ChasingTicket.status == TicketStatus.SNOOZED_TONIGHT, 4),
    (ChasingTicket.status == TicketStatus.OPEN, 5),
    else_=6,
)
PRIORITY_ORDER = case(
    (ChasingTicket.priority == TicketPriority.URGENT_DEADLINE, 0),
    (ChasingTicket.priority == TicketPriority.HIGH, 1),
    else_=2,
)


@router.post("/quick-send", response_model=QuickSendResponse, status_code=201)
def quick_send(body: QuickSendRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    started = time.perf_counter()
    client = get_client_or_404(db, body.client_id)
    if body.template_id:
        template = db.get(MessageTemplate, body.template_id)
        if not template:
            raise HTTPException(404, "התבנית לא נמצאה")
    elif body.template_slug:
        template = template_by_slug(db, body.template_slug)
    else:
        raise HTTPException(422, "יש לבחור תבנית")

    ticket, msg = create_and_send_ticket(
        db, client=client, template=template, variables=body.context_variables,
        worker_id=user.id, priority=body.priority,
    )
    log_activity(db, user, "TICKET_SENT", f"נשלחה בקשה ”{template.name_he}“ אל {client.full_name} ({ticket.ticket_ref})",
                 entity_type="ticket", entity_id=ticket.id, ip_address=client_ip(request))
    db.commit()
    return QuickSendResponse(
        ticket=ticket_out(ticket),
        message=message_out(msg),
        rendered_text=msg.content_text,
        buttons=msg.buttons_json or [],
        direction=text_direction(),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
    )


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: list[TicketStatus] | None = Query(None),
    client_id: int | None = None,
    q: str = "",
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    stmt = select(ChasingTicket).join(Client)
    if status:
        stmt = stmt.where(ChasingTicket.status.in_(status))
    if client_id:
        stmt = stmt.where(ChasingTicket.client_id == client_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(ChasingTicket.ticket_ref.ilike(like), Client.full_name.ilike(like), Client.company_name.ilike(like)))
    stmt = stmt.order_by(STATUS_ORDER, PRIORITY_ORDER, ChasingTicket.updated_at.desc()).limit(limit)
    return [ticket_out(t) for t in db.scalars(stmt)]


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    return ticket_detail(get_ticket_or_404(db, ticket_id))


@router.post("/{ticket_id}/approve", response_model=TicketDetail)
def approve(ticket_id: int, request: Request, body: TicketNote | None = None, db: Session = Depends(get_db),
            user: User = Depends(require_user)):
    ticket = get_ticket_or_404(db, ticket_id)
    approve_ticket(db, ticket, user, (body.note if body else ""))
    log_activity(db, user, "TICKET_APPROVED", f"אושרה החשבונית בפנייה {ticket.ticket_ref} של {ticket.client.full_name}",
                 entity_type="ticket", entity_id=ticket.id, ip_address=client_ip(request))
    db.commit()
    return ticket_detail(ticket)


@router.post("/{ticket_id}/resolve", response_model=TicketDetail)
def resolve(ticket_id: int, request: Request, body: TicketNote | None = None, db: Session = Depends(get_db),
            user: User = Depends(require_user)):
    ticket = get_ticket_or_404(db, ticket_id)
    resolve_ticket(db, ticket, body.note if body else "")
    log_activity(db, user, "TICKET_RESOLVED", f"נסגרה הפנייה {ticket.ticket_ref} של {ticket.client.full_name}",
                 entity_type="ticket", entity_id=ticket.id, ip_address=client_ip(request))
    db.commit()
    return ticket_detail(ticket)


@router.post("/{ticket_id}/reopen", response_model=TicketDetail)
def reopen(ticket_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    ticket = get_ticket_or_404(db, ticket_id)
    reopen_ticket(db, ticket)
    log_activity(db, user, "TICKET_REOPENED", f"נפתחה מחדש הפנייה {ticket.ticket_ref} של {ticket.client.full_name}",
                 entity_type="ticket", entity_id=ticket.id, ip_address=client_ip(request))
    db.commit()
    return ticket_detail(ticket)


@router.patch("/{ticket_id}/ocr", response_model=TicketDetail)
def edit_ocr(ticket_id: int, body: OcrUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    ticket = get_ticket_or_404(db, ticket_id)
    overrides = body.model_dump(exclude_unset=True)
    if not overrides:
        raise HTTPException(422, "לא הוזנו שדות לעדכון")
    office = get_system_settings(db)
    ticket.ocr_validation_json = revalidate_with_overrides(
        ticket.ocr_validation_json, overrides, "he",
        vat_rate=office.vat_rate / 100.0, allocation_threshold=office.allocation_number_threshold_nis,
    )
    if ticket.status in (TicketStatus.NEEDS_CORRECTION, TicketStatus.WAITING_FOR_CLIENT, TicketStatus.ESCALATED):
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
    log_activity(db, user, "OCR_EDITED", f"תוקנו ידנית שדות החשבונית בפנייה {ticket.ticket_ref}: {', '.join(overrides)}",
                 entity_type="ticket", entity_id=ticket.id, details=overrides, ip_address=client_ip(request))
    touch(db, ticket)
    db.commit()
    return ticket_detail(ticket)
