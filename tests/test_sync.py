"""Offline-first sync tests. A FakeTransport stands in for Supabase;
no real cloud credentials are needed or used."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from counterx import database, models
from counterx.sync import FakeTransport, SyncService
from counterx.sync.service import enqueue_obj
from counterx.services import Cart, CartLine


@pytest.fixture()
def fake():
    return FakeTransport()


@pytest.fixture()
def sync(engine, fake):
    return SyncService(engine, transport_factory=lambda state: fake)


@pytest.fixture()
def enabled(engine, sync, db):
    # Commit fixture setup (owner creation etc.) first: production commits
    # every UI action, so the sync worker's own sessions must never meet
    # an unrelated open write transaction.
    db.commit()
    with database.session_scope(engine) as s:
        sync.configure(s, "http://fake.local", "fake-anon-key", True)
    return sync


def _product(db, svcs, owner):
    p = svcs["catalog"].create_product(
        owner, sku="SYNC-1", name="Sync Item", sell_price=Decimal("500"))
    svcs["inventory"].set_opening_stock(p.id, Decimal("20"), owner)
    return p


def _checkout(db, svcs, cashier, product):
    cart = Cart(lines=[CartLine(product_id=product.id, variant_id=None,
                                name=product.name, qty=Decimal("1"),
                                unit_price=product.sell_price,
                                tax_rate=Decimal("0"))])
    totals = svcs["sales"].cart_totals(cart)
    return svcs["sales"].checkout(
        cart, [{"method": "cash", "amount": totals["grand_total"],
                "received": totals["grand_total"]}], cashier)


# -- migration -----------------------------------------------------------------
def test_fresh_db_is_v2_with_installation_id(engine):
    assert database.current_version(engine) == 2
    with database.session_scope(engine) as s:
        state = s.query(models.SyncState).first()
        assert state and len(state.installation_id) == 36


def test_v1_to_v2_migration_backfills(tmp_path):
    # Simulate a genuine v1 database: the full v1 products table WITHOUT the
    # sync_uuid column (derived from the real DDL minus that column).
    # init_db must add the column and backfill existing rows.
    from sqlalchemy.schema import CreateTable

    eng = database.get_engine(tmp_path / "v1.db")
    ddl = str(CreateTable(models.Product.__table__).compile(eng))
    v1_ddl_lines = [ln for ln in ddl.splitlines()
                    if "sync_uuid" not in ln]
    v1_ddl = "\n".join(v1_ddl_lines).replace(",\n)", "\n)")
    with eng.begin() as c:
        c.execute(text("PRAGMA foreign_keys=OFF"))  # v1 stub: parent tables not built
        c.execute(text(v1_ddl))
        c.execute(text(
            "INSERT INTO products (sku, name, sell_price, cost_price, "
            "track_stock, is_active, created_at) "
            "VALUES ('OLD-1', 'Old Product', 100, 50, 1, 1, "
            "'2025-01-01 10:00:00')"))
        c.execute(text("PRAGMA user_version = 1"))
    database.init_db(eng)  # create_all skips products; migration v2 ALTERs it
    assert database.current_version(eng) == 2
    with database.session_scope(eng) as s:
        p = s.query(models.Product).filter_by(sku="OLD-1").first()
        assert p.sync_uuid and len(p.sync_uuid) == 36
        # and the row is fully readable through the ORM
        assert p.sell_price == 100


# -- outbox ----------------------------------------------------------------------
def test_checkout_enqueues_sync_rows(db, svcs, owner, cashier):
    product = _product(db, svcs, owner)
    sale = _checkout(db, svcs, cashier, product)
    rows = db.query(models.SyncQueue).all()
    entities = {r.entity for r in rows}
    assert {"sales", "sale_items", "payments"} <= entities
    sale_row = db.query(models.SyncQueue).filter_by(entity="sales").first()
    assert sale_row.sync_uuid == sale.sync_uuid
    assert sale_row.status == "pending"


def test_no_credentials_in_user_payload(db, auth, owner):
    row = db.query(models.SyncQueue).filter_by(entity="users").first()
    assert row is not None
    assert "password_hash" not in row.payload
    assert "password_salt" not in row.payload
    assert "password" not in row.payload.lower()


# -- upload ------------------------------------------------------------------------
def test_sync_once_uploads_and_clears(db, svcs, owner, cashier, enabled, fake):
    product = _product(db, svcs, owner)
    _checkout(db, svcs, cashier, product)
    db.commit()
    result = enabled.sync_once()
    assert result.failed == 0 and result.uploaded > 0
    with database.session_scope(enabled.engine) as s:
        assert s.query(models.SyncQueue).count() == 0  # confirmed -> removed
    assert len(fake.tables["sales"]) == 1
    cloud_sale = next(iter(fake.tables["sales"].values()))
    assert cloud_sale["installation_id"]  # scoped to this business


def test_failed_upload_retries_with_backoff(db, svcs, owner, cashier,
                                            enabled, fake):
    product = _product(db, svcs, owner)
    _checkout(db, svcs, cashier, product)
    db.commit()
    fake.fail_next = 99
    r1 = enabled.sync_once()
    assert r1.failed > 0
    with database.session_scope(enabled.engine) as s:
        row = s.query(models.SyncQueue).first()
        assert row.status == "failed" and row.attempts == 1
        assert row.next_retry_at > datetime.now()
        # not due yet -> skipped silently
    r2 = enabled.sync_once()
    assert r2.uploaded == 0  # backoff not elapsed, nothing attempted
    # make it due again, let it succeed
    fake.fail_next = 0
    with database.session_scope(enabled.engine) as s:
        s.query(models.SyncQueue).update(
            {models.SyncQueue.next_retry_at: datetime.now() - timedelta(seconds=1)})
    r3 = enabled.sync_once()
    assert r3.failed == 0 and r3.uploaded > 0


def test_idempotent_reupload_no_duplicates(db, svcs, owner, cashier,
                                           enabled, fake):
    product = _product(db, svcs, owner)
    sale = _checkout(db, svcs, cashier, product)
    db.commit()
    enabled.sync_once()
    assert len(fake.tables["sales"]) == 1
    # Re-enqueue the SAME sale (e.g. after an edit) and sync again.
    with database.session_scope(enabled.engine) as s:
        enqueue_obj(s, "sales", s.get(models.Sale, sale.id))
    enabled.sync_once()
    assert len(fake.tables["sales"]) == 1  # still one row


def test_immutable_first_write_wins(db, svcs, owner, cashier, enabled, fake):
    product = _product(db, svcs, owner)
    sale = _checkout(db, svcs, cashier, product)
    db.commit()
    enabled.sync_once()
    # Tamper the cloud copy, then re-upload the same sale.
    key = next(iter(fake.tables["sales"]))
    fake.tables["sales"][key] = dict(fake.tables["sales"][key],
                                     grand_total=999999.0)
    with database.session_scope(enabled.engine) as s:
        enqueue_obj(s, "sales", s.get(models.Sale, sale.id))
    enabled.sync_once()
    assert fake.tables["sales"][key]["grand_total"] == 999999.0  # not overwritten


def test_mutable_last_write_wins(db, svcs, owner, enabled, fake):
    p = svcs["catalog"].create_product(owner, sku="MUT-1", name="Mutable",
                                       sell_price=Decimal("100"))
    db.commit()
    enabled.sync_once()
    key = next(iter(fake.tables["products"]))
    assert fake.tables["products"][key]["sell_price"] == 100.0
    svcs["catalog"].update_product(p.id, owner, sell_price=Decimal("150"))
    db.commit()  # production commits each UI action; worker sees it after
    enabled.sync_once()
    assert fake.tables["products"][key]["sell_price"] == 150.0


def test_billing_never_blocked_by_sync_failure(db, svcs, owner, cashier,
                                               enabled, fake):
    product = _product(db, svcs, owner)
    db.commit()
    fake.fail_next = 99
    # sync_once must never raise, even when the cloud is down
    result = enabled.sync_once()
    assert result.failed >= 0
    # and billing still works fine offline
    sale = _checkout(db, svcs, cashier, product)
    assert sale.status == "completed"


def test_sync_skipped_when_disabled(engine, fake):
    svc = SyncService(engine, transport_factory=lambda state: fake)
    result = svc.sync_once()
    assert result.skipped is True
    assert fake.calls == []


# -- recovery -----------------------------------------------------------------------
def test_recovery_code_flow(auth, owner):
    code = auth.set_recovery_code(owner)
    assert code.startswith("CXRC-")
    assert auth.verify_recovery_code(code) is True
    assert auth.verify_recovery_code("CXRC-WRONG-WRONG") is False
    auth.recover_owner_password(code, "brandnew99")
    auth.authenticate("owner", "brandnew99")


def test_recovery_code_hash_not_plaintext(db, auth, owner):
    auth.set_recovery_code(owner)
    row = db.query(models.Setting).filter_by(key="recovery_code_hash").first()
    assert row.value and not row.value.startswith("CXRC-")
    assert len(row.value) == 64  # sha256 hex
