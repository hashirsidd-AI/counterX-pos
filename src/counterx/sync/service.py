"""Offline-first sync engine.

- `enqueue()` writes to the outbox in the SAME transaction as the business
  mutation: a crash between "sale saved" and "sale queued" is impossible.
- The background worker uploads oldest-first. Billing NEVER waits for it.
- A row is deleted from the queue only after the cloud confirms the write.
- Failed rows retry with exponential backoff; nothing is ever deleted
  locally because an upload failed.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..database import session_scope
from .serializers import ENTITY_TABLES, IMMUTABLE_ENTITIES, serialize
from .transport import (CloudTransport, FakeTransport, SupabaseAuth,
                        SupabaseTransport, SyncError, _AlreadyRegistered)

log = logging.getLogger("counterx.sync")

BATCH_LIMIT = 200


@dataclass
class SyncResult:
    uploaded: int = 0
    failed: int = 0
    skipped: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)


def _backoff(attempts: int) -> timedelta:
    seconds = min(60 * (2 ** max(0, attempts - 1)), 3600)
    return timedelta(seconds=seconds)


def enqueue_obj(s: Session, entity: str, obj, operation: str = "upsert") -> None:
    """Queue one object for cloud upload.

    Call inside the business mutation's transaction, after flush: the queue
    row commits atomically with the business data (outbox pattern).
    """
    from .serializers import ENTITY_TABLES, serialize

    if entity not in ENTITY_TABLES:
        raise ValueError(f"Unknown sync entity: {entity}")
    state = s.query(models.SyncState).first()
    installation_id = state.installation_id if state else "unknown"
    if not obj.sync_uuid:
        obj.sync_uuid = str(_uuid.uuid4())
        s.flush()
    payload = serialize(entity, obj, installation_id)
    # Link child rows to their parent sale's stable UUID for cloud-side joins.
    if entity in ("sale_items", "payments") and getattr(obj, "sale_id", None):
        parent = s.get(models.Sale, obj.sale_id)
        if parent is not None:
            if not parent.sync_uuid:
                parent.sync_uuid = str(_uuid.uuid4())
                s.flush()
            payload["sale_sync_uuid"] = parent.sync_uuid
    row = s.query(models.SyncQueue).filter_by(
        entity=entity, sync_uuid=obj.sync_uuid).first()
    blob = json.dumps(payload, default=str)
    if row is None:
        s.add(models.SyncQueue(entity=entity, entity_id=obj.id,
                                sync_uuid=obj.sync_uuid, operation=operation,
                                payload=blob))
    else:
        row.payload = blob
        row.operation = operation
        row.status = "pending"
        row.attempts = 0
        row.last_error = ""
        row.next_retry_at = None
    s.flush()


class SyncService:
    def __init__(self, engine, transport_factory=None) -> None:
        """
        transport_factory: callable(sync_state) -> CloudTransport | None.
        Defaults to building a SupabaseTransport from the stored config.
        Tests inject a FakeTransport.
        """
        self.engine = engine
        self._transport_factory = transport_factory or self._default_transport
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()

    # -- configuration ---------------------------------------------------------
    def get_state(self, s: Session) -> models.SyncState:
        state = s.query(models.SyncState).first()
        if not state:
            state = models.SyncState(installation_id=str(_uuid.uuid4()))
            s.add(state)
            s.flush()
        return state

    def configure(self, s: Session, url: str, anon_key: str,
                  enabled: bool) -> models.SyncState:
        state = self.get_state(s)
        state.cloud_url = url.strip().rstrip("/")
        state.anon_key = anon_key.strip()
        state.sync_enabled = enabled
        s.flush()
        return state

    def connect_cloud_account(self, s: Session) -> dict:
        """Create (or sign into) this installation's Supabase Auth user."""
        state = self.get_state(s)
        if not state.cloud_url or not state.anon_key:
            raise SyncError("Configure the Supabase URL and anon key first")
        auth = SupabaseAuth(state.cloud_url, state.anon_key)
        if not state.cloud_email:
            state.cloud_email = f"{state.installation_id}@counterx.local"
            state.cloud_password = secrets.token_urlsafe(24)
        try:
            auth.sign_up(state.cloud_email, state.cloud_password)
        except _AlreadyRegistered:
            pass  # user exists -> sign in below
        tokens = auth.sign_in(state.cloud_email, state.cloud_password)
        self._store_tokens(state, tokens)
        s.flush()
        return {"email": state.cloud_email}

    def _store_tokens(self, state: models.SyncState, tokens: dict) -> None:
        state.access_token = tokens.get("access_token", "")
        state.refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)
        state.token_expires_at = datetime.now() + timedelta(
            seconds=max(60, expires_in - 60))

    def _token_provider(self):
        def _get() -> str:
            with session_scope(self.engine) as s:
                state = self.get_state(s)
                exp = state.token_expires_at
                if (not state.access_token or not exp
                        or exp <= datetime.now() + timedelta(seconds=30)):
                    auth = SupabaseAuth(state.cloud_url, state.anon_key)
                    if state.refresh_token:
                        try:
                            tokens = auth.refresh(state.refresh_token)
                        except SyncError:
                            tokens = auth.sign_in(state.cloud_email,
                                                  state.cloud_password)
                    else:
                        tokens = auth.sign_in(state.cloud_email,
                                              state.cloud_password)
                    self._store_tokens(state, tokens)
                return state.access_token
        return _get

    def _default_transport(self, state: models.SyncState):
        if not state.sync_enabled or not state.cloud_url or not state.anon_key:
            return None
        return SupabaseTransport(state.cloud_url, state.anon_key,
                                 self._token_provider())

    # -- outbox ------------------------------------------------------------------
    def enqueue(self, s: Session, entity: str, obj,
                operation: str = "upsert") -> None:
        """Queue one object for upload. Call inside the mutation's transaction."""
        enqueue_obj(s, entity, obj, operation)

    def pending_count(self, s: Session) -> int:
        return s.query(models.SyncQueue).filter(
            models.SyncQueue.status.in_(("pending", "failed"))).count()

    def failed_count(self, s: Session) -> int:
        return s.query(models.SyncQueue).filter_by(status="failed").count()

    def status(self, s: Session) -> dict:
        state = self.get_state(s)
        return {
            "enabled": state.sync_enabled,
            "configured": bool(state.cloud_url and state.anon_key),
            "installation_id": state.installation_id,
            "pending": self.pending_count(s),
            "failed": self.failed_count(s),
            "last_sync_at": state.last_sync_at,
            "last_error": state.last_error,
        }

    # -- upload --------------------------------------------------------------------
    def sync_once(self) -> SyncResult:
        """Upload all due rows. Safe to call from any thread. Never raises."""
        try:
            with session_scope(self.engine) as s:
                state = self.get_state(s)
                if not state.sync_enabled:
                    return SyncResult(skipped=True, message="Sync disabled")
                # Recover rows left 'inflight' by a crashed/interrupted run.
                s.query(models.SyncQueue).filter_by(status="inflight").update(
                    {"status": "pending"}, synchronize_session=False)
                transport = self._transport_factory(state)
                if transport is None:
                    return SyncResult(skipped=True,
                                      message="Sync not configured")
                now = datetime.now()
                due = (s.query(models.SyncQueue)
                       .filter(models.SyncQueue.status.in_(("pending", "failed")),
                               (models.SyncQueue.next_retry_at.is_(None) |
                                (models.SyncQueue.next_retry_at <= now)))
                       .order_by(models.SyncQueue.created_at)
                       .limit(BATCH_LIMIT).all())
                if not due:
                    state.last_sync_at = now
                    return SyncResult(message="Nothing to sync")
                for row in due:
                    row.status = "inflight"
                s.flush()
                # Snapshot plain values NOW: ORM objects detach when the
                # session closes, and must not be touched afterwards.
                items = [(r.id, r.entity, r.sync_uuid, json.loads(r.payload))
                         for r in due]
        except Exception as e:  # noqa: BLE001
            log.exception("sync_once setup failed")
            return SyncResult(failed=1, errors=[str(e)])

        # Upload outside the lock-held session; rows are marked inflight.
        by_entity: dict[str, list[tuple[int, dict]]] = {}
        for qid, entity, sync_uuid, payload in items:
            by_entity.setdefault(entity, []).append((qid, payload))

        uploaded, failed, errors = 0, 0, []
        ok_ids: list[int] = []
        fail_updates: list[tuple[int, str]] = []
        for entity, rows in by_entity.items():
            table = ENTITY_TABLES[entity]
            merge = entity not in IMMUTABLE_ENTITIES
            try:
                transport.upsert(table, [p for _, p in rows],
                                 on_conflict="sync_uuid", merge=merge)
                for qid, _ in rows:
                    ok_ids.append(qid)
                    uploaded += 1
            except SyncError as e:
                log.warning("sync upload failed for %s: %s", entity, e)
                for qid, _ in rows:
                    fail_updates.append((qid, str(e)))
                    failed += 1
                    errors.append(f"{entity}: {e}")
            except Exception as e:  # noqa: BLE001 - never crash the worker
                log.exception("unexpected sync error")
                for qid, _ in rows:
                    fail_updates.append((qid, f"Unexpected: {e}"))
                    failed += 1

        try:
            with session_scope(self.engine) as s:
                state = self.get_state(s)
                if ok_ids:
                    s.query(models.SyncQueue).filter(
                        models.SyncQueue.id.in_(ok_ids)).delete(
                        synchronize_session=False)
                for qid, err in fail_updates:
                    row = s.get(models.SyncQueue, qid)
                    if row:
                        row.status = "failed"
                        row.attempts += 1
                        row.last_error = err[:500]
                        row.next_retry_at = datetime.now() + _backoff(row.attempts)
                if failed == 0:
                    state.last_sync_at = datetime.now()
                    state.last_error = ""
                else:
                    state.last_error = errors[0][:500] if errors else ""
        except Exception:  # noqa: BLE001
            log.exception("sync_once finalize failed")
        return SyncResult(uploaded=uploaded, failed=failed,
                          errors=errors[:5])

    # -- background worker ---------------------------------------------------------
    def start_worker(self, interval_seconds: int = 60) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()

        def _loop():
            while not self._stop.is_set():
                try:
                    self.sync_once()
                except Exception:  # noqa: BLE001 - worker must never die
                    log.exception("sync worker iteration failed")
                self._wake.wait(interval_seconds)
                self._wake.clear()

        self._worker = threading.Thread(target=_loop, name="counterx-sync",
                                        daemon=True)
        self._worker.start()
        log.info("sync worker started")

    def request_sync(self) -> None:
        """Trigger an immediate upload cycle (manual 'Sync Now')."""
        self._wake.set()

    def stop_worker(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=10)
