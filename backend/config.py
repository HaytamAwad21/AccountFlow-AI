"""Runtime configuration for AccountFlow AI.

Every value can be overridden with an environment variable of the same name
(case-insensitive) or through a `.env` file in the repo root or `/backend`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR.parent / ".env"), str(BASE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AccountFlow AI"
    # Initial values for the `system_settings` row; managers change them from the Settings tab.
    firm_name: str = "כהן ושות׳ - רואי חשבון"

    # SQLite by default; set DATABASE_URL=postgresql+psycopg://user:pass@host/db for production.
    database_url: str = f"sqlite:///{(BASE_DIR / 'accountflow.db').as_posix()}"
    seed_on_startup: bool = True

    timezone: str = "Asia/Jerusalem"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Nagging engine
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    reminder_interval_hours: int = 48
    urgent_reminder_interval_hours: int = 24
    urgent_deadline_days: int = 3
    default_max_reminders: int = 3
    snooze_hour: int = 20

    # Accounting rules (initial values; live values live in `system_settings`)
    vat_rate: float = 0.18
    allocation_number_threshold_nis: int = 10000
    auto_approve_verified: bool = False
    default_payment_link: str = "https://www.gov.il/he/departments/israel_tax_authority"

    # Vision AI: auto | openai | gemini | local
    vision_provider: str = "auto"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    vision_timeout_seconds: float = 30.0
    blur_threshold: float = 60.0

    # WhatsApp Cloud API (Meta). Leave empty to run in simulator-only mode.
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "accountflow-verify"
    # Meta App Secret (App settings ▸ Basic). Cloud API webhook posts must carry a matching
    # X-Hub-Signature-256 header; while this is empty, every Meta webhook post is refused.
    whatsapp_app_secret: str = ""
    # Meta-approved template sent when the client's 24-hour customer-service window is closed: the
    # firm's messages are held until the client taps it or writes. Body variables: {{1}} client name,
    # {{2}} firm name; one quick-reply button. Empty: messages are held until the client writes.
    whatsapp_reengage_template: str = ""
    whatsapp_template_language: str = "he"
    whatsapp_api_version: str = "v21.0"
    default_country_code: str = "972"

    upload_dir: Path = BASE_DIR / "uploads"

    # Login & sessions
    session_hours: int = 12
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    # Given to existing users that have no password yet (e.g. after upgrading an older database).
    initial_user_password: str = "ChangeMe123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def whatsapp_live(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
