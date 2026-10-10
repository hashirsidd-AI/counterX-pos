"""Stock control: receiving, adjustments, counts, waste, ledger, alerts."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..sync.service import enqueue_obj
from ..utils.money import d, q
from .auth import AuthService


class InventoryService:
    def __init__(self, session: Session, auth: AuthService):
        self.s = session
        self.auth = auth

    def stock_level(self, product_id: int) -> Decimal:
        total = self.s.query(func.coalesce(func.sum(models.StockMove.qty_change), 0)).filter(
            models.StockMove.product_id == product_id).scalar()
        return q(total or 0)

    def adjust(self, product_id: int, qty_change: Decimal, user: models.User,
               note: str = "") -> models.StockMove:
        self.auth.require(user, "stock_adjust")
        move = models.StockMove(product_id=product_id, qty_change=q(qty_change),
                                move_type="adjustment", note=note, user_id=user.id)
        self.s.add(move)
        self.s.flush()
        enqueue_obj(self.s, "stock_moves", move)
        self._audit(user, "stock.adjust", product_id, f"qty_change={qty_change} note={note}")
        return move

    def set_opening_stock(self, product_id: int, qty: Decimal, user: models.User) -> None:
        self.auth.require(user, "stock_adjust")
        current = self.stock_level(product_id)
        diff = q(d(qty) - current)
        if diff != 0:
            self.s.add(models.StockMove(product_id=product_id, qty_change=diff,
                                        move_type="opening", note="Opening stock",
                                        user_id=user.id))
            self.s.flush()

    def receive_purchase(self, supplier_id: int | None, items: list[dict],
                         user: models.User, invoice_ref: str = "") -> models.Purchase:
        """items: [{product_id, qty, unit_cost}] — creates purchase + stock moves."""
        self.auth.require(user, "purchases")
        purchase = models.Purchase(supplier_id=supplier_id, invoice_ref=invoice_ref,
                                   user_id=user.id)
        self.s.add(purchase)
        self.s.flush()
        total = Decimal("0")
        for it in items:
            qty, cost = q(it["qty"]), q(it["unit_cost"])
            line = q(qty * cost)
            total += line
            self.s.add(models.PurchaseItem(purchase_id=purchase.id,
                                           product_id=it["product_id"],
                                           qty=qty, unit_cost=cost, line_total=line))
            mv = models.StockMove(product_id=it["product_id"], qty_change=qty,
                                     move_type="purchase", ref_type="purchase",
                                     ref_id=purchase.id, unit_cost=cost,
                                     user_id=user.id)
            self.s.add(mv)
            self.s.flush()
            enqueue_obj(self.s, "stock_moves", mv)
            prod = self.s.get(models.Product, it["product_id"])
            if prod:
                prod.cost_price = cost  # last purchase cost becomes the cost price
        purchase.total = q(total)
        self.s.flush()
        self._audit(user, "purchase.receive", purchase.id, f"total={purchase.total}")
        return purchase

    def record_waste(self, product_id: int, qty: Decimal, user: models.User,
                     note: str = "") -> models.StockMove:
        self.auth.require(user, "stock_adjust")
        move = models.StockMove(product_id=product_id, qty_change=-q(qty),
                                move_type="waste", note=note, user_id=user.id)
        self.s.add(move)
        self.s.flush()
        return move

    def ledger(self, product_id: int, limit: int = 200) -> list[models.StockMove]:
        return (self.s.query(models.StockMove)
                .filter_by(product_id=product_id)
                .order_by(models.StockMove.created_at.desc(), models.StockMove.id.desc())
                .limit(limit).all())

    def low_stock(self) -> list[dict]:
        """Products at or below their minimum stock threshold."""
        result = []
        for p in self.s.query(models.Product).filter_by(is_active=True, track_stock=True):
            level = self.stock_level(p.id)
            if level <= (p.min_stock or Decimal("0")):
                result.append({"product": p, "level": level, "min": p.min_stock or Decimal("0")})
        return result

    def valuation(self) -> dict:
        """Stock valuation at cost price."""
        total = Decimal("0")
        lines = []
        for p in self.s.query(models.Product).filter_by(is_active=True, track_stock=True):
            level = self.stock_level(p.id)
            value = q(level * (p.cost_price or Decimal("0")))
            total += value
            if level != 0:
                lines.append({"product": p, "level": level, "value": value})
        return {"total": q(total), "lines": lines}

    def _audit(self, user, action, product_id, details):
        self.s.add(models.AuditLog(user_id=user.id, action=action, entity="products",
                                   entity_id=product_id, details=details))
