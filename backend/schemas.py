"""Pydantic v2 request/response schemas and ORM serializers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from models import (
    BulkTaxCampaign,
    BulkTaxRecipient,
    ChasingTicket,
    DeliveryStatus,
    MessageDirection,
    MessageTemplate,
    MessageType,
    PaymentStatus,
    ReportingFrequency,
    TemplateCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    WhatsAppMessageLog,
)
from services.templating import required_variables, template_variables


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── users & clients ──────────────────────────────────────────────────────────

NINE_DIGIT_PATTERN = r"^\d{9}$"


class UserOut(ORMModel):
    id: int
    full_name: str
    job_title: str
    email: str
    role: UserRole
    avatar_initials: str
    is_active: bool
    created_at: UTCDateTime


class UserIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    job_title: str = Field("", max_length=120)
    is_active: bool = True
    email: str = Field(min_length=5, max_length=180, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: UserRole = UserRole.WORKER
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    job_title: str | None = Field(None, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=6, max_length=128, description="manager-set new password (resets the user's sessions)")


class LoginUser(ORMModel):
    """Public, minimal user card for the login screen (no e-mail)."""

    id: int
    full_name: str
    job_title: str
    role: UserRole
    avatar_initials: str
    is_active: bool


class LoginRequest(BaseModel):
    user_id: int
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    expires_at: UTCDateTime
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class ActivityOut(BaseModel):
    id: int
    created_at: UTCDateTime
    user_id: int | None
    user_name: str | None
    user_role: UserRole | None
    action: str
    action_label: str
    description: str
    entity_type: str | None
    entity_id: int | None
    details: dict | None
    ip_address: str


class ActivityPage(BaseModel):
    total: int
    items: list[ActivityOut]
    actions: dict[str, str]


class ClientIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    company_name: str = ""
    tax_id: str = Field(pattern=NINE_DIGIT_PATTERN, description="ח.פ / ע.מ — exactly 9 digits")
    whatsapp_phone: str = Field(min_length=6, max_length=32)
    reporting_frequency: ReportingFrequency = ReportingFrequency.MONTHLY
    assigned_worker_id: int | None = None
    notes: str = ""
    is_active: bool = True


class ClientUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=160)
    company_name: str | None = None
    tax_id: str | None = Field(None, pattern=NINE_DIGIT_PATTERN)
    whatsapp_phone: str | None = Field(None, min_length=6, max_length=32)
    reporting_frequency: ReportingFrequency | None = None
    assigned_worker_id: int | None = None
    notes: str | None = None
    is_active: bool | None = None


class ClientOut(ORMModel):
    id: int
    full_name: str
    company_name: str
    tax_id: str
    whatsapp_phone: str
    reporting_frequency: ReportingFrequency
    assigned_worker_id: int | None
    assigned_worker_name: str | None = None
    notes: str
    is_active: bool
    created_at: UTCDateTime
    open_ticket_count: int = 0
    days_to_deadline: int = 0
    next_deadline: str = ""  # dd/mm/yyyy — always the 26th of a reporting month
    last_message_at: UTCDateTime | None = None
    last_message_preview: str | None = None


# ── templates ────────────────────────────────────────────────────────────────

class TemplateButton(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    action: str = Field(min_length=1, max_length=40)
    he: str = Field(min_length=1, max_length=60)


class TemplateOut(ORMModel):
    id: int
    slug: str
    category: TemplateCategory
    name_he: str
    body_he: str
    buttons_json: list[TemplateButton]
    requires_media_reply: bool
    is_system: bool
    updated_at: UTCDateTime
    variables: list[str] = []
    required_variables: list[str] = []


class TemplateUpdate(BaseModel):
    name_he: str | None = None
    body_he: str | None = None
    buttons_json: list[TemplateButton] | None = None
    requires_media_reply: bool | None = None


class PreviewRequest(BaseModel):
    client_id: int
    variables: dict[str, Any] = {}


class PreviewOut(BaseModel):
    direction: Literal["rtl", "ltr"]
    text: str
    buttons: list[dict]
    missing: list[str]


# ── messages & tickets ───────────────────────────────────────────────────────

class MessageOut(ORMModel):
    id: int
    ticket_id: int | None
    client_id: int
    direction: MessageDirection
    sender_name: str
    is_automated: bool = True
    sender_user_id: int | None = None
    message_type: MessageType
    content_text: str
    buttons_json: list[dict] | None
    media_url: str | None
    delivery_status: DeliveryStatus
    error_text: str | None = None
    created_at: UTCDateTime


class TicketOut(BaseModel):
    id: int
    ticket_ref: str
    client_id: int
    client_name: str
    company_name: str
    client_phone: str
    worker_id: int | None
    worker_name: str | None
    template_id: int
    template_slug: str
    template_name: str
    category: TemplateCategory
    requires_media_reply: bool
    status: TicketStatus
    priority: TicketPriority
    context_variables_json: dict
    reminder_count: int
    max_reminders: int
    last_contacted_at: UTCDateTime | None
    next_reminder_at: UTCDateTime | None
    resolved_at: UTCDateTime | None
    media_file_path: str | None
    ocr_validation_json: dict | None
    resolution_note: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class TicketDetail(TicketOut):
    messages: list[MessageOut] = []


class QuickSendRequest(BaseModel):
    client_id: int
    template_id: int | None = None
    template_slug: str | None = None
    context_variables: dict[str, Any] = {}
    priority: TicketPriority = TicketPriority.NORMAL


class QuickSendResponse(BaseModel):
    ticket: TicketOut
    message: MessageOut
    rendered_text: str
    buttons: list[dict]
    direction: Literal["rtl", "ltr"]
    elapsed_ms: float


class TicketNote(BaseModel):
    note: str = ""


class TicketReject(BaseModel):
    reason: str = Field(min_length=3, max_length=300, description="Hebrew reason, sent to the client on WhatsApp")


class OcrUpdate(BaseModel):
    invoice_number: str | None = None
    supplier_name: str | None = None
    business_id: str | None = None
    allocation_number: str | None = None
    invoice_date: str | None = None
    net_amount: float | None = None
    vat_amount: float | None = None
    total_amount: float | None = None


# ── inbound / simulator ──────────────────────────────────────────────────────

class InboundMessage(BaseModel):
    client_id: int | None = None
    from_phone: str | None = None
    type: Literal["button", "text"]
    button_id: str | None = None
    payload: str | None = None
    text: str | None = None
    ticket_id: int | None = None


class DemoReceiptRequest(BaseModel):
    client_id: int
    ticket_id: int | None = None
    scenario: Literal["clear", "blurry", "missing_number", "wrong_supplier", "bad_math", "missing_allocation",
                      "invalid_tax_id"] = "clear"


class InboundResult(BaseModel):
    ok: bool = True
    ticket: TicketOut | None = None
    action: str | None = None
    reply: str | None = None
    ocr: dict | None = None
    validation: dict | None = None
    elapsed_ms: float | None = None


# ── settings / dashboard / scheduler ─────────────────────────────────────────

class SettingsOut(BaseModel):
    id: int
    firm_name: str
    vat_rate: float
    allocation_number_threshold_nis: int
    reminder_interval_hours: int
    max_reminders: int
    vat_deadline_day: int  # read-only: fixed by law to the 26th
    auto_approve_verified: bool
    updated_at: UTCDateTime
    updated_by_user_id: int | None
    updated_by_name: str | None
    # read-only runtime info
    vision_provider: str
    whatsapp_live: bool
    timezone: str
    urgent_deadline_days: int
    scheduler: dict


class SettingsUpdate(BaseModel):
    firm_name: str | None = Field(None, min_length=2, max_length=200)
    vat_rate: float | None = Field(None, ge=0, le=50)
    allocation_number_threshold_nis: int | None = Field(None, ge=0, le=10_000_000)
    reminder_interval_hours: int | None = Field(None, ge=1, le=720)
    max_reminders: int | None = Field(None, ge=1, le=10)
    auto_approve_verified: bool | None = None


class KpiOut(BaseModel):
    active_waiting: int
    auto_reminders_this_month: int
    needs_clerk_review: int
    resolved_this_week: int
    escalated: int
    needs_correction: int
    estimated_hours_saved: float
    hours_saved_basis: str


class SchedulerResult(BaseModel):
    shifted_tickets: int | None = None
    actions: list[dict]
    summary: dict[str, int]


# ── campaigns ────────────────────────────────────────────────────────────────

class RecipientOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    ticket_id: int | None
    ticket_ref: str | None
    ticket_status: TicketStatus | None
    vat_amount: float
    income_tax_advance: float
    national_insurance: float
    total_due: float
    due_date: str
    payment_status: PaymentStatus
    updated_at: UTCDateTime


class CampaignOut(BaseModel):
    id: int
    title: str
    tax_period: str
    total_clients: int
    confirmed_count: int
    pending_count: int
    created_at: UTCDateTime
    stats: dict


class CampaignDetail(CampaignOut):
    recipients: list[RecipientOut] = []


class BulkUploadResult(BaseModel):
    campaign: CampaignDetail
    errors: list[str]
    created_clients: int
    sent: int


# ── serializers ──────────────────────────────────────────────────────────────

def user_out(u: User) -> UserOut:
    return UserOut.model_validate(u)


def template_out(tpl: MessageTemplate) -> TemplateOut:
    out = TemplateOut.model_validate(tpl)
    out.variables = template_variables(tpl)
    out.required_variables = required_variables(tpl)
    return out


def message_out(msg: WhatsAppMessageLog) -> MessageOut:
    return MessageOut.model_validate(msg)


def ticket_out(t: ChasingTicket) -> TicketOut:
    tpl = t.template
    return TicketOut(
        id=t.id,
        ticket_ref=t.ticket_ref,
        client_id=t.client_id,
        client_name=t.client.full_name,
        company_name=t.client.company_name,
        client_phone=t.client.whatsapp_phone,
        worker_id=t.worker_id,
        worker_name=t.worker.full_name if t.worker else None,
        template_id=t.template_id,
        template_slug=tpl.slug,
        template_name=tpl.name_he,
        category=tpl.category,
        requires_media_reply=tpl.requires_media_reply,
        status=t.status,
        priority=t.priority,
        context_variables_json=t.context_variables_json or {},
        reminder_count=t.reminder_count,
        max_reminders=t.max_reminders,
        last_contacted_at=t.last_contacted_at,
        next_reminder_at=t.next_reminder_at,
        resolved_at=t.resolved_at,
        media_file_path=t.media_file_path,
        ocr_validation_json=t.ocr_validation_json,
        resolution_note=t.resolution_note or "",
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def ticket_detail(t: ChasingTicket) -> TicketDetail:
    base = ticket_out(t).model_dump()
    return TicketDetail(**base, messages=[message_out(m) for m in t.messages])


def recipient_out(r: BulkTaxRecipient) -> RecipientOut:
    return RecipientOut(
        id=r.id,
        client_id=r.client_id,
        client_name=r.client.full_name,
        ticket_id=r.ticket_id,
        ticket_ref=r.ticket.ticket_ref if r.ticket else None,
        ticket_status=r.ticket.status if r.ticket else None,
        vat_amount=r.vat_amount,
        income_tax_advance=r.income_tax_advance,
        national_insurance=r.national_insurance,
        total_due=r.total_due,
        due_date=r.due_date,
        payment_status=r.payment_status,
        updated_at=r.updated_at,
    )


def campaign_out(c: BulkTaxCampaign, stats: dict, detail: bool = False) -> CampaignOut | CampaignDetail:
    data = dict(
        id=c.id, title=c.title, tax_period=c.tax_period, total_clients=c.total_clients,
        confirmed_count=c.confirmed_count, pending_count=c.pending_count, created_at=c.created_at, stats=stats,
    )
    if detail:
        return CampaignDetail(**data, recipients=[recipient_out(r) for r in c.recipients])
    return CampaignOut(**data)
