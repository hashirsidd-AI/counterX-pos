"""SQLite engine, sessions, and versioned migrations.

Single-computer offline default. Every connection enforces foreign keys.
Schema upgrades run through explicit migrations tracked by PRAGMA user_version,
so customer data survives application updates.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DB_PATH
from . import models

log = logging.getLogger("counterx.database")

SCHEMA_VERSION = 2

_SYNC_TABLES = (
    "sales", "sale_items", "payments", "products", "product_variants",
    "modifiers", "categories", "tax_rates", "customers", "suppliers",
    "stock_moves", "purchases", "purchase_items", "refunds", "shifts",
    "cash_moves", "expenses", "users", "audit_logs",
)

# version -> list of DDL statements (applied in order, inside one transaction each)
MIGRATIONS: dict[int, list[str]] = {
    # v1 is the baseline created by models.Base.metadata.create_all()
    # v2: stable sync UUIDs for offline-first cloud sync (new tables are
    # created automatically by create_all; only the columns need ALTERs)
    2: [f"ALTER TABLE {t} ADD COLUMN sync_uuid VARCHAR(36)" for t in _SYNC_TABLES],
}


def _backfill_sync_uuids(engine: Engine) -> None:
    """Give every pre-existing row a stable UUID so it can sync idempotently."""
    import uuid as _uuid

    with engine.begin() as conn:
        for table in _SYNC_TABLES:
            rows = conn.execute(
                text(f"SELECT id FROM {table} WHERE sync_uuid IS NULL")).fetchall()
            for (row_id,) in rows:
                conn.execute(
                    text(f"UPDATE {table} SET sync_uuid = :u WHERE id = :i"),
                    {"u": str(_uuid.uuid4()), "i": row_id})
            if rows:
                log.info("Backfilled %d sync_uuids in %s", len(rows), table)


def _on_connect(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("PRAGMA synchronous = NORMAL")
    cur.close()


def get_engine(db_path: Path | str = DB_PATH) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: wait (instead of failing fast) when another thread/process
    # briefly holds the write lock — the sync worker and the UI share the DB.
    engine = create_engine(f"sqlite:///{db_path}", future=True,
                           connect_args={"timeout": 30})
    event.listen(engine, "connect", _on_connect)
    return engine


def current_version(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("PRAGMA user_version")).scalar() or 0


def _set_version(engine: Engine, version: int) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"PRAGMA user_version = {version}"))


def _add_column_if_missing(conn, stmt: str) -> None:
    """Idempotent ADD COLUMN: skip when the column already exists.

    Makes migrations safe to re-run after an interrupted upgrade.
    """
    import re as _re

    m = _re.match(r"\s*ALTER TABLE (\w+) ADD COLUMN (\w+)",
                  stmt, _re.IGNORECASE)
    if not m:
        conn.execute(text(stmt))
        return
    table, column = m.group(1), m.group(2)
    existing = {r[1] for r in
                conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
    if column not in existing:
        conn.execute(text(stmt))
    else:
        log.info("Migration: column %s.%s already exists, skipping",
                 table, column)


def run_migrations(engine: Engine) -> int:
    """Apply pending migrations. Returns the schema version now in effect."""
    version = current_version(engine)
    pending = sorted(v for v in MIGRATIONS if v > version)
    for v in pending:
        log.info("Applying migration v%s", v)
        with engine.begin() as conn:
            for stmt in MIGRATIONS[v]:
                _add_column_if_missing(conn, stmt)
        if v >= 2:
            _backfill_sync_uuids(engine)
        _set_version(engine, v)
        version = v
    return version


def init_db(engine: Engine) -> None:
    """Create a fresh database (or bring an existing one up to date)."""
    models.Base.metadata.create_all(engine)
    if current_version(engine) == 0:
        _set_version(engine, SCHEMA_VERSION)
    run_migrations(engine)
    seed_defaults(engine)


def seed_defaults(engine: Engine) -> None:
    """Idempotent seed: default tax rate, settings keys, nothing customer-specific."""
    import uuid as _uuid

    from .models import TaxRate, Setting, SyncState

    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as s:
        if not s.query(SyncState).first():
            # Unique identity for this installation: generated once, never changes.
            # Used to scope cloud records so businesses never see each other's data.
            s.add(SyncState(installation_id=str(_uuid.uuid4())))
        if not s.query(TaxRate).filter_by(is_default=True).first():
            s.add(TaxRate(name="No Tax", rate_percent="0", is_default=True))
        defaults = {
            "business_name": "",
            "business_address": "",
            "business_city": "",
            "business_province": "",
            "business_phone": "",
            "tax_registration": "",
            "receipt_footer": "Thank you for your visit!",
            "currency_symbol": "Rs",
            "currency_code": "PKR",
            "auto_backup": "1",
            "backup_keep": "14",
        }
        for k, v in defaults.items():
            if not s.query(Setting).filter_by(key=k).first():
                s.add(Setting(key=k, value=v))
        s.commit()


@contextmanager
def session_scope(engine: Engine):
    """Transactional scope: commit on success, rollback on error."""
    SessionLocal = sessionmaker(bind=engine, future=True)
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
