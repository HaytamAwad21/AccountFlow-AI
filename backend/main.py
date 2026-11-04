"""AccountFlow AI — FastAPI application entrypoint.

    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import SessionLocal, init_db
from routers import activity, auth, campaigns, core, files, scheduler as scheduler_router, tickets, webhook, whatsapp
from seed import ensure_passwords, install_office_defaults, seed_if_empty, upgrade_templates
from services.events import broker
from services.activity import cleanup_legacy_activity, describe_device, request_device
from services.history import hebrewize_message_history
from services.no_emoji import purge_emojis_from_db
from services.scheduler import start_scheduler, stop_scheduler
from services.ticket_engine import EngineError, MissingVariablesError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("accountflow")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.seed_on_startup:
        result = seed_if_empty()
        if result.get("seeded"):
            log.info("Seeded demo data: %s", result)
    elif install_office_defaults():
        log.info("New office: message templates installed; create the first manager on the setup screen.")
    with SessionLocal() as db:
        hebrewize_message_history(db)  # WhatsApp chat is Hebrew-only, also for older history
        purge_emojis_from_db(db)  # strict no-emoji policy, also for templates and history from older releases
        upgrade_templates(db)  # after the purge: an old default with emojis matches only once they are gone
        cleaned = cleanup_legacy_activity(db)  # failed logins / simulator demos are not activity
        if cleaned:
            log.warning("Activity log cleanup: %d legacy rows removed or renamed", cleaned)
    fixed = ensure_passwords()
    if fixed:
        log.warning("Initial passwords set for users without one: %s (see README › Demo logins)", ", ".join(fixed))
    broker.bind_loop(asyncio.get_running_loop())
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Automated client-chasing, invoice collection and tax notifications for accounting firms.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def remember_device(request: Request, call_next):
    """Lets the activity log name the device ("Chrome · Windows") of whoever made this request."""
    token = request_device.set(describe_device(request.headers.get("user-agent")))
    try:
        return await call_next(request)
    finally:
        request_device.reset(token)


@app.exception_handler(EngineError)
async def engine_error_handler(_request: Request, exc: EngineError):
    body = {"detail": str(exc)}
    if isinstance(exc, MissingVariablesError):
        body["missing"] = exc.missing
    return JSONResponse(status_code=exc.status_code, content=body)


for r in (auth.router, core.router, tickets.router, webhook.router, whatsapp.router, scheduler_router.router, campaigns.router,
          activity.router, files.router):
    app.include_router(r)
