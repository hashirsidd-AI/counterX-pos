"""SQLAlchemy data model. Money is Numeric(12,2); app code uses Decimal."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
MONEY = Numeric(12, 2)


def _now():
    return datetime.now()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    password_salt = Column(String(64), nullable=False)
    full_name = Column(String(128), default="")
    role = Column(String(16), nullable=False, default="cashier")  # owner/manager/cashier
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class UserPermissionOverride(Base):
    """Per-user grant/revoke on top of the role matrix."""
    __tablename__ = "user_permission_overrides"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String(32), nullable=False)
    granted = Column(Boolean, nullable=False)  # True=grant, False=revoke
    __table_args__ = (UniqueConstraint("user_id", "permission"),)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    name = Column(String(128), nullable=False)
    name_ur = Column(String(128), default="")
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)


class TaxRate(Base):
    __tablename__ = "tax_rates"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    name = Column(String(64), nullable=False)
    rate_percent = Column(MONEY, nullable=False, default=0)
    is_default = Column(Boolean, default=False, nullable=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    sku = Column(String(64), unique=True, nullable=False)
    barcode = Column(String(64), unique=True, nullable=True)
    name = Column(String(160), nullable=False)
    name_ur = Column(String(160), default="")
    description = Column(Text, default="")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    cost_price = Column(MONEY, nullable=False, default=0)
    sell_price = Column(MONEY, nullable=False, default=0)
    tax_rate_id = Column(Integer, ForeignKey("tax_rates.id"), nullable=True)
    track_stock = Column(Boolean, default=True, nullable=False)
    min_stock = Column(Numeric(12, 3), default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    image_path = Column(String(256), default="")
    created_at = Column(DateTime, default=_now, nullable=False)

    category = relationship("Category")


class ProductVariant(Base):
    """Sizes / variants, e.g. Small / Regular / Large."""
    __tablename__ = "product_variants"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(64), nullable=False)
    price_delta = Column(MONEY, nullable=False, default=0)  # added to sell_price


class Modifier(Base):
    __tablename__ = "modifiers"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    name = Column(String(128), nullable=False)
    price = Column(MONEY, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)


class ProductModifier(Base):
    __tablename__ = "product_modifiers"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    modifier_id = Column(Integer, ForeignKey("modifiers.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("product_id", "modifier_id"),)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), default="")
    address = Column(String(256), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), default="")
    address = Column(String(256), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now, nullable=False)


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    invoice_no = Column(Integer, unique=True, nullable=False)
    token_no = Column(String(32), nullable=False)
    client_ref = Column(String(64), unique=True, nullable=False)  # idempotency key
    business_day = Column(String(10), nullable=False)  # YYYY-MM-DD
    sale_type = Column(String(16), nullable=False, default="takeaway")
    table_no = Column(String(32), default="")
    waiter = Column(String(64), default="")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # cashier
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    subtotal = Column(MONEY, nullable=False, default=0)
    discount_total = Column(MONEY, nullable=False, default=0)
    tax_total = Column(MONEY, nullable=False, default=0)
    service_charge = Column(MONEY, nullable=False, default=0)
    delivery_charge = Column(MONEY, nullable=False, default=0)
    grand_total = Column(MONEY, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="completed")  # completed/voided/refunded/held
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now, nullable=False)

    items = relationship("SaleItem", cascade="all, delete-orphan", backref="sale")
    payments = relationship("Payment", cascade="all, delete-orphan", backref="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    name_snapshot = Column(String(200), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(MONEY, nullable=False)
    item_discount = Column(MONEY, nullable=False, default=0)
    tax_amount = Column(MONEY, nullable=False, default=0)
    line_total = Column(MONEY, nullable=False)


class SaleItemModifier(Base):
    __tablename__ = "sale_item_modifiers"
    id = Column(Integer, primary_key=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False)
    modifier_id = Column(Integer, ForeignKey("modifiers.id"), nullable=True)
    name_snapshot = Column(String(128), nullable=False)
    price = Column(MONEY, nullable=False, default=0)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    method = Column(String(16), nullable=False)  # cash/card/bank_transfer
    amount = Column(MONEY, nullable=False)       # applied to the bill
    received = Column(MONEY, nullable=False, default=0)  # cash tendered
    change_due = Column(MONEY, nullable=False, default=0)
    created_at = Column(DateTime, default=_now, nullable=False)


class Refund(Base):
    __tablename__ = "refunds"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    amount = Column(MONEY, nullable=False)
    reason = Column(String(256), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class StockMove(Base):
    __tablename__ = "stock_moves"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty_change = Column(Numeric(12, 3), nullable=False)  # negative = out
    move_type = Column(String(16), nullable=False)  # opening/purchase/sale/adjustment/waste/return
    ref_type = Column(String(16), default="")
    ref_id = Column(Integer, nullable=True)
    unit_cost = Column(MONEY, nullable=True)
    note = Column(String(256), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)


class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    invoice_ref = Column(String(64), default="")
    total = Column(MONEY, nullable=False, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    items = relationship("PurchaseItem", cascade="all, delete-orphan", backref="purchase")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(MONEY, nullable=False)
    line_total = Column(MONEY, nullable=False)


class Shift(Base):
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    business_day = Column(String(10), nullable=False)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    opened_at = Column(DateTime, default=_now, nullable=False)
    opening_cash = Column(MONEY, nullable=False, default=0)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    closing_cash_counted = Column(MONEY, nullable=True)
    expected_cash = Column(MONEY, nullable=True)
    variance = Column(MONEY, nullable=True)
    status = Column(String(16), nullable=False, default="open")  # open/closed
    notes = Column(Text, default="")


class CashMove(Base):
    __tablename__ = "cash_moves"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    move_type = Column(String(16), nullable=False)  # cash_in/cash_out
    amount = Column(MONEY, nullable=False)
    reason = Column(String(256), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    category = Column(String(64), default="General")
    amount = Column(MONEY, nullable=False)
    note = Column(String(256), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), nullable=True, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False)
    entity = Column(String(64), default="")
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=_now, nullable=False)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    id = Column(Integer, primary_key=True)
    path = Column(String(512), nullable=False)
    size_bytes = Column(Integer, default=0)
    sha256 = Column(String(64), default="")
    validated = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True)
    license_key = Column(String(128), unique=True, nullable=False)
    issued_to = Column(String(128), default="")
    valid_until = Column(String(10), default="")  # YYYY-MM-DD or empty = perpetual
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=_now, nullable=False)


Index("ix_sales_business_day", Sale.business_day)
Index("ix_sales_status", Sale.status)
Index("ix_stock_moves_product", StockMove.product_id)
Index("ix_audit_created", AuditLog.created_at)
Index("ix_products_barcode", Product.barcode)


# ---------------------------------------------------------------------------
# Offline-first cloud sync (outbox pattern). Local SQLite is the system of
# record; rows here are uploaded to Supabase when connectivity allows.
# ---------------------------------------------------------------------------

class SyncQueue(Base):
    """Outbox: one row per pending cloud operation. Written in the SAME
    database transaction as the business mutation, so a crash can never lose
    a sync event. Rows are marked done only after the cloud confirms."""
    __tablename__ = "sync_queue"
    id = Column(Integer, primary_key=True)
    entity = Column(String(64), nullable=False)       # e.g. "sales"
    entity_id = Column(Integer, nullable=False)       # local PK
    sync_uuid = Column(String(36), nullable=False)    # stable id -> idempotency
    operation = Column(String(16), nullable=False, default="upsert")
    payload = Column(Text, nullable=False, default="{}")  # JSON
    status = Column(String(16), nullable=False, default="pending")  # pending/inflight/failed/done
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True)
    last_error = Column(String(512), default="")
    created_at = Column(DateTime, default=_now, nullable=False)
    __table_args__ = (UniqueConstraint("entity", "sync_uuid"),)


class SyncState(Base):
    """Single-row table: this installation's identity + cloud config."""
    __tablename__ = "sync_state"
    id = Column(Integer, primary_key=True)
    installation_id = Column(String(36), nullable=False)  # UUID, generated once
    sync_enabled = Column(Boolean, nullable=False, default=False)
    cloud_url = Column(String(256), default="")   # Supabase project URL (user-provided)
    anon_key = Column(String(512), default="")    # Supabase anon key (public by design + RLS)
    cloud_email = Column(String(128), default="") # per-installation Supabase Auth user
    cloud_password = Column(String(128), default="")  # random machine credential
    access_token = Column(Text, default="")
    refresh_token = Column(Text, default="")
    token_expires_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_error = Column(String(512), default="")


Index("ix_sync_queue_status", SyncQueue.status)
