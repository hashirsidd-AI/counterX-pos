from datetime import datetime
from decimal import Decimal

from counterx import models


def _sale(svcs, user, total, day=None):
    s = svcs["sales"].s
    day = day or datetime.now().strftime("%Y-%m-%d")
    sale = models.Sale(
        invoice_no=svcs["sales"]._next_invoice_no(), token_no="T1",
        client_ref=f"r-{total}-{day}-{datetime.now().microsecond}",
        business_day=day, sale_type="takeaway", user_id=user.id,
        subtotal=total, tax_total=Decimal("0"), grand_total=total)
    s.add(sale)
    s.flush()
    s.add(models.Payment(sale_id=sale.id, method="cash", amount=total, received=total))
    s.flush()
    return sale


def test_daily_sales_reconciles(svcs, owner):
    day = datetime.now().strftime("%Y-%m-%d")
    _sale(svcs, owner, Decimal("1000"), day)
    _sale(svcs, owner, Decimal("2500"), day)
    rep = svcs["reports"].daily_sales(day)
    assert rep["transactions"] == 2
    assert rep["net"] == Decimal("3500.00")
    assert rep["by_method"]["cash"] == Decimal("3500.00")


def test_voided_excluded(svcs, owner):
    day = datetime.now().strftime("%Y-%m-%d")
    sale = _sale(svcs, owner, Decimal("1000"), day)
    svcs["sales"].void_sale(sale.id, owner)
    rep = svcs["reports"].daily_sales(day)
    assert rep["transactions"] == 0
    assert rep["net"] == Decimal("0.00")
    assert rep["voided_count"] == 1


def test_cashier_performance(svcs, owner):
    day = datetime.now().strftime("%Y-%m-%d")
    _sale(svcs, owner, Decimal("700"), day)
    perf = svcs["reports"].cashier_performance(day, day)
    assert perf[0]["transactions"] == 1
    assert perf[0]["total"] == Decimal("700.00")


def test_profit_estimate_labelled(svcs, owner):
    day = datetime.now().strftime("%Y-%m-%d")
    p = svcs["catalog"].create_product(owner, sku="P1", name="P1",
                                       sell_price=Decimal("500"),
                                       cost_price=Decimal("300"))
    cart_line = {"product_id": p.id}
    from counterx.services import Cart, CartLine
    cart = Cart(lines=[CartLine(product_id=p.id, variant_id=None, name="P1",
                                qty=Decimal("2"), unit_price=Decimal("500"),
                                tax_rate=Decimal("0"))])
    svcs["inventory"].set_opening_stock(p.id, Decimal("10"), owner)
    svcs["sales"].checkout(cart, [{"method": "cash", "amount": Decimal("1000"),
                                   "received": Decimal("1000")}], owner)
    est = svcs["reports"].profit_estimate(day, day)
    assert est["net_sales"] == Decimal("1000.00")
    assert est["cogs_estimate"] == Decimal("600.00")
    assert est["gross_profit_estimate"] == Decimal("400.00")
    assert "Estimate" in est["note"]
