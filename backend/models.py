"""SQLAlchemy 2.0 ORM models for AccountFlow AI."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from services.clock import utcnow


def _enum(enum_cls: type[enum.Enum]) -> SAEnum:
    # Stored as VARCHAR + CHECK so the schema is portable between SQLite and PostgreSQL.
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class UserRole(str, enum.Enum):
    MANAGER = "MANAGER"
    WORKER = "WORKER"


class Language(str, enum.Enum):
    AR = "ar"
    HE = "he"
    EN = "en"


class ReportingFrequency(str, enum.Enum):
    MONTHLY = "MONTHLY"  # דיווח חד חודשי
    BIMONTHLY = "BIMONTHLY"  # דיווח דו חודשי


class TemplateCategory(str, enum.Enum):
    MISSING_INVOICE = "MISSING_INVOICE"
    MISSING_DETAIL = "MISSING_DETAIL"
    UNIDENTIFIED_CHARGE = "UNIDENTIFIED_CHARGE"
    TAX_READY = "TAX_READY"
    MONTHLY_FOLDER = "MONTHLY_FOLDER"


class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    WAITING_FOR_CLIENT = "WAITING_FOR_CLIENT"
    SNOOZED_TONIGHT = "SNOOZED_TONIGHT"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    NEEDS_CLERK_REVIEW = "NEEDS_CLERK_REVIEW"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class TicketPriority(str, enum.Enum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT_DEADLINE = "URGENT_DEADLINE"


class MessageDirection(str, enum.Enum):
    OUTBOUND = "OUTBOUND"
    INBOUND = "INBOUND"


class MessageType(str, enum.Enum):
    TEMPLATE = "TEMPLATE"
    TEXT = "TEXT"
    BUTTON_REPLY = "BUTTON_REPLY"
    IMAGE_UPLOAD = "IMAGE_UPLOAD"
    AUTO_REMINDER = "AUTO_REMINDER"
    OCR_FEEDBACK = "OCR_FEEDBACK"


class DeliveryStatus(str, enum.Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"


class PaymentStatus(str, enum.Enum):
    SENT = "SENT"
    VIEWED = "VIEWED"
    CONFIRMED_PAID = "CONFIRMED_PAID"
    QUESTION_ASKED = "QUESTION_ASKED"


class User(Base):
    """Office staff: managers administer clients & settings, workers run the chasing desk."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    job_title: Mapped[str] = mapped_column(String(120), default="")  # e.g. "פקיד הנה״ח" — shown under the name
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.WORKER, index=True)
    avatar_initials: Mapped[str] = mapped_column(String(4), default="")
    # PBKDF2-SHA256 hash (services/security.py); never returned by the API
    password_hash: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    clients: Mapped[list[Client]] = relationship(back_populates="assigned_worker")

    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.MANAGER


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_active_name", "is_active", "full_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160))
    company_name: Mapped[str] = mapped_column(String(200), default="")
    tax_id: Mapped[str] = mapped_column(String(9), index=True, default="")  # 9-digit ח.פ / ע.מ
    whatsapp_phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # Legacy column kept for existing databases; WhatsApp contact is Hebrew-only, so it is always "he".
    preferred_language: Mapped[Language] = mapped_column(_enum(Language), default=Language.HE)
    # VAT deadline is always the 26th; frequency decides which months have one.
    reporting_frequency: Mapped[ReportingFrequency] = mapped_column(_enum(ReportingFrequency), default=ReportingFrequency.MONTHLY)
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    assigned_worker: Mapped[User | None] = relationship(back_populates="clients")
    tickets: Mapped[list[ChasingTicket]] = relationship(back_populates="client")


