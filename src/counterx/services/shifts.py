"""Cashier shifts: open, cash in/out, expenses, close with reconciliation.

Expected closing cash = opening_cash
    + cash received from completed sales (in this shift)
    + cash_in moves
    - cash_out moves
    - expenses (cash)
    - cash refunds issued in this shift

Card / bank-transfer payments never touch the cash drawer.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..sync.service import enqueue_obj
from ..utils.money import d, q
from .auth import AuthService


class ShiftService:
    def __init__(self, session: Session, auth: AuthService):
        self.s = session
        self.auth = auth

    # -- lifecycle -----------------------------------------------------------------
    def current_shift(self) -> models.Shift | None:
        return (self.s.query(models.Shift).filter_by(status="open")
                .order_by(models.Shift.opened_at.desc()).first())

    def open_shift(self, user: models.User, opening_cash: Decimal) -> models.Shift:
        self.auth.require(user, "sell")
        if self.current_shift():
            raise ValueError("A shift is already open")
        shift = models.Shift(business_day=datetime.now().strftime("%Y-%m-%d"),
                             opened_by=user.id, opening_cash=q(opening_cash))
        self.s.add(shift)
        self.s.flush()
        self._audit(user, "shift.open", shift.id, f"opening_cash={shift.opening_cash}")
        enqueue_obj(self.s, "shifts", shift)
        return shift

    def cash_in(self, shift_id: int, amount: Decimal, user: models.User,
                reason: str = "") -> models.CashMove:
        self.auth.require(user, "cash_moves")
        return self._cash_move(shift_id, "cash_in", amount, user, reason)

    def cash_out(self, shift_id: int, amount: Decimal, user: models.User,
                 reason: str = "") -> models.CashMove:
        self.auth.require(user, "cash_moves")
        return self._cash_move(shift_id, "cash_out", amount, user, reason)

    def _cash_move(self, shift_id: int, move_type: str, amount: Decimal,
                   user: models.User, reason: str) -> models.CashMove:
        amount = q(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        shift = self._open_shift_or_raise(shift_id)
        move = models.CashMove(shift_id=shift.id, move_type=move_type, amount=amount,
                               reason=reason, user_id=user.id)
        self.s.add(move)
        self.s.flush()
        self._audit(user, f"shift.{move_type}", shift.id, f"amount={amount} {reason}")
        enqueue_obj(self.s, "cash_moves", move)
        return move

    def add_expense(self, shift_id: int, category: str, amount: Decimal,
                    user: models.User, note: str = "") -> models.Expense:
        self.auth.require(user, "expenses")
        amount = q(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        shift = self._open_shift_or_raise(shift_id)
        expense = models.Expense(shift_id=shift.id, category=category, amount=amount,
                                 note=note, user_id=user.id)
        self.s.add(expense)
        self.s.flush()
        self._audit(user, "shift.expense", shift.id, f"{category} amount={amount} {note}")
        enqueue_obj(self.s, "expenses", expense)
        return expense

    def expected_cash(self, shift_id: int) -> Decimal:
        shift = self.s.get(models.Shift, shift_id)
        if not shift:
            raise ValueError("Shift not found")
        cash_sales = self.s.query(
            func.coalesce(func.sum(models.Payment.amount), 0)).join(
            models.Sale, models.Payment.sale_id == models.Sale.id).filter(
            models.Sale.shift_id == shift.id,
            models.Sale.status == "completed",
            models.Payment.method == "cash").scalar() or 0
        cash_in = self._moves_total(shift.id, "cash_in")
        cash_out = self._moves_total(shift.id, "cash_out")
        expenses = self.s.query(func.coalesce(func.sum(models.Expense.amount), 0)).filter(
            models.Expense.shift_id == shift.id).scalar() or 0
        refunds = self.s.query(func.coalesce(func.sum(models.Refund.amount), 0)).join(
            models.Sale, models.Refund.sale_id == models.Sale.id).filter(
            models.Sale.shift_id == shift.id,
            models.Sale.status.in_(("completed", "refunded"))).scalar() or 0
        return q(d(shift.opening_cash) + d(cash_sales) + d(cash_in)
                 - d(cash_out) - d(expenses) - d(refunds))

    def close_shift(self, shift_id: int, counted_cash: Decimal,
                    user: models.User) -> models.Shift:
        self.auth.require(user, "shift_close")
        shift = self._open_shift_or_raise(shift_id)
        expected = self.expected_cash(shift.id)
        counted = q(counted_cash)
        shift.closing_cash_counted = counted
        shift.expected_cash = expected
        shift.variance = q(counted - expected)
        shift.status = "closed"
        shift.closed_by = user.id
        shift.closed_at = datetime.now()
        self.s.flush()
        self._audit(user, "shift.close", shift.id,
                    f"expected={expected} counted={counted} variance={shift.variance}")
        enqueue_obj(self.s, "shifts", shift)
        return shift

    def shift_history(self, limit: int = 100) -> list[models.Shift]:
        return (self.s.query(models.Shift).order_by(models.Shift.opened_at.desc())
                .limit(limit).all())

    def shift_summary(self, shift_id: int) -> dict:
        """Sales/payment breakdown for the closing report."""
        shift = self.s.get(models.Shift, shift_id)
        sales = (self.s.query(models.Sale)
                 .filter(models.Sale.shift_id == shift_id,
                         models.Sale.status == "completed").all())
        by_type: dict[str, dict] = {}
        by_method: dict[str, Decimal] = {}
        gross = discount = tax = Decimal("0")
        for sale in sales:
            t = by_type.setdefault(sale.sale_type, {"count": 0, "total": Decimal("0")})
            t["count"] += 1
            t["total"] = q(t["total"] + sale.grand_total)
            gross += sale.subtotal
            discount += sale.discount_total
            tax += sale.tax_total
            for p in sale.payments:
                by_method[p.method] = q(by_method.get(p.method, Decimal("0")) + p.amount)
        return {
            "shift": shift,
            "sales_count": len(sales),
            "gross": q(gross),
            "discount": q(discount),
            "tax": q(tax),
            "net": q(sum((s.grand_total for s in sales), Decimal("0"))),
            "by_type": by_type,
            "by_method": {k: q(v) for k, v in by_method.items()},
            "expected_cash": self.expected_cash(shift_id),
        }

    # -- helpers ---------------------------------------------------------------------
    def _open_shift_or_raise(self, shift_id: int) -> models.Shift:
        shift = self.s.get(models.Shift, shift_id)
        if not shift or shift.status != "open":
            raise ValueError("Shift is not open")
        return shift

    def _moves_total(self, shift_id: int, move_type: str) -> Decimal:
        total = self.s.query(func.coalesce(func.sum(models.CashMove.amount), 0)).filter(
            models.CashMove.shift_id == shift_id,
            models.CashMove.move_type == move_type).scalar() or 0
        return q(total)

    def _audit(self, user, action, shift_id, details):
        self.s.add(models.AuditLog(user_id=user.id, action=action, entity="shifts",
                                   entity_id=shift_id, details=details))
