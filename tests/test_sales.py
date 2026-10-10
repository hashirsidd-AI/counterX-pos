from decimal import Decimal

import pytest

from counterx.services import Cart, CartLine, PermissionDenied
from counterx.utils.money import q


@pytest.fixture()
def product(db, svcs, owner):
    cat = svcs["catalog"].create_category("Platters", owner)
    p = svcs["catalog"].create_product(
        owner, sku="PLT-001", name="Chinese Platter",
        sell_price=Decimal("1799"), cost_price=Decimal("900"),
        category_id=cat.id)
    svcs["inventory"].set_opening_stock(p.id, Decimal("50"), owner)
    return p


def _cart(product, qty="2"):
    return Cart(lines=[CartLine(product_id=product.id, variant_id=None,
                                name=product.name, qty=Decimal(qty),
                                unit_price=product.sell_price,
                                tax_rate=Decimal("15"))])


def _pay(total):
    return [{"method": "cash", "amount": total, "received": total}]


def test_cart_totals(svcs, product):
    totals = svcs["sales"].cart_totals(_cart(product))
    assert totals["subtotal"] == Decimal("3598.00")
    assert totals["tax_total"] == Decimal("539.70")   # 15% of 3598
    assert totals["grand_total"] == Decimal("4137.70")


def test_item_discount_capped(svcs, product):
    cart = _cart(product, qty="1")
    cart.lines[0].item_discount = Decimal("99999")
    totals = svcs["sales"].cart_totals(cart)
    assert totals["discount_total"] == Decimal("1799.00")  # capped at line gross
    assert totals["grand_total"] == Decimal("0.00")


def test_checkout_happy_path(db, svcs, owner, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)
    assert sale.invoice_no == 1
    assert sale.grand_total == Decimal("4137.70")
    assert len(sale.payments) == 1
    # stock deducted
    assert svcs["inventory"].stock_level(product.id) == Decimal("48")
    # sale persisted with items
    assert len(sale.items) == 1


def test_checkout_idempotent_on_retry(db, svcs, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    ref = "retry-key-123"
    s1 = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier, client_ref=ref)
    s2 = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier, client_ref=ref)
    assert s1.id == s2.id
    assert svcs["inventory"].stock_level(product.id) == Decimal("48")  # deducted once


def test_insufficient_payment_rejected(svcs, cashier, product):
    cart = _cart(product)
    with pytest.raises(ValueError):
        svcs["sales"].checkout(cart, [{"method": "cash", "amount": Decimal("10"),
                                       "received": Decimal("10")}], cashier)


def test_insufficient_stock_rejected(svcs, cashier, product):
    cart = _cart(product, qty="999")
    totals = svcs["sales"].cart_totals(cart)
    with pytest.raises(ValueError, match="Insufficient stock"):
        svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)


def test_cash_change_computed(db, svcs, cashier, product):
    cart = _cart(product, qty="1")
    totals = svcs["sales"].cart_totals(cart)  # 1799 + 269.85 = 2068.85
    sale = svcs["sales"].checkout(
        cart, [{"method": "cash", "amount": totals["grand_total"],
                "received": Decimal("2500")}], cashier)
    assert sale.payments[0].change_due == Decimal("431.15")


def test_split_payment(db, svcs, cashier, product):
    cart = _cart(product, qty="1")
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, [
        {"method": "cash", "amount": Decimal("1000"), "received": Decimal("1000")},
        {"method": "card", "amount": q(totals["grand_total"] - Decimal("1000"))},
    ], cashier)
    assert len(sale.payments) == 2
    assert sum((p.amount for p in sale.payments), Decimal("0")) == totals["grand_total"]


def test_hold_and_list(svcs, cashier, product):
    held = svcs["sales"].hold_sale(_cart(product), cashier)
    assert held.status == "held"
    assert any(s.id == held.id for s in svcs["sales"].held_sales())
    # holding does not touch stock
    assert svcs["inventory"].stock_level(product.id) == Decimal("50")


def test_void_reverses_stock(db, svcs, owner, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)
    svcs["sales"].void_sale(sale.id, owner, reason="test void")
    assert svcs["sales"].get_sale(sale.id).status == "voided"
    assert svcs["inventory"].stock_level(product.id) == Decimal("50")


def test_void_requires_permission(svcs, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)
    with pytest.raises(PermissionDenied):
        svcs["sales"].void_sale(sale.id, cashier)


def test_partial_refund(db, svcs, owner, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)
    r = svcs["sales"].refund(sale.id, Decimal("100"), owner, reason="goodwill")
    assert r.amount == Decimal("100.00")
    assert svcs["sales"].get_sale(sale.id).status == "completed"  # partial -> stays completed


def test_full_refund_marks_sale(db, svcs, owner, cashier, product):
    cart = _cart(product)
    totals = svcs["sales"].cart_totals(cart)
    sale = svcs["sales"].checkout(cart, _pay(totals["grand_total"]), cashier)
    svcs["sales"].refund(sale.id, totals["grand_total"], owner)
    assert svcs["sales"].get_sale(sale.id).status == "refunded"


def test_release_hold_prevents_double_resume(db, svcs, cashier, product):
    held = svcs["sales"].hold_sale(_cart(product), cashier)
    svcs["sales"].release_hold(held.id, cashier)
    assert svcs["sales"].get_sale(held.id).status == "released"
    assert all(s.id != held.id for s in svcs["sales"].held_sales())
    with pytest.raises(ValueError):
        svcs["sales"].release_hold(held.id, cashier)  # already consumed