class SystemSettings(Base):
    """Single-row office configuration, editable by managers from the Settings tab."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firm_name: Mapped[str] = mapped_column(String(200), default="כהן ושות׳ - רואי חשבון")
    vat_rate: Mapped[float] = mapped_column(Float, default=18.0)  # percent
    allocation_number_threshold_nis: Mapped[int] = mapped_column(Integer, default=10000)
    reminder_interval_hours: Mapped[int] = mapped_column(Integer, default=48)
    max_reminders: Mapped[int] = mapped_column(Integer, default=3)
    auto_approve_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    updated_by: Mapped[User | None] = relationship()


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category: Mapped[TemplateCategory] = mapped_column(_enum(TemplateCategory))
    name_he: Mapped[str] = mapped_column(String(160))
    body_he: Mapped[str] = mapped_column(Text)
    # [{"id": "upload_photo", "action": "REQUEST_MEDIA", "he": "..."}]
    buttons_json: Mapped[list] = mapped_column(JSON, default=list)
    requires_media_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ChasingTicket(Base):
    __tablename__ = "chasing_tickets"
    __table_args__ = (
        Index("ix_tickets_status_next", "status", "next_reminder_at"),
        Index("ix_tickets_client_status", "client_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("message_templates.id"), index=True)
    status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus), default=TicketStatus.OPEN, index=True)
    priority: Mapped[TicketPriority] = mapped_column(_enum(TicketPriority), default=TicketPriority.NORMAL)
    context_variables_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    max_reminders: Mapped[int] = mapped_column(Integer, default=3)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    media_file_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ocr_validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    client: Mapped[Client] = relationship(back_populates="tickets")
    worker: Mapped[User | None] = relationship()
    template: Mapped[MessageTemplate] = relationship()
    messages: Mapped[list[WhatsAppMessageLog]] = relationship(
        back_populates="ticket", order_by="WhatsAppMessageLog.created_at"
    )


class WhatsAppMessageLog(Base):
    __tablename__ = "whatsapp_message_logs"
    __table_args__ = (Index("ix_msg_client_created", "client_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("chasing_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(_enum(MessageDirection))
    sender_name: Mapped[str] = mapped_column(String(160))
    # True for bot / template / reminder / Vision AI messages; False for a worker's manual message
    # (and for inbound client messages). The customer sees "הודעה אוטומטית" or "הודעה מאת <worker>".
    is_automated: Mapped[bool] = mapped_column(Boolean, default=True)
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    message_type: Mapped[MessageType] = mapped_column(_enum(MessageType), index=True)
    content_text: Mapped[str] = mapped_column(Text, default="")
    buttons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(_enum(DeliveryStatus), default=DeliveryStatus.SENT)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    ticket: Mapped[ChasingTicket | None] = relationship(back_populates="messages")
    client: Mapped[Client] = relationship()
    sender_user: Mapped[User | None] = relationship()


class BulkTaxCampaign(Base):
    __tablename__ = "bulk_tax_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    tax_period: Mapped[str] = mapped_column(String(40))
    total_clients: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recipients: Mapped[list[BulkTaxRecipient]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="BulkTaxRecipient.id"
    )


class BulkTaxRecipient(Base):
    __tablename__ = "bulk_tax_recipients"
    __table_args__ = (Index("ix_recipient_campaign_status", "campaign_id", "payment_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("bulk_tax_campaigns.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("chasing_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    vat_amount: Mapped[float] = mapped_column(Float, default=0.0)
    income_tax_advance: Mapped[float] = mapped_column(Float, default=0.0)
    national_insurance: Mapped[float] = mapped_column(Float, default=0.0)
    total_due: Mapped[float] = mapped_column(Float, default=0.0)
    due_date: Mapped[str] = mapped_column(String(20))
    payment_status: Mapped[PaymentStatus] = mapped_column(_enum(PaymentStatus), default=PaymentStatus.SENT)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    campaign: Mapped[BulkTaxCampaign] = relationship(back_populates="recipients")
    client: Mapped[Client] = relationship()
    ticket: Mapped[ChasingTicket | None] = relationship()


class UserSession(Base):
    """A logged-in browser. Only the SHA-256 digest of the bearer token is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")

    user: Mapped[User] = relationship()


class ActivityLog(Base):
    """Audit trail of who did what in the office dashboard. Readable by managers only."""

    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User | None] = relationship()


class LoginFailure(Base):
    """Wrong-password attempts, kept only to enforce the temporary lockout.

    Not part of the activity log (which records operational events only). Rows for a user are
    deleted on their next successful login, and rows older than the lockout window are purged.
    """

    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
