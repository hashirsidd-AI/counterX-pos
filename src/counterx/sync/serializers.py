"""Local row -> cloud dict. NEVER includes passwords or password hashes."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _num(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _base(obj, installation_id: str) -> dict:
    return {
        "installation_id": installation_id,
        "sync_uuid": obj.sync_uuid,
        "updated_at": _iso(datetime.now()),
    }


def serialize(entity: str, obj, installation_id: str) -> dict:
    fn = _SERIALIZERS.get(entity)
    if not fn:
        raise ValueError(f"No serializer for entity: {entity}")
    data = _base(obj, installation_id)
    data.update(fn(obj))
    return data


def _sale(o):
    return {"local_id": o.id, "invoice_no": o.invoice_no, "token_no": o.token_no,
            "business_day": o.business_day, "sale_type": o.sale_type,
            "table_no": o.table_no, "waiter": o.waiter,
            "subtotal": _num(o.subtotal), "discount_total": _num(o.discount_total),
            "tax_total": _num(o.tax_total), "service_charge": _num(o.service_charge),
            "delivery_charge": _num(o.delivery_charge),
            "grand_total": _num(o.grand_total), "status": o.status,
            "created_at": _iso(o.created_at)}


def _sale_item(o):
    return {"local_id": o.id, "sale_sync_uuid": None, "product_id": o.product_id,
            "name": o.name_snapshot, "qty": _num(o.qty),
            "unit_price": _num(o.unit_price), "item_discount": _num(o.item_discount),
            "tax_amount": _num(o.tax_amount), "line_total": _num(o.line_total)}


def _payment(o):
    return {"local_id": o.id, "method": o.method, "amount": _num(o.amount),
            "received": _num(o.received), "change_due": _num(o.change_due),
            "created_at": _iso(o.created_at)}


def _product(o):
    return {"local_id": o.id, "sku": o.sku, "barcode": o.barcode, "name": o.name,
            "name_ur": o.name_ur, "category_id": o.category_id,
            "cost_price": _num(o.cost_price), "sell_price": _num(o.sell_price),
            "track_stock": bool(o.track_stock), "min_stock": _num(o.min_stock),
            "is_active": bool(o.is_active)}


def _category(o):
    return {"local_id": o.id, "name": o.name, "name_ur": o.name_ur,
            "parent_id": o.parent_id, "is_active": bool(o.is_active)}


def _stock_move(o):
    return {"local_id": o.id, "product_id": o.product_id,
            "qty_change": _num(o.qty_change), "move_type": o.move_type,
            "ref_type": o.ref_type, "ref_id": o.ref_id,
            "note": o.note, "created_at": _iso(o.created_at)}


def _refund(o):
    return {"local_id": o.id, "amount": _num(o.amount), "reason": o.reason,
            "created_at": _iso(o.created_at)}


def _shift(o):
    return {"local_id": o.id, "business_day": o.business_day,
            "opening_cash": _num(o.opening_cash),
            "closing_cash_counted": _num(o.closing_cash_counted),
            "expected_cash": _num(o.expected_cash), "variance": _num(o.variance),
            "status": o.status, "opened_at": _iso(o.opened_at),
            "closed_at": _iso(o.closed_at)}


def _cash_move(o):
    return {"local_id": o.id, "move_type": o.move_type,
            "amount": _num(o.amount), "reason": o.reason,
            "created_at": _iso(o.created_at)}


def _expense(o):
    return {"local_id": o.id, "category": o.category,
            "amount": _num(o.amount), "note": o.note,
            "created_at": _iso(o.created_at)}


def _purchase(o):
    return {"local_id": o.id, "invoice_ref": o.invoice_ref,
            "total": _num(o.total), "created_at": _iso(o.created_at)}


def _customer(o):
    return {"local_id": o.id, "name": o.name, "phone": o.phone,
            "address": o.address}


def _supplier(o):
    return {"local_id": o.id, "name": o.name, "phone": o.phone,
            "address": o.address}


def _user(o):
    # Redacted: identity and role only. Password hashes NEVER leave the PC.
    return {"local_id": o.id, "username": o.username,
            "full_name": o.full_name, "role": o.role,
            "is_active": bool(o.is_active)}


def _audit_log(o):
    return {"local_id": o.id, "action": o.action, "entity": o.entity,
            "entity_id": o.entity_id, "details": (o.details or "")[:500],
            "created_at": _iso(o.created_at)}


_SERIALIZERS = {
    "sales": _sale,
    "sale_items": _sale_item,
    "payments": _payment,
    "products": _product,
    "categories": _category,
    "stock_moves": _stock_move,
    "refunds": _refund,
    "shifts": _shift,
    "cash_moves": _cash_move,
    "expenses": _expense,
    "purchases": _purchase,
    "customers": _customer,
    "suppliers": _supplier,
    "users": _user,
    "audit_logs": _audit_log,
}

# Immutable financial records: first write wins, never overwritten.
IMMUTABLE_ENTITIES = frozenset({
    "sales", "sale_items", "payments", "stock_moves", "refunds",
    "shifts", "cash_moves", "expenses", "purchases", "audit_logs",
})

# Mutable master data: last write wins (by updated_at).
MUTABLE_ENTITIES = frozenset({
    "products", "categories", "customers", "suppliers", "users",
})

ENTITY_TABLES = {
    "sales": "sales", "sale_items": "sale_items", "payments": "payments",
    "products": "products", "categories": "categories",
    "stock_moves": "stock_moves", "refunds": "refunds", "shifts": "shifts",
    "cash_moves": "cash_moves", "expenses": "expenses", "purchases": "purchases",
    "customers": "customers", "suppliers": "suppliers", "users": "users",
    "audit_logs": "audit_logs",
}
