"""Database engine and session factory (SQLite by default, PostgreSQL via DATABASE_URL)."""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {},
    pool_pre_ping=True,
)

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _schema_outdated() -> bool:
    """True when the DB was created by an older AccountFlow release (before users / system_settings)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not tables:
        return False
    if "clerk_users" in tables or "system_settings" not in tables:
        return True
    client_cols = {c["name"] for c in inspector.get_columns("clients")} if "clients" in tables else set()
    if client_cols and ("full_name" not in client_cols or "reporting_frequency" not in client_cols
                        or "monthly_deadline_day" in client_cols):
        return True
    settings_cols = {c["name"] for c in inspector.get_columns("system_settings")}
    return "default_deadline_day" in settings_cols


def _add_missing_columns() -> None:
    """In-place upgrades that keep existing data (new tables are created by create_all)."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_hash" not in user_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(256) NOT NULL DEFAULT ''"))
            logging.getLogger("accountflow").warning("Added users.password_hash; existing users get an initial password on startup.")
        if "job_title" not in user_cols:
            # Older releases stored "שם - תפקיד" in full_name: split it into full_name + job_title.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR(120) NOT NULL DEFAULT ''"))
                for user_id, full_name in conn.execute(text("SELECT id, full_name FROM users")).all():
                    name, sep, title = (full_name or "").partition(" - ")
                    if sep:
                        conn.execute(text("UPDATE users SET full_name = :n, job_title = :t WHERE id = :i"),
                                     {"n": name.strip(), "t": title.strip(), "i": user_id})
            logging.getLogger("accountflow").warning("Added users.job_title and split existing 'name - title' values.")
    if "whatsapp_message_logs" in inspector.get_table_names():
        msg_cols = {c["name"] for c in inspector.get_columns("whatsapp_message_logs")}
        if "is_automated" not in msg_cols:
            # Every message stored so far was sent by the bot; inbound client messages are not automated.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE whatsapp_message_logs ADD COLUMN is_automated BOOLEAN NOT NULL DEFAULT TRUE"))
                conn.execute(text("UPDATE whatsapp_message_logs SET is_automated = FALSE WHERE direction = 'INBOUND'"))
            logging.getLogger("accountflow").warning("Added whatsapp_message_logs.is_automated.")
        if "sender_user_id" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE whatsapp_message_logs ADD COLUMN sender_user_id INTEGER "
                                  "REFERENCES users(id) ON DELETE SET NULL"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_message_logs_sender_user_id "
                                  "ON whatsapp_message_logs (sender_user_id)"))
            logging.getLogger("accountflow").warning("Added whatsapp_message_logs.sender_user_id.")
        if "awaiting_window" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE whatsapp_message_logs ADD COLUMN awaiting_window BOOLEAN NOT NULL DEFAULT FALSE"))
            logging.getLogger("accountflow").warning("Added whatsapp_message_logs.awaiting_window.")


def init_db() -> None:
    import models  # noqa: F401  (registers tables on Base.metadata)

    _add_missing_columns()
    if _schema_outdated():
        logging.getLogger("accountflow").warning("Outdated database schema detected: rebuilding tables and reseeding demo data.")
        legacy = MetaData()
        legacy.reflect(bind=engine)
        legacy.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
