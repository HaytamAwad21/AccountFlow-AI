"""Real-time event broker (Server-Sent Events) with commit-aware publishing.

Engine code calls `queue_event(db, {...})` / `queue_after_commit(db, fn)`; nothing is
published until the surrounding transaction commits, so the UI never refetches stale rows.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

log = logging.getLogger("accountflow.events")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="af-outbound")


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    @staticmethod
    def _put(q: asyncio.Queue, event: dict) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def publish(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            loop.call_soon_threadsafe(self._put, q, event)


broker = EventBroker()


def queue_event(db: Session, event: dict) -> None:
    db.info.setdefault("pending_events", []).append(event)


def queue_after_commit(db: Session, fn: Callable[[], None]) -> None:
    db.info.setdefault("pending_jobs", []).append(fn)


@sa_event.listens_for(Session, "after_commit")
def _flush_after_commit(session: Session) -> None:
    events = session.info.pop("pending_events", [])
    jobs = session.info.pop("pending_jobs", [])
    seen: set[tuple] = set()
    for ev in events:
        key = tuple(sorted((k, str(v)) for k, v in ev.items()))
        if key in seen:
            continue
        seen.add(key)
        broker.publish(ev)
    for job in jobs:
        _executor.submit(_run_job, job)


@sa_event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    session.info.pop("pending_events", None)
    session.info.pop("pending_jobs", None)


def _run_job(job: Callable[[], None]) -> None:
    try:
        job()
    except Exception:  # pragma: no cover - logged for operators
        log.exception("Background job failed")
