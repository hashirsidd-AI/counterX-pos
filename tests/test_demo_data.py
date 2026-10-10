"""Demo catalogue seeding: idempotent, never touches real data."""
from decimal import Decimal

from counterx import models
from counterx.services.demo_data import (
    DEMO_CATEGORIES, DEMO_PRODUCTS, is_demo_seeded, remove_demo_data,
    seed_demo_menu,
)


def _demo_products(db):
    return (db.query(models.Product)
            .filter(models.Product.sku.like("DEMO-%")).all())


def test_seed_creates_categories_products_and_stock(db, svcs, owner):
    res = seed_demo_menu(db, owner)
    assert res["seeded"] is True
    assert res["products"] == len(DEMO_PRODUCTS)

    cats = db.query(models.Category).filter(
        models.Category.name.in_(DEMO_CATEGORIES)).all()
    assert len(cats) == 6

    prods = _demo_products(db)
    assert len(prods) == len(DEMO_PRODUCTS)
    names = {p.name for p in prods}
    assert "Zinger Burger" in names
    assert "Fajita Pizza (Medium)" in names
    assert "Mineral Water" in names

    # stock was set for every demo product
    inv = svcs["inventory"]
    levels = {p.name: inv.stock_level(p.id) for p in prods}
    assert levels["Zinger Burger"] == Decimal("50")
    assert levels["Pepsi"] == Decimal("100")
    assert levels["Extra Sauce"] == Decimal("80")

    # flag persisted
    assert is_demo_seeded(db) is True


def test_seed_is_idempotent(db, owner):
    assert seed_demo_menu(db, owner)["seeded"] is True
    second = seed_demo_menu(db, owner)
    assert second["seeded"] is False
    assert len(_demo_products(db)) == len(DEMO_PRODUCTS)
    assert db.query(models.Category).filter(
        models.Category.name.in_(DEMO_CATEGORIES)).count() == 6


def test_seed_does_not_touch_real_products(db, svcs, owner):
    real = svcs["catalog"].create_product(
        owner, sku="REAL-001", name="Real Biryani",
        sell_price=Decimal("250"), cost_price=Decimal("180"))
    real_id = real.id

    seed_demo_menu(db, owner)

    kept = db.get(models.Product, real_id)
    assert kept is not None
    assert kept.name == "Real Biryani"
    assert kept.sku == "REAL-001"
    assert kept.sell_price == Decimal("250")
    assert db.query(models.Product).count() == len(DEMO_PRODUCTS) + 1


def test_remove_demo_data_removes_only_demo(db, svcs, owner):
    real = svcs["catalog"].create_product(
        owner, sku="REAL-002", name="Real Kebab",
        sell_price=Decimal("300"))
    seed_demo_menu(db, owner)

    removed = remove_demo_data(db, owner)
    assert removed == len(DEMO_PRODUCTS)
    assert _demo_products(db) == []
    # demo categories are gone, flags cleared
    assert db.query(models.Category).filter(
        models.Category.name.in_(DEMO_CATEGORIES)).count() == 0
    assert is_demo_seeded(db) is False
    # real product untouched
    assert db.get(models.Product, real.id) is not None


def test_generate_sku_unique(svcs, owner):
    cat = svcs["catalog"]
    sku1 = cat.generate_sku()
    cat.create_product(owner, sku=sku1, name="A", sell_price=Decimal("10"))
    sku2 = cat.generate_sku()
    assert sku2 != sku1
    assert sku2.startswith("P-")
