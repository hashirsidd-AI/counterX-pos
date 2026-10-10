"""Ready-to-use demo catalogue: a Pakistani fast-food sample menu.

Data-only seeding — no schema changes. Idempotent: seeding twice never
duplicates anything, and real (non-demo) client data is never touched.
Demo products are marked with ``DEMO-`` SKUs so they are easy to find,
edit, or remove.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..utils.money import d, q
from .auth import AuthService
from .catalog import CatalogService
from .inventory import InventoryService

DEMO_SKU_PREFIX = "DEMO-"
SEED_FLAG_KEY = "demo_data_seeded"
SEED_CATS_KEY = "demo_category_ids"
DEMO_DESCRIPTION = "Demo sample item \u2014 edit or delete freely."

DEMO_CATEGORIES = [
    "Burgers",
    "Pizza",
    "Roasted & Grilled",
    "Fries & Sides",
    "Cold Drinks",
    "Extras",
]

# (category, name, sell_price, stock_qty, min_stock). Illustrative sample
# prices only \u2014 every price and quantity is editable in the app.
DEMO_PRODUCTS: list[tuple[str, str, str, str, str]] = [
    ("Burgers", "Zinger Burger", "450", "50", "10"),
    ("Burgers", "Chicken Burger", "350", "50", "10"),
    ("Burgers", "Beef Burger", "500", "40", "10"),
    ("Pizza", "Chicken Tikka Pizza (Small)", "650", "30", "8"),
    ("Pizza", "Fajita Pizza (Medium)", "1050", "25", "8"),
    ("Pizza", "Cheese Pizza (Small)", "600", "30", "8"),
    ("Roasted & Grilled", "Quarter Chicken Roast", "450", "40", "10"),
    ("Roasted & Grilled", "Half Chicken Roast", "850", "30", "8"),
    ("Roasted & Grilled", "Grilled Chicken", "550", "30", "8"),
    ("Fries & Sides", "Regular Fries", "200", "60", "15"),
    ("Fries & Sides", "Loaded Fries", "350", "40", "10"),
    ("Fries & Sides", "Chicken Nuggets", "300", "50", "10"),
    ("Cold Drinks", "Pepsi", "120", "100", "20"),
    ("Cold Drinks", "Coca-Cola", "120", "100", "20"),
    ("Cold Drinks", "7UP", "120", "100", "20"),
    ("Cold Drinks", "Mineral Water", "80", "100", "20"),
    ("Extras", "Extra Cheese", "100", "50", "10"),
    ("Extras", "Extra Sauce", "50", "80", "15"),
]


def _get_setting(s: Session, key: str) -> str:
    row = s.query(models.Setting).filter_by(key=key).first()
    return row.value if row and row.value else ""


def _set_setting(s: Session, key: str, value: str) -> None:
    row = s.query(models.Setting).filter_by(key=key).first()
    if row is None:
        s.add(models.Setting(key=key, value=value))
    else:
        row.value = value
    s.flush()


def is_demo_seeded(s: Session) -> bool:
    """True when the demo catalogue has been seeded (or was already present)."""
    if _get_setting(s, SEED_FLAG_KEY) == "1":
        return True
    return (s.query(models.Product)
            .filter(models.Product.sku.like(f"{DEMO_SKU_PREFIX}%"))
            .first() is not None)


def seed_demo_menu(s: Session, user: models.User) -> dict:
    """Insert the sample fast-food menu. Idempotent.

    Returns ``{"seeded": True, "products": N}`` on success, or
    ``{"seeded": False, "reason": ...}`` when seeding is skipped so existing
    data is never duplicated or overwritten.
    """
    if _get_setting(s, SEED_FLAG_KEY) == "1":
        return {"seeded": False, "reason": "already_seeded"}
    if (s.query(models.Product)
            .filter(models.Product.sku.like(f"{DEMO_SKU_PREFIX}%"))
            .first() is not None):
        return {"seeded": False, "reason": "demo_products_exist"}

    catalog = CatalogService(s, AuthService(s))
    inventory = InventoryService(s, AuthService(s))

    cat_ids: dict[str, int] = {}
    for name in DEMO_CATEGORIES:
        existing = (s.query(models.Category)
                    .filter(models.Category.name == name).first())
        if existing is not None:
            cat_ids[name] = existing.id
        else:
            cat = catalog.create_category(name, user)
            cat_ids[name] = cat.id

    n = 0
    for i, (cat_name, name, price, stock, min_stock) in enumerate(DEMO_PRODUCTS, 1):
        prod = catalog.create_product(
            user,
            sku=f"{DEMO_SKU_PREFIX}{i:03d}",
            name=name,
            sell_price=d(price),
            cost_price=d(price),
            category_id=cat_ids[cat_name],
            description=DEMO_DESCRIPTION,
            track_stock=True,
            min_stock=q(d(min_stock)),
        )
        inventory.set_opening_stock(prod.id, d(stock), user)
        n += 1

    _set_setting(s, SEED_FLAG_KEY, "1")
    _set_setting(s, SEED_CATS_KEY, ",".join(str(cat_ids[c]) for c in DEMO_CATEGORIES))
    s.flush()
    return {"seeded": True, "products": n}


def remove_demo_data(s: Session, user: models.User) -> int:
    """Remove demo products (and their opening stock moves) plus any demo
    categories left without real products. Never touches non-demo data.
    Returns the number of products removed."""
    auth = AuthService(s)
    auth.require(user, "products")

    demo_prods = (s.query(models.Product)
                  .filter(models.Product.sku.like(f"{DEMO_SKU_PREFIX}%"))
                  .all())
    removed = 0
    for p in demo_prods:
        # Never delete a demo product that has real business history
        # (sales or non-opening stock moves) attached to it.
        has_sales = (s.query(models.SaleItem)
                     .filter_by(product_id=p.id).first() is not None)
        has_moves = (s.query(models.StockMove)
                     .filter(models.StockMove.product_id == p.id,
                             models.StockMove.move_type != "opening")
                     .first() is not None)
        if has_sales or has_moves:
            continue
        (s.query(models.StockMove)
         .filter_by(product_id=p.id, move_type="opening").delete())
        s.delete(p)
        removed += 1
    s.flush()

    # Drop demo categories that no longer hold any (non-demo) products.
    raw = _get_setting(s, SEED_CATS_KEY)
    for cid_str in raw.split(","):
        cid_str = cid_str.strip()
        if not cid_str.isdigit():
            continue
        cid = int(cid_str)
        remaining = (s.query(models.Product)
                     .filter(models.Product.category_id == cid)
                     .first() is not None)
        if not remaining:
            cat = s.get(models.Category, cid)
            if cat is not None:
                s.delete(cat)
    s.flush()

    for key in (SEED_FLAG_KEY, SEED_CATS_KEY):
        row = s.query(models.Setting).filter_by(key=key).first()
        if row is not None:
            s.delete(row)
    s.flush()
    return removed
