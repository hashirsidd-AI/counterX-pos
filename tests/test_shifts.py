from decimal import Decimal

import pytest

from counterx.services import Cart, CartLine, PermissionDenied


def _sell(svcs, user, amount, method="cash", shift_id=None):
    """Direct minimal sale row for shift math tests (bypasses catalog)."""
    from counterx import models
    from datetime import datetime
    sale = models.Sale(
        invoice_no=svcs["sales"]._next_invoice_no(),
        token_no="T0001", client_ref=f"ref-{amount}-{method}-{datetime.now().microsecond}",
        business_day=datetime.now().strftime("%Y-%m-%d"), sale_type="takeaway",
        user_id=user.id, shift_id=shift_id, subtotal=amount,
        grand_total=amount)
    svcs["sales"].s.add(sale)
    svcs["sales"].s.flush()
    svcs["sales"].s.add(models.Payment(sale_id=sale.id, method=method,
                                       amount=amount, received=amount))
    svcs["sales"].s.flush()
    return sale


def test_open_and_close_shift(svcs, owner):
    shift = svcs["shifts"].open_shift(owner, Decimal("5000"))
    assert shift.status == "open"
    assert svcs["shifts"].current_shift().id == shift.id
    closed = svcs["shifts"].close_shift(shift.id, Decimal("5000"), owner)
    assert closed.status == "closed"
    assert closed.expected_cash == Decimal("5000.00")
    assert closed.variance == Decimal("0.00")
    assert svcs["shifts"].current_shift() is None


def test_double_open_rejected(svcs, owner):
    svcs["shifts"].open_shift(owner, Decimal("1000"))
    with pytest.raises(ValueError):
        svcs["shifts"].open_shift(owner, Decimal("1000"))


def test_expected_cash_math(svcs, owner):
    shift = svcs["shifts"].open_shift(owner, Decimal("5000"))
    _sell(svcs, owner, Decimal("2000"), "cash", shift.id)    # drawer +2000
    _sell(svcs, owner, Decimal("1500"), "card", shift.id)    # drawer +0
    svcs["shifts"].cash_in(shift.id, Decimal("500"), owner, "change float")
    svcs["shifts"].cash_out(shift.id, Decimal("200"), owner, "supplier")
    svcs["shifts"].add_expense(shift.id, "Utilities", Decimal("300"), owner)
    # 5000 + 2000 + 500 - 200 - 300 = 7000
    assert svcs["shifts"].expected_cash(shift.id) == Decimal("7000.00")
    closed = svcs["shifts"].close_shift(shift.id, Decimal("6950"), owner)
    assert closed.variance == Decimal("-50.00")  # shortage


def test_cashier_cannot_close_shift(svcs, owner, cashier):
    shift = svcs["shifts"].open_shift(owner, Decimal("100"))
    with pytest.raises(PermissionDenied):
        svcs["shifts"].close_shift(shift.id, Decimal("100"), cashier)


def test_shift_summary(svcs, owner):
    shift = svcs["shifts"].open_shift(owner, Decimal("0"))
    _sell(svcs, owner, Decimal("1000"), "cash", shift.id)
    _sell(svcs, owner, Decimal("500"), "card", shift.id)
    summary = svcs["shifts"].shift_summary(shift.id)
    assert summary["sales_count"] == 2
    assert summary["net"] == Decimal("1500.00")
    assert summary["by_method"]["cash"] == Decimal("1000.00")
    assert summary["by_method"]["card"] == Decimal("500.00")
