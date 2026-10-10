from decimal import Decimal

import pytest

from counterx.services import PermissionDenied


@pytest.fixture()
def product(db, svcs, owner):
    return svcs["catalog"].create_product(
        owner, sku="RICE-1KG", name="Rice 1kg",
        sell_price=Decimal("350"), cost_price=Decimal("300"))


def test_opening_stock(svcs, owner, product):
    svcs["inventory"].set_opening_stock(product.id, Decimal("100"), owner)
    assert svcs["inventory"].stock_level(product.id) == Decimal("100")


def test_purchase_receiving_updates_stock_and_cost(db, svcs, owner, product):
    svcs["inventory"].set_opening_stock(product.id, Decimal("10"), owner)
    pur = svcs["inventory"].receive_purchase(
        None, [{"product_id": product.id, "qty": Decimal("40"),
                "unit_cost": Decimal("310")}], owner, invoice_ref="SUP-1")
    assert pur.total == Decimal("12400.00")
    assert svcs["inventory"].stock_level(product.id) == Decimal("50")
    db.refresh(product)
    assert product.cost_price == Decimal("310.00")  # last cost wins


def test_adjust_and_waste(svcs, owner, product):
    svcs["inventory"].set_opening_stock(product.id, Decimal("100"), owner)
    svcs["inventory"].adjust(product.id, Decimal("-5"), owner, note="damaged")
    svcs["inventory"].record_waste(product.id, Decimal("2"), owner, note="expired")
    assert svcs["inventory"].stock_level(product.id) == Decimal("93")


def test_cashier_cannot_adjust(svcs, cashier, product):
    with pytest.raises(PermissionDenied):
        svcs["inventory"].adjust(product.id, Decimal("5"), cashier)


def test_low_stock_alert(svcs, owner, product):
    svcs["catalog"].update_product(product.id, owner, min_stock=Decimal("10"))
    svcs["inventory"].set_opening_stock(product.id, Decimal("8"), owner)
    low = svcs["inventory"].low_stock()
    assert any(e["product"].id == product.id for e in low)


def test_valuation(db, svcs, owner, product):
    svcs["inventory"].set_opening_stock(product.id, Decimal("10"), owner)
    val = svcs["inventory"].valuation()
    assert val["total"] == Decimal("3000.00")  # 10 x cost 300
