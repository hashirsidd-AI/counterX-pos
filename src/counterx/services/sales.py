"""POS billing: cart math, transactional checkout, hold/resume, void, refund.

All money uses Decimal. Checkout runs inside one database transaction:
sale + items + payments + stock moves + audit row are written atomically.
`client_ref` (UUID per checkout attempt) makes double-clicks/retries safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..sync.service import enqueue_obj
from ..utils.money import d, q
from .auth import AuthService, PermissionDenied


@dataclass
class CartModifier:
    modifier_id: int | None
    name: str
    price: Decimal


@dataclass
class CartLine:
    product_id: int | None
    variant_id: int | None
    name: str
    qty: Decimal
    unit_price: Decimal
    item_discount: Decimal = Decimal("0")   # total discount for this line
    tax_rate: Decimal = Decimal("0")        # percent
    modifiers: list[CartModifier] = field(default_factory=list)


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)
    order_discount: Decimal = Decimal("0")  # order-level discount amount
    service_charge: Decimal = Decimal("0")
    delivery_charge: Decimal = Decimal("0")
    sale_type: str = "takeaway"
    table_no: str = ""
    waiter: str = ""
    customer_id: int | None = None
    notes: str = ""


class SaleService:
    def __init__(self, session: Session, auth: AuthService):
        self.s = session
        self.auth = auth

    # -- cart math -------------------------------------------------------------
    def line_totals(self, line: CartLine) -> dict:
        """Returns gross, discount, taxable, tax, total for one cart line."""
        gross = q(line.qty * line.unit_price)
        mods = q(sum((m.price for m in line.modifiers), Decimal("0")) * line.qty)
        discount = q(min(line.item_discount, gross + mods))
        taxable = q(gross + mods - discount)
        tax = q(taxable * line.tax_rate / 100)
        total = q(taxable + tax)
        return {"gross": gross, "modifiers": mods, "discount": discount,
                "taxable": taxable, "tax": tax, "total": total}

    def cart_totals(self, cart: Cart) -> dict:
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        for line in cart.lines:
            t = self.line_totals(line)
            subtotal += t["gross"] + t["modifiers"]
            discount_total += t["discount"]
            tax_total += t["tax"]
        order_discount = q(min(cart.order_discount, subtotal - discount_total))
        grand = q(subtotal - discount_total - order_discount + tax_total
                  + cart.service_charge + cart.delivery_charge)
        return {
            "subtotal": q(subtotal),
            "item_discount": q(discount_total),
            "order_discount": order_discount,
            "discount_total": q(discount_total + order_discount),
            "tax_total": q(tax_total),
            "service_charge": q(cart.service_charge),
            "delivery_charge": q(cart.delivery_charge),
            "grand_total": grand,
        }

    # -- checkout ----------------------------------------------------------------
    def _next_invoice_no(self) -> int:
        last = self.s.query(func.max(models.Sale.invoice_no)).scalar() or 0
        return int(last) + 1

    def _next_token(self, business_day: str) -> str:
        count = self.s.query(func.count(models.Sale.id)).filter(
            models.Sale.business_day == business_day).scalar() or 0
        return f"T{count + 1:04d}"

    def checkout(self, cart: Cart, payments: list[dict], user: models.User,
                 shift_id: int | None = None,
                 client_ref: str | None = None) -> models.Sale:
        """Complete a sale. `payments`: [{method, amount, received}]."""
        self.auth.require(user, "sell")
        if not cart.lines:
            raise ValueError("Cart is empty")
        totals = self.cart_totals(cart)
        paid = q(sum((d(p["amount"]) for p in payments), Decimal("0")))
        if paid < totals["grand_total"]:
            raise ValueError(f"Insufficient payment: {paid} < {totals['grand_total']}")
        client_ref = client_ref or uuid4().hex
        existing = self.s.query(models.Sale).filter_by(client_ref=client_ref).first()
        if existing:
            return existing  # duplicate submit (double click / retry) -> same sale

        business_day = datetime.now().strftime("%Y-%m-%d")
        sale = models.Sale(
            invoice_no=self._next_invoice_no(),
            token_no=self._next_token(business_day),
            client_ref=client_ref,
            business_day=business_day,
            sale_type=cart.sale_type,
            table_no=cart.table_no,
            waiter=cart.waiter,
            customer_id=cart.customer_id,
            user_id=user.id,
            shift_id=shift_id,
            subtotal=totals["subtotal"],
            discount_total=totals["discount_total"],
            tax_total=totals["tax_total"],
            service_charge=totals["service_charge"],
            delivery_charge=totals["delivery_charge"],
            grand_total=totals["grand_total"],
            notes=cart.notes,
        )
        self.s.add(sale)
        self.s.flush()

        # Apply payment legs in order; cash tendered beyond what is due
        # comes back as change. `amount` = applied to the bill.
        remaining_due = totals["grand_total"]
        for p in payments:
            method = p["method"]
            if method == "cash":
                tendered = q(p.get("received", p["amount"]))
                applied = min(tendered, remaining_due)
                change = q(tendered - applied)
                received = tendered
            else:
                applied = min(q(p["amount"]), remaining_due)
                change = Decimal("0")
                received = applied
            remaining_due = q(remaining_due - applied)
            self.s.add(models.Payment(sale_id=sale.id, method=method,
                                      amount=applied, received=received,
                                      change_due=change))

        for line in cart.lines:
            t = self.line_totals(line)
            item = models.SaleItem(
                sale_id=sale.id, product_id=line.product_id, variant_id=line.variant_id,
                name_snapshot=line.name, qty=line.qty, unit_price=q(line.unit_price),
                item_discount=t["discount"], tax_amount=t["tax"], line_total=t["total"])
            self.s.add(item)
            self.s.flush()
            for m in line.modifiers:
                self.s.add(models.SaleItemModifier(
                    sale_item_id=item.id, modifier_id=m.modifier_id,
                    name_snapshot=m.name, price=q(m.price)))
            if line.product_id:
                prod = self.s.get(models.Product, line.product_id)
                if prod and prod.track_stock:
                    self._deduct_stock(prod, line.qty, sale.id, user)

        self.s.add(models.AuditLog(user_id=user.id, action="sale.checkout",
                                   entity="sales", entity_id=sale.id,
                                   details=f"invoice={sale.invoice_no} total={sale.grand_total}"))
        self.s.flush()
        # Outbox: queue for cloud sync in the SAME transaction.
        enqueue_obj(self.s, "sales", sale)
        for item in sale.items:
            enqueue_obj(self.s, "sale_items", item)
        for payment in sale.payments:
            enqueue_obj(self.s, "payments", payment)
        return sale

    def _deduct_stock(self, product: models.Product, qty: Decimal,
                      sale_id: int, user: models.User) -> None:
        allow_negative = self._setting("allow_negative_stock", "0") == "1"
        level = self.stock_level(product.id)
        if not allow_negative and level - qty < 0:
            raise ValueError(f"Insufficient stock for {product.name} "
                             f"(have {level}, need {qty})")
        self.s.add(models.StockMove(product_id=product.id, qty_change=-q(qty),
                                    move_type="sale", ref_type="sale", ref_id=sale_id,
                                    user_id=user.id))

    # -- hold / resume -----------------------------------------------------------
    def hold_sale(self, cart: Cart, user: models.User) -> models.Sale:
        self.auth.require(user, "sell")
        if not cart.lines:
            raise ValueError("Cart is empty")
        totals = self.cart_totals(cart)
        business_day = datetime.now().strftime("%Y-%m-%d")
        sale = models.Sale(
            invoice_no=self._next_invoice_no(), token_no=self._next_token(business_day),
            client_ref=uuid4().hex, business_day=business_day, sale_type=cart.sale_type,
            table_no=cart.table_no, waiter=cart.waiter, customer_id=cart.customer_id,
            user_id=user.id, subtotal=totals["subtotal"],
            discount_total=totals["discount_total"], tax_total=totals["tax_total"],
            service_charge=totals["service_charge"], delivery_charge=totals["delivery_charge"],
            grand_total=totals["grand_total"], status="held", notes=cart.notes)
        self.s.add(sale)
        self.s.flush()
        for line in cart.lines:
            t = self.line_totals(line)
            self.s.add(models.SaleItem(
                sale_id=sale.id, product_id=line.product_id, variant_id=line.variant_id,
                name_snapshot=line.name, qty=line.qty, unit_price=q(line.unit_price),
                item_discount=t["discount"], tax_amount=t["tax"], line_total=t["total"]))
        self.s.flush()
        return sale

    def held_sales(self) -> list[models.Sale]:
        return (self.s.query(models.Sale).filter_by(status="held")
                .order_by(models.Sale.created_at.desc()).all())

    def release_hold(self, sale_id: int, user: models.User) -> models.Sale:
        """Consume a held sale when it is resumed into the cart.

        The held row can no longer be resumed afterwards, so the same
        ticket can never be fulfilled twice. Held sales carry no payments
        or stock moves, so nothing financial needs reversing.
        """
        self.auth.require(user, "sell")
        sale = self.s.get(models.Sale, sale_id)
        if not sale or sale.status != "held":
            raise ValueError("Held sale not found or already processed")
        sale.status = "released"
        self.s.add(models.AuditLog(user_id=user.id, action="sale.hold_release",
                                   entity="sales", entity_id=sale.id,
                                   details=f"token={sale.token_no}"))
        self.s.flush()
        return sale

    # -- void & refund -------------------------------------------------------------
    def void_sale(self, sale_id: int, user: models.User, reason: str = "") -> models.Sale:
        self.auth.require(user, "void")
        sale = self.s.get(models.Sale, sale_id)
        if not sale or sale.status != "completed":
            raise ValueError("Only completed sales can be voided")
        sale.status = "voided"
        # reverse stock
        for item in sale.items:
            if item.product_id:
                prod = self.s.get(models.Product, item.product_id)
                if prod and prod.track_stock:
                    self.s.add(models.StockMove(
                        product_id=item.product_id, qty_change=item.qty,
                        move_type="adjustment", ref_type="void", ref_id=sale.id,
                        note=f"void invoice {sale.invoice_no}", user_id=user.id))
        self.s.add(models.AuditLog(user_id=user.id, action="sale.void",
                                   entity="sales", entity_id=sale.id, details=reason))
        self.s.flush()
        enqueue_obj(self.s, "sales", sale)
        return sale

    def refund(self, sale_id: int, amount: Decimal, user: models.User,
               reason: str = "") -> models.Refund:
        self.auth.require(user, "refund")
        sale = self.s.get(models.Sale, sale_id)
        if not sale or sale.status != "completed":
            raise ValueError("Only completed sales can be refunded")
        amount = q(amount)
        if amount <= 0 or amount > sale.grand_total:
            raise ValueError("Invalid refund amount")
        refund = models.Refund(sale_id=sale.id, amount=amount,
                               reason=reason, user_id=user.id)
        self.s.add(refund)
        if amount == q(sale.grand_total):
            sale.status = "refunded"
        self.s.add(models.AuditLog(user_id=user.id, action="sale.refund",
                                   entity="sales", entity_id=sale.id,
                                   details=f"amount={amount} reason={reason}"))
        self.s.flush()
        enqueue_obj(self.s, "refunds", refund)
        enqueue_obj(self.s, "sales", sale)
        return refund

    # -- lookups -------------------------------------------------------------------
    def get_sale(self, sale_id: int) -> models.Sale | None:
        return self.s.get(models.Sale, sale_id)

    def stock_level(self, product_id: int) -> Decimal:
        total = self.s.query(func.coalesce(func.sum(models.StockMove.qty_change), 0)).filter(
            models.StockMove.product_id == product_id).scalar()
        return q(total or 0)

    def _setting(self, key: str, default: str = "") -> str:
        row = self.s.query(models.Setting).filter_by(key=key).first()
        return row.value if row else default
